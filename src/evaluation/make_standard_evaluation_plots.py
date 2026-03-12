#!/usr/bin/env python3
"""
Generate the standard set of evaluation plots for completed experiments.

Produces:
    - Global bar charts (column_mapping_accuracy, avg_value_accuracy, avg_value_f1)
    - Per-column performance heatmap
    - Confusion matrices per run per column (grouped by model)
    - Cross-model comparison heatmaps per column (if row_values.csv available)
    - Data tables (runs.csv, column_values.csv, confusion.csv, row_values.csv)

Usage:
    python make_standard_evaluation_plots.py \\
        --metrics-glob "results/*/metrics.json" \\
        --out-dir analysis/plots_YYYYMMDD_HHMM

    # With backfill for existing runs missing row_values.csv:
    python make_standard_evaluation_plots.py \\
        --metrics-glob "results/*/metrics.json" \\
        --out-dir analysis/plots_YYYYMMDD_HHMM \\
        --backfill-row-values
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.visualization.aggregate import heatmap_matrix
from evaluation.visualization.failure_io import build_all_runs_table, load_analysis_report
from evaluation.visualization.io import discover_metrics_files, load_metrics_bundle
from evaluation.visualization.normalize import build_tables
from evaluation.visualization.plots import (
    plot_boxplot,
    plot_confusion,
    plot_cross_model_comparison,
    plot_error_breakdown,
    plot_failure_distribution,
    plot_failure_sunburst,
    plot_global_bars,
    plot_heatmap,
    plot_success_failure_heatmap,
    save_figure,
)
from evaluation.visualization.report import write_manifest

logger = logging.getLogger(__name__)


def _generate_all_confusion_matrices(
    confusion_df, runs_df, plots_out, backend, figure_format, dpi, max_unique,
):
    """Generate confusion matrices for every run x column, organized by model subfolder."""
    generated = 0
    for _, run in runs_df.iterrows():
        run_id = run["run_id"]
        model_label = run.get("model_label", run_id)
        context = run.get("context", "")
        folder_name = model_label.replace("/", "_").replace(" ", "_")
        model_dir = plots_out / "confusion_matrices" / folder_name

        columns = confusion_df[confusion_df["run_id"] == run_id]["column_name"].unique()
        for col in columns:
            n_unique = confusion_df[
                (confusion_df["run_id"] == run_id) & (confusion_df["column_name"] == col)
            ]["expected_value"].nunique()
            if n_unique > max_unique:
                continue

            try:
                fig = plot_confusion(
                    confusion_df, run_id=run_id, column_name=col, backend=backend,
                )
                fname = f"confusion_{run_id}_{context}_{col}"
                save_figure(fig, model_dir / fname, backend=backend, figure_format=figure_format, dpi=dpi)
                generated += 1
            except Exception as e:
                logger.warning(f"Failed to generate confusion matrix for {run_id}/{col}: {e}")

    return generated


def _backfill_missing_row_values(runs_df):
    """Backfill row_values.csv for runs that don't have one yet."""
    # Import here to avoid circular dependency
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from calculate_metrics import backfill_row_values

    backfilled = 0
    for _, run in runs_df.iterrows():
        results_dir = Path(run["results_dir"])
        rv_path = results_dir / "row_values.csv"
        if rv_path.exists():
            continue
        logger.info(f"Backfilling row_values.csv for {results_dir.name}")
        ret = backfill_row_values(results_dir)
        if ret == 0:
            backfilled += 1
        else:
            logger.warning(f"Failed to backfill {results_dir.name}")

    if backfilled:
        logger.info(f"Backfilled {backfilled} runs")
    return backfilled


