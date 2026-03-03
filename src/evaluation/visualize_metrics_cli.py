#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script without installing package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.visualization.aggregate import apply_cost_bins, apply_filters, heatmap_matrix
from evaluation.visualization.enrich import load_labels_file
from evaluation.visualization.io import discover_metrics_files, load_metrics_bundle
from evaluation.visualization.normalize import build_tables
from evaluation.visualization.plots import (
    plot_boxplot,
    plot_confusion,
    plot_global_bars,
    plot_heatmap,
    save_figure,
)
from evaluation.visualization.report import write_manifest


def _common_parser(parser: argparse.ArgumentParser):
    parser.add_argument("--metrics-files", nargs="*", default=[], help="metrics.json files or result dirs")
    parser.add_argument("--metrics-glob", action="append", default=[], help="glob pattern(s) to metrics.json")
    parser.add_argument("--labels-file", help="optional CSV/JSON labels metadata")
    parser.add_argument("--include-runs", help="regex filter include experiment_name")
    parser.add_argument("--exclude-runs", help="regex filter exclude experiment_name")
    parser.add_argument("--out-dir", default="analysis/visualizations", help="output directory")
    parser.add_argument("--backend", choices=["seaborn", "plotly"], default="seaborn")
    parser.add_argument("--interactive", action="store_true", help="shortcut for --backend plotly")
    parser.add_argument("--figure-format", default="png", choices=["png", "svg", "pdf", "html"])
    parser.add_argument("--dpi", type=int, default=160)
    parser.add_argument("--save-dataframes", action="store_true")
    parser.add_argument("--group-by", default=None, help="Column to group by instead of display_label (e.g. model_family_group, cost_tier, is_local)")
    parser.add_argument("--sort-by", default=None, help="Column to sort results by")
    parser.add_argument("--cost-bin-edges", default=None, help="Comma-separated cost tier bin edges (e.g. 0,0.5,5,999)")


def _load_tables(args) -> tuple[dict, list[Path], list[dict[str, str]]]:
    paths = discover_metrics_files(args.metrics_files, args.metrics_glob)
    if not paths:
        raise SystemExit("No metrics files found. Provide --metrics-files or --metrics-glob")
    loaded, skipped = load_metrics_bundle(paths)
    labels = load_labels_file(args.labels_file)
    tables = build_tables(loaded, labels_df=labels)

    for key in ["runs", "column_mapping", "column_values", "confusion"]:
        tables[key] = apply_filters(tables[key], include_runs=args.include_runs, exclude_runs=args.exclude_runs)

    # Apply custom cost bins if specified
    cost_edges = getattr(args, "cost_bin_edges", None)
    if cost_edges and not tables["runs"].empty:
        edges = [float(x) for x in cost_edges.split(",")]
        tables["runs"] = apply_cost_bins(tables["runs"], bin_edges=edges)

    return tables, paths, skipped


def _error_columns(column_values_df):
    if column_values_df.empty or "error_total" not in column_values_df.columns:
        return set()
    agg = column_values_df.groupby("column_name", dropna=False)["error_total"].sum(min_count=1)
    return set(agg[agg.fillna(0) > 0].index.tolist())


def cmd_summarize(args):
    tables, paths, skipped = _load_tables(args)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = tables["runs"].copy()
    if runs.empty:
        print("No runs to summarize after filtering.")
        return

    cols = [
        "run_id",
        "experiment_name",
        "model_label",
        "context",
        "model_family",
        "column_mapping_accuracy",
        "avg_value_accuracy_excl_empty",
        "avg_value_f1_excl_empty",
        "timing_seconds",
    ]
    cols = [c for c in cols if c in runs.columns]
    summary = runs[cols].sort_values(by=["column_mapping_accuracy", "avg_value_accuracy_excl_empty"], ascending=False)
    print(summary.to_string(index=False))

    summary.to_csv(out_dir / "run_summary.csv", index=False)
    if args.save_dataframes:
        for name, df in tables.items():
            df.to_csv(out_dir / f"{name}.csv", index=False)

    write_manifest(out_dir, {
        "command": "summarize",
        "input_count": len(paths),
        "skipped": skipped,
        "out_dir": str(out_dir),
    })