def main():
    parser = argparse.ArgumentParser(
        description="Generate standard evaluation plots for completed experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--metrics-files", nargs="*", default=[], help="Direct paths to metrics.json files")
    parser.add_argument("--metrics-glob", action="append", default=[], help="Glob pattern(s) to find metrics.json")
    parser.add_argument("--out-dir", required=True, help="Output directory for plots and tables")
    parser.add_argument("--backend", default="seaborn", choices=["seaborn", "plotly"])
    parser.add_argument("--figure-format", default="png", choices=["png", "svg", "pdf", "html"])
    parser.add_argument("--dpi", type=int, default=160)
    parser.add_argument("--max-unique-values", type=int, default=25,
                        help="Skip confusion matrices for columns with more unique values (default: 25)")
    parser.add_argument("--backfill-row-values", action="store_true",
                        help="Regenerate missing row_values.csv files before plotting")
    parser.add_argument("--skip-confusion", action="store_true", help="Skip confusion matrix generation")
    parser.add_argument("--skip-cross-compare", action="store_true", help="Skip cross-model comparison plots")
    parser.add_argument("--analysis-report", default=None,
                        help="Path to analysis report JSON (from read_and_analyze_logs_and_traces_cli.py --json) "
                             "to include failure mode plots")
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # 1. Discover and load metrics
    logger.info("Discovering metrics files...")
    paths = discover_metrics_files(args.metrics_files, args.metrics_glob)
    if not paths:
        raise SystemExit("No metrics files found. Provide --metrics-files or --metrics-glob")

    loaded, skipped = load_metrics_bundle(paths)
    logger.info(f"Loaded {len(loaded)} metrics files, skipped {len(skipped)}")

    tables = build_tables(loaded)
    runs = tables["runs"]
    if runs.empty:
        raise SystemExit("No run data available after loading.")

    base_out = Path(args.out_dir)
    plots_out = base_out / "plots"
    tables_out = base_out / "tables"

    # 2. Backfill row_values.csv if requested
    if args.backfill_row_values:
        _backfill_missing_row_values(runs)
        # Rebuild tables to pick up new row_values
        tables = build_tables(loaded)
        runs = tables["runs"]

    # 3. Save data tables
    logger.info("Saving data tables...")
    tables_out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(tables_out / f"{name}.csv", index=False)
        logger.info(f"  {name}.csv: {len(df)} rows")

    # 4. Global bar charts
    logger.info("Generating global bar charts...")
    plots_out.mkdir(parents=True, exist_ok=True)
    default_metrics = [
        "column_mapping_accuracy",
        "avg_value_accuracy_excl_empty",
        "avg_value_f1_excl_empty",
    ]
    for metric in default_metrics:
        if metric in runs.columns:
            fig = plot_global_bars(
                runs, metric=metric, x_col="display_label",
                hue_col="context", backend=args.backend,
                title=f"Global comparison: {metric}",
            )
            save_figure(
                fig, plots_out / f"global_bar_{metric}",
                backend=args.backend, figure_format=args.figure_format, dpi=args.dpi,
            )
            logger.info(f"  global_bar_{metric}")

    # 5. Per-column performance heatmap
    logger.info("Generating performance heatmap...")
    col_df = tables["column_values"]
    if not col_df.empty:
        matrix = heatmap_matrix(col_df, metric="accuracy_excl_empty", row_key="display_label")
        if not matrix.empty:
            fig = plot_heatmap(
                matrix, backend=args.backend,
                title="Per-column accuracy (excl empty)",
            )
            save_figure(
                fig, plots_out / "heatmap_accuracy_excl_empty",
                backend=args.backend, figure_format=args.figure_format, dpi=args.dpi,
            )
            logger.info("  heatmap_accuracy_excl_empty")

    # 6. Boxplots by grouping columns (if data available)
    for box_group in ["model_family_group", "is_local", "cost_tier"]:
        if box_group in runs.columns and runs[box_group].notna().any():
            for box_metric in default_metrics:
                if box_metric in runs.columns:
                    try:
                        fig = plot_boxplot(
                            runs, metric=box_metric, group_col=box_group,
                            backend=args.backend,
                            title=f"{box_metric} by {box_group}",
                        )
                        save_figure(
                            fig, plots_out / f"boxplot_{box_metric}_{box_group}",
                            backend=args.backend, figure_format=args.figure_format, dpi=args.dpi,
                        )
                    except Exception:
                        pass

    # 7. Confusion matrices — per model subfolder
    if not args.skip_confusion:
        confusion_df = tables["confusion"]
        if not confusion_df.empty:
            logger.info("Generating confusion matrices...")
            generated = _generate_all_confusion_matrices(
                confusion_df, runs, plots_out,
                args.backend, args.figure_format, args.dpi,
                args.max_unique_values,
            )
            logger.info(f"  Generated {generated} confusion matrices")
        else:
            logger.info("No confusion data available, skipping confusion matrices")

    # 8. Cross-model comparison heatmaps (if row_values available)
    if not args.skip_cross_compare:
        row_values = tables.get("row_values")
        if row_values is not None and not row_values.empty:
            logger.info("Generating cross-model comparison plots...")
            cross_out = plots_out / "cross_model_comparison"
            generated = 0
            for col in sorted(row_values["column_name"].unique()):
                try:
                    fig = plot_cross_model_comparison(
                        row_values, column_name=col, backend=args.backend,
                        title=f"Cross-model comparison: {col}",
                    )
                    save_figure(
                        fig, cross_out / f"cross_compare_{col}",
                        backend=args.backend, figure_format=args.figure_format, dpi=args.dpi,
                    )
                    generated += 1
                except ValueError as e:
                    logger.warning(f"Skipping cross-compare for {col}: {e}")
            logger.info(f"  Generated {generated} cross-model comparison plots")
        else:
            logger.info("No row_values data available, skipping cross-model comparison plots")

    # 9. Error breakdown (hallucinations / omissions / genuine errors)
    logger.info("Generating error breakdown...")
    try:
        fig = plot_error_breakdown(runs, backend=args.backend)
        save_figure(
            fig, plots_out / "error_breakdown",
            backend=args.backend, figure_format=args.figure_format, dpi=args.dpi,
        )
        logger.info("  error_breakdown")
    except ValueError as e:
        logger.info(f"  Skipping error breakdown: {e}")

    # 10. Failure mode plots (requires --analysis-report)
    if args.analysis_report:
        logger.info("Loading analysis report for failure mode plots...")
        try:
            report = load_analysis_report(args.analysis_report)
            all_runs = build_all_runs_table(report, tables)
            if not all_runs.empty:
                failure_out = plots_out / "failure_analysis"
                all_runs.to_csv(tables_out / "all_runs.csv", index=False)
                logger.info(f"  all_runs.csv: {len(all_runs)} rows")

                try:
                    fig = plot_success_failure_heatmap(all_runs, backend=args.backend)
                    save_figure(
                        fig, failure_out / "success_failure_heatmap",
                        backend=args.backend, figure_format=args.figure_format, dpi=args.dpi,
                    )
                    logger.info("  success_failure_heatmap")
                except (ValueError, KeyError) as e:
                    logger.warning(f"  Skipping success/failure heatmap: {e}")

                try:
                    fig = plot_failure_distribution(all_runs, backend=args.backend)
                    save_figure(
                        fig, failure_out / "failure_distribution",
                        backend=args.backend, figure_format=args.figure_format, dpi=args.dpi,
                    )
                    logger.info("  failure_distribution")
                except (ValueError, KeyError) as e:
                    logger.warning(f"  Skipping failure distribution: {e}")

                try:
                    fig = plot_failure_sunburst(all_runs, backend=args.backend)
                    save_figure(
                        fig, failure_out / "failure_sunburst",
                        backend=args.backend, figure_format=args.figure_format, dpi=args.dpi,
                    )
                    logger.info("  failure_sunburst")
                except (ValueError, KeyError) as e:
                    logger.warning(f"  Skipping failure sunburst: {e}")
            else:
                logger.warning("  Analysis report produced empty all_runs table")
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"  Failed to load analysis report: {e}")

    # 11. Write manifest
    write_manifest(base_out, {
        "command": "make_standard_evaluation_plots",
        "input_count": len(paths),
        "skipped": skipped,
        "backend": args.backend,
        "figure_format": args.figure_format,
        "runs": len(runs),
        "out_dir": str(base_out),
    })

    logger.info(f"\nAll plots saved to: {base_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