def cmd_bars(args):
    tables, paths, skipped = _load_tables(args)
    out_dir = Path(args.out_dir) / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = tables["runs"]
    if runs.empty:
        raise SystemExit("No run data available.")

    backend = "plotly" if args.interactive else args.backend
    metric = args.metric
    if metric not in runs.columns:
        raise SystemExit(f"Unknown metric '{metric}'.")

    x_col = args.group_by or "display_label"
    if args.sort_by and args.sort_by in runs.columns:
        runs = runs.sort_values(args.sort_by, ascending=False)

    fig = plot_global_bars(runs, metric=metric, x_col=x_col, hue_col=args.hue, backend=backend, title=f"Global comparison: {metric}")
    save_figure(fig, out_dir / f"global_bar_{metric}", backend=backend, figure_format=args.figure_format, dpi=args.dpi)

    write_manifest(Path(args.out_dir), {
        "command": "bars",
        "metric": metric,
        "group_by": x_col,
        "backend": backend,
        "input_count": len(paths),
        "skipped": skipped,
    })


def cmd_heatmap(args):
    tables, paths, skipped = _load_tables(args)
    out_dir = Path(args.out_dir) / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    backend = "plotly" if args.interactive else args.backend
    metric = args.metric

    col_df = tables["column_values"].copy()
    if args.error_columns_only:
        err_cols = _error_columns(col_df)
        col_df = col_df[col_df["column_name"].isin(err_cols)] if err_cols else col_df.iloc[0:0]

    row_key = args.group_by or "display_label"
    matrix = heatmap_matrix(col_df, metric=metric, row_key=row_key, columns_mode=args.columns_mode)
    if args.topk_columns and args.topk_columns > 0 and not matrix.empty:
        ranked = matrix.mean(axis=0).sort_values(ascending=False).head(args.topk_columns).index
        matrix = matrix.loc[:, ranked]
    if matrix.empty:
        raise SystemExit("No heatmap data available.")

    suffix = "_errors_only" if args.error_columns_only else ""
    fig = plot_heatmap(matrix, backend=backend, title=f"Per-column {metric}{' (error columns)' if args.error_columns_only else ''}")
    save_figure(fig, out_dir / f"heatmap_{metric}{suffix}", backend=backend, figure_format=args.figure_format, dpi=args.dpi)

    write_manifest(Path(args.out_dir), {
        "command": "heatmap",
        "metric": metric,
        "error_columns_only": bool(args.error_columns_only),
        "backend": backend,
        "input_count": len(paths),
        "skipped": skipped,
    })


def cmd_confusion(args):
    tables, paths, skipped = _load_tables(args)
    out_dir = Path(args.out_dir) / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    backend = "plotly" if args.interactive else args.backend
    confusion_df = tables["confusion"]
    if confusion_df.empty:
        raise SystemExit("No confusion data available.")

    run_id = args.run_id or sorted(confusion_df["run_id"].unique())[0]
    candidates = confusion_df[confusion_df["run_id"] == run_id]["column_name"].unique().tolist()
    column_name = args.column or (candidates[0] if candidates else None)
    if not column_name:
        raise SystemExit(f"No confusion columns found for run_id={run_id}")

    fig = plot_confusion(
        confusion_df,
        run_id=run_id,
        column_name=column_name,
        normalize=args.normalize,
        top_n_labels=args.top_n_labels,
        backend=backend,
    )
    save_figure(fig, out_dir / f"confusion_{run_id}_{column_name}", backend=backend, figure_format=args.figure_format, dpi=args.dpi)

    write_manifest(Path(args.out_dir), {
        "command": "confusion",
        "run_id": run_id,
        "column": column_name,
        "backend": backend,
        "input_count": len(paths),
        "skipped": skipped,
    })


def cmd_errors(args):
    tables, paths, skipped = _load_tables(args)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    confusion_df = tables["confusion"].copy()
    if confusion_df.empty:
        raise SystemExit("No confusion data available for error analysis.")

    if args.run_id:
        confusion_df = confusion_df[confusion_df["run_id"] == args.run_id]

    errors = confusion_df[confusion_df["expected_value"] != confusion_df["predicted_value"]].copy()
    if args.error_columns_only:
        err_cols = set(errors["column_name"].unique())
        errors = errors[errors["column_name"].isin(err_cols)]
    if errors.empty:
        print("No errors found for selected filters.")
        return

    grouped = (
        errors.groupby(["run_id", "column_name", "expected_value", "predicted_value"], dropna=False)["count"]
        .sum()
        .reset_index()
        .sort_values(["run_id", "column_name", "count"], ascending=[True, True, False])
    )

    top = grouped.groupby(["run_id", "column_name"], dropna=False).head(args.top_n)
    print(top.to_string(index=False))
    top.to_csv(out_dir / "top_errors_per_column.csv", index=False)

    summary = (
        errors.groupby(["run_id", "column_name"], dropna=False)["count"]
        .sum()
        .reset_index(name="total_error_count")
        .sort_values(["run_id", "total_error_count"], ascending=[True, False])
    )
    summary.to_csv(out_dir / "error_columns_summary.csv", index=False)

    write_manifest(out_dir, {
        "command": "errors",
        "run_id": args.run_id,
        "top_n": args.top_n,
        "input_count": len(paths),
        "skipped": skipped,
    })


def cmd_boxplot(args):
    tables, paths, skipped = _load_tables(args)
    out_dir = Path(args.out_dir) / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = tables["runs"]
    if runs.empty:
        raise SystemExit("No run data available.")

    backend = "plotly" if args.interactive else args.backend
    metric = args.metric
    if metric not in runs.columns:
        raise SystemExit(f"Unknown metric '{metric}'.")

    group_col = args.group_by or "model_family_group"
    hue_col = args.hue if hasattr(args, "hue") else None

    fig = plot_boxplot(runs, metric=metric, group_col=group_col, hue_col=hue_col, backend=backend, title=f"{metric} by {group_col}")
    save_figure(fig, out_dir / f"boxplot_{metric}_{group_col}", backend=backend, figure_format=args.figure_format, dpi=args.dpi)

    write_manifest(Path(args.out_dir), {
        "command": "boxplot",
        "metric": metric,
        "group_by": group_col,
        "hue": hue_col,
        "backend": backend,
        "input_count": len(paths),
        "skipped": skipped,
    })


def cmd_compare(args):
    tables, paths, skipped = _load_tables(args)
    base_out = Path(args.out_dir)
    plots_out = base_out / "plots"
    tables_out = base_out / "tables"
    plots_out.mkdir(parents=True, exist_ok=True)
    tables_out.mkdir(parents=True, exist_ok=True)

    backend = "plotly" if args.interactive else args.backend
    runs = tables["runs"]
    if runs.empty:
        raise SystemExit("No run data available.")

    default_metrics = [
        "column_mapping_accuracy",
        "avg_value_accuracy_excl_empty",
        "avg_value_f1_excl_empty",
    ]
    for metric in default_metrics:
        if metric in runs.columns:
            fig = plot_global_bars(runs, metric=metric, x_col="display_label", hue_col="context", backend=backend, title=f"Global comparison: {metric}")
            save_figure(fig, plots_out / f"global_bar_{metric}", backend=backend, figure_format=args.figure_format, dpi=args.dpi)

    col_df = tables["column_values"].copy()
    if args.error_columns_only:
        err_cols = _error_columns(col_df)
        col_df = col_df[col_df["column_name"].isin(err_cols)] if err_cols else col_df.iloc[0:0]

    heat_metric = args.metric if args.metric in col_df.columns else "accuracy_excl_empty"
    matrix = heatmap_matrix(col_df, metric=heat_metric, row_key="display_label", columns_mode=args.columns_mode)
    if not matrix.empty:
        fig = plot_heatmap(matrix, backend=backend, title=f"Per-column {heat_metric}")
        save_figure(fig, plots_out / f"heatmap_{heat_metric}", backend=backend, figure_format=args.figure_format, dpi=args.dpi)

    for name, df in tables.items():
        df.to_csv(tables_out / f"{name}.csv", index=False)

    # Boxplots by model_family_group and is_local (if data available)
    for box_group in ["model_family_group", "is_local", "cost_tier"]:
        if box_group in runs.columns and runs[box_group].notna().any():
            for box_metric in default_metrics:
                if box_metric in runs.columns:
                    try:
                        fig = plot_boxplot(runs, metric=box_metric, group_col=box_group, backend=backend, title=f"{box_metric} by {box_group}")
                        save_figure(fig, plots_out / f"boxplot_{box_metric}_{box_group}", backend=backend, figure_format=args.figure_format, dpi=args.dpi)
                    except Exception:
                        pass

    # Always produce error summary tables in compare
    confusion_df = tables["confusion"]
    errors = confusion_df[confusion_df["expected_value"] != confusion_df["predicted_value"]] if not confusion_df.empty else confusion_df
    if not errors.empty:
        top = (
            errors.groupby(["run_id", "column_name", "expected_value", "predicted_value"], dropna=False)["count"]
            .sum().reset_index().sort_values(["run_id", "column_name", "count"], ascending=[True, True, False])
            .groupby(["run_id", "column_name"], dropna=False).head(10)
        )
        top.to_csv(tables_out / "top_errors_per_column.csv", index=False)

    write_manifest(base_out, {
        "command": "compare",
        "backend": backend,
        "error_columns_only": bool(args.error_columns_only),
        "input_count": len(paths),
        "skipped": skipped,
        "metrics": default_metrics,
        "heatmap_metric": heat_metric,
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Visualize Harmonia metrics.json results")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sum = sub.add_parser("summarize", help="Print and export run summary table")
    _common_parser(p_sum)
    p_sum.set_defaults(func=cmd_summarize)

    p_bars = sub.add_parser("bars", help="Generate global bar comparison")
    _common_parser(p_bars)
    p_bars.add_argument("--metric", default="avg_value_accuracy_excl_empty")
    p_bars.add_argument("--hue", default="context")
    p_bars.set_defaults(func=cmd_bars)

    p_heat = sub.add_parser("heatmap", help="Generate model-by-column heatmap")
    _common_parser(p_heat)
    p_heat.add_argument("--metric", default="accuracy_excl_empty")
    p_heat.add_argument("--columns-mode", choices=["union", "intersection"], default="union")
    p_heat.add_argument("--topk-columns", type=int)
    p_heat.add_argument("--error-columns-only", action="store_true", help="restrict heatmap to columns with any errors")
    p_heat.set_defaults(func=cmd_heatmap)

    p_conf = sub.add_parser("confusion", help="Generate confusion matrix for run+column")
    _common_parser(p_conf)
    p_conf.add_argument("--run-id")
    p_conf.add_argument("--column")
    p_conf.add_argument("--normalize", choices=["none", "rows"], default="none")
    p_conf.add_argument("--top-n-labels", type=int, default=20)
    p_conf.set_defaults(func=cmd_confusion)

    p_err = sub.add_parser("errors", help="Print top errors per column")
    _common_parser(p_err)
    p_err.add_argument("--run-id", help="optional run id filter")
    p_err.add_argument("--top-n", type=int, default=10)
    p_err.add_argument("--error-columns-only", action="store_true", help="subset to columns with any errors")
    p_err.set_defaults(func=cmd_errors)

    p_box = sub.add_parser("boxplot", help="Generate box-and-whisker plot by group")
    _common_parser(p_box)
    p_box.add_argument("--metric", default="avg_value_accuracy_excl_empty")
    p_box.add_argument("--hue", default=None)
    p_box.set_defaults(func=cmd_boxplot)

    p_cmp = sub.add_parser("compare", help="Generate full comparison bundle")
    _common_parser(p_cmp)
    p_cmp.add_argument("--metric", default="accuracy_excl_empty")
    p_cmp.add_argument("--columns-mode", choices=["union", "intersection"], default="union")
    p_cmp.add_argument("--error-columns-only", action="store_true", help="restrict per-column plots to columns with errors")
    p_cmp.set_defaults(func=cmd_compare)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
