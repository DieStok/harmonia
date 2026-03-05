#!/usr/bin/env python3
"""
CLI script for calculating metadata harmonization metrics.

Compares LLM-produced harmonized output against gold standard data and produces
a comprehensive metrics.json file with schema mapping quality, value harmonization
quality, and error analysis.

Usage:
    python calculate_metrics.py --results-dir <path> [options]
"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from evaluation.metrics import calculate_all_metrics
from evaluation.schemas import MetricsResult


def setup_logging(verbose: bool, log_file: Optional[Path] = None) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=handlers,
    )


def load_json(path: Path) -> dict | None:
    """Load JSON file, return None if not found."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_yaml(path: Path) -> dict:
    """Load YAML config file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _write_row_values_csv(result, row_values_path: Path) -> None:
    """Write row_values.csv from a MetricsResult."""
    with open(row_values_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "column_name", "source_column_name", "row_index",
            "gold_value", "predicted_value", "classification", "error_type",
        ])
        for col_name, col_metrics in result.column_values.items():
            for rc in col_metrics.row_comparisons:
                writer.writerow([
                    col_name,
                    col_metrics.source_column_name,
                    rc.row_index,
                    rc.gold_value,
                    rc.predicted_value,
                    rc.classification,
                    rc.error_type or "",
                ])


def backfill_row_values(results_dir: Path, verbose: bool = False) -> int:
    """Regenerate row_values.csv for an existing run without overwriting metrics.json.

    Tries two strategies to find required paths:
    1. From .experiment_id → config YAML → evaluation block
    2. From metrics.json → gold_standard_file, llm_output_file (with gold_column_mapping
       inferred from the gold standard directory)
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    results_dir = Path(results_dir)
    row_values_path = results_dir / "row_values.csv"

    gold_standard_path = None
    gold_column_mapping_path = None
    index_column = None
    numeric_tolerance = None
    acceptable_columns_path = None

    # Strategy 1: .experiment_id → config YAML
    exp_id_file = results_dir / ".experiment_id"
    if exp_id_file.exists():
        exp_id = json.loads(exp_id_file.read_text())
        config_path = exp_id.get("config_path")
        if config_path:
            config_path = Path(config_path)
            if not config_path.is_absolute():
                config_path = Path(__file__).parent / config_path
            if config_path.exists():
                config_data = load_yaml(config_path)
                evaluation_config = config_data.get("evaluation", {})
                gold_standard_path = evaluation_config.get("gold_standard")
                gold_column_mapping_path = evaluation_config.get("gold_column_mapping")
                index_column = evaluation_config.get("index_column")
                numeric_tolerance = evaluation_config.get("numeric_tolerance")
                acceptable_columns_path = evaluation_config.get("acceptable_columns_file")

    # Strategy 2: fall back to metrics.json
    if not gold_standard_path or not gold_column_mapping_path:
        metrics_file = results_dir / "metrics.json"
        if not metrics_file.exists():
            logger.error(f"Neither .experiment_id config nor metrics.json found in {results_dir}")
            return 1

        metrics_data = json.loads(metrics_file.read_text())
        gold_standard_path = gold_standard_path or metrics_data.get("gold_standard_file")

        if gold_standard_path and not gold_column_mapping_path:
            # Infer gold_column_mapping from gold standard directory
            gs_dir = Path(gold_standard_path).parent
            candidate = gs_dir / "gold_standard_column_mapping.json"
            if candidate.exists():
                gold_column_mapping_path = str(candidate)

            if not gold_column_mapping_path:
                # Try acceptable_columns as fallback for column list
                candidate2 = gs_dir / "harmonization_acceptable_columns.json"
                if candidate2.exists():
                    acceptable_columns_path = str(candidate2)

    if not gold_standard_path or not gold_column_mapping_path:
        logger.error(f"Cannot determine gold_standard and gold_column_mapping for {results_dir}")
        return 1

    gold_standard_path = Path(gold_standard_path)
    gold_column_mapping_path = Path(gold_column_mapping_path)

    if not gold_standard_path.exists():
        logger.error(f"Gold standard CSV not found: {gold_standard_path}")
        return 1
    if not gold_column_mapping_path.exists():
        logger.error(f"Gold column mapping not found: {gold_column_mapping_path}")
        return 1

    # Find LLM output
    llm_output_csv = results_dir / "dou_harmonized.csv"
    if not llm_output_csv.exists():
        candidates = list(results_dir.glob("*harmonized*.csv"))
        if candidates:
            llm_output_csv = candidates[0]
        else:
            logger.error(f"No harmonized output CSV found in {results_dir}")
            return 1

    # Load mappings
    gold_column_mapping = load_json(gold_column_mapping_path)
    llm_column_mapping = None
    llm_column_mapping_file = results_dir / "column_mapping.json"
    if llm_column_mapping_file.exists():
        llm_column_mapping = load_json(llm_column_mapping_file)

    acceptable_columns = None
    if acceptable_columns_path:
        acceptable_columns_path = Path(acceptable_columns_path)
        if acceptable_columns_path.exists():
            acceptable_columns = load_json(acceptable_columns_path)

    logger.info(f"Backfilling row_values.csv for {results_dir.name}")

    result = calculate_all_metrics(
        gold_standard_csv=gold_standard_path,
        llm_output_csv=llm_output_csv,
        gold_column_mapping=gold_column_mapping,
        llm_column_mapping=llm_column_mapping,
        acceptable_columns=acceptable_columns,
        index_column=index_column,
        numeric_tolerance=numeric_tolerance,
    )

    _write_row_values_csv(result, row_values_path)
    logger.info(f"✓ Row values backfilled to: {row_values_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Calculate metadata harmonization metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required
    parser.add_argument(
        "--results-dir",
        type=Path,
        required=True,
        help="Directory containing experiment results (with dou_harmonized.csv, etc.)",
    )

    # Config-based options
    parser.add_argument(
        "--config",
        type=Path,
        help="Experiment config YAML (reads evaluation block for paths)",
    )

    # Override options
    parser.add_argument(
        "--gold-standard",
        type=Path,
        help="Path to gold standard harmonized CSV",
    )
    parser.add_argument(
        "--gold-column-mapping",
        type=Path,
        help="Path to gold standard column mapping JSON",
    )
    parser.add_argument(
        "--gold-value-mapping",
        type=Path,
        help="Path to gold standard value mapping JSON (for reference)",
    )
    parser.add_argument(
        "--acceptable-columns",
        type=Path,
        help="Path to acceptable alternative column mappings JSON",
    )
    parser.add_argument(
        "--llm-output",
        type=str,
        default="dou_harmonized.csv",
        help="LLM output filename (default: dou_harmonized.csv)",
    )
    parser.add_argument(
        "--index-column",
        type=str,
        help="Index column name for row alignment verification",
    )
    parser.add_argument(
        "--numeric-tolerance",
        type=float,
        help="Tolerance for numeric comparisons",
    )

    # Backfill mode
    parser.add_argument(
        "--backfill-row-values",
        action="store_true",
        help="Regenerate row_values.csv from existing results without overwriting metrics.json",
    )

    # Logging
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Backfill mode: regenerate row_values.csv without recalculating metrics.json
    if args.backfill_row_values:
        return backfill_row_values(args.results_dir, verbose=args.verbose)

    # Setup logging
    log_file = args.results_dir / "metrics_calculation.log"
    setup_logging(args.verbose, log_file)
    logger = logging.getLogger(__name__)

    logger.info("=" * 80)
    logger.info("METADATA HARMONIZATION METRICS CALCULATION")
    logger.info("=" * 80)

    # Load config if provided
    config_data = None
    if args.config:
        logger.info(f"Loading config: {args.config}")
        config_data = load_yaml(args.config)

    # Determine paths (CLI args override config)
    evaluation_config = config_data.get("evaluation", {}) if config_data else {}

    gold_standard_path = args.gold_standard or evaluation_config.get("gold_standard")
    gold_column_mapping_path = args.gold_column_mapping or evaluation_config.get("gold_column_mapping")
    gold_value_mapping_path = args.gold_value_mapping or evaluation_config.get("gold_value_mapping")
    acceptable_columns_path = args.acceptable_columns or evaluation_config.get("acceptable_columns_file")
    index_column = args.index_column or evaluation_config.get("index_column")
    numeric_tolerance = args.numeric_tolerance or evaluation_config.get("numeric_tolerance")

    # Validate required paths
    if not gold_standard_path:
        logger.error("--gold-standard is required (or must be in config evaluation block)")
        sys.exit(1)

    if not gold_column_mapping_path:
        logger.error("--gold-column-mapping is required (or must be in config evaluation block)")
        sys.exit(1)

    gold_standard_path = Path(gold_standard_path)
    gold_column_mapping_path = Path(gold_column_mapping_path)

    if gold_value_mapping_path:
        gold_value_mapping_path = Path(gold_value_mapping_path)
    if acceptable_columns_path:
        acceptable_columns_path = Path(acceptable_columns_path)

    # Find LLM output files
    results_dir = Path(args.results_dir)
    llm_output_csv = results_dir / args.llm_output
    llm_column_mapping_file = results_dir / "column_mapping.json"
    llm_value_mapping_file = results_dir / "value_mapping.json"
    trace_file = results_dir / "trace.json"

    logger.info("\nPaths:")
    logger.info(f"  Results dir: {results_dir}")
    logger.info(f"  Gold standard CSV: {gold_standard_path}")
    logger.info(f"  Gold column mapping: {gold_column_mapping_path}")
    logger.info(f"  Gold value mapping: {gold_value_mapping_path}")
    logger.info(f"  Acceptable columns: {acceptable_columns_path}")
    logger.info(f"  LLM output CSV: {llm_output_csv}")
    logger.info(f"  LLM column mapping: {llm_column_mapping_file}")
    logger.info(f"  LLM value mapping: {llm_value_mapping_file}")
    logger.info(f"  Trace JSON: {trace_file}")

    # Check file existence
    if not llm_output_csv.exists():
        logger.error(f"LLM output CSV not found: {llm_output_csv}")
        sys.exit(1)

    if not gold_standard_path.exists():
        logger.error(f"Gold standard CSV not found: {gold_standard_path}")
        sys.exit(1)

    if not gold_column_mapping_path.exists():
        logger.error(f"Gold column mapping not found: {gold_column_mapping_path}")
        sys.exit(1)

    # Load files
    logger.info("\nLoading files...")

    gold_column_mapping = load_json(gold_column_mapping_path)
    logger.info(f"  ✓ Loaded gold column mapping: {len(gold_column_mapping)} columns")

    gold_value_mapping = None
    if gold_value_mapping_path and gold_value_mapping_path.exists():
        gold_value_mapping = load_json(gold_value_mapping_path)
        logger.info("  ✓ Loaded gold value mapping")
    else:
        logger.info("  ⊘ Gold value mapping not found (optional)")

    acceptable_columns = None
    if acceptable_columns_path and acceptable_columns_path.exists():
        acceptable_columns = load_json(acceptable_columns_path)
        logger.info(f"  ✓ Loaded acceptable columns: {len(acceptable_columns)} columns")
    else:
        logger.info("  ⊘ Acceptable columns not found (optional)")

    llm_column_mapping = None
    if llm_column_mapping_file.exists():
        llm_column_mapping = load_json(llm_column_mapping_file)
        logger.info(f"  ✓ Loaded LLM column mapping: {len(llm_column_mapping)} columns")
    else:
        logger.warning("  ⚠ LLM column mapping not found - will use fallback mode")

    trace_data = None
    if trace_file.exists():
        trace_data = load_json(trace_file)
        logger.info("  ✓ Loaded trace.json for metadata extraction")
    else:
        logger.info("  ⊘ trace.json not found (optional)")

    # Calculate metrics
    logger.info("\n" + "=" * 80)
    logger.info("CALCULATING METRICS")
    logger.info("=" * 80 + "\n")

    try:
        result = calculate_all_metrics(
            gold_standard_csv=gold_standard_path,
            llm_output_csv=llm_output_csv,
            gold_column_mapping=gold_column_mapping,
            llm_column_mapping=llm_column_mapping,
            gold_value_mapping=gold_value_mapping,
            acceptable_columns=acceptable_columns,
            index_column=index_column,
            numeric_tolerance=numeric_tolerance,
            trace_json=trace_data,
            value_mapping_file_found=llm_value_mapping_file.exists(),
        )

        # Validate with Pydantic (should already be validated, but double-check)
        validated_result = MetricsResult.model_validate(result.model_dump())

        # Write metrics.json (exclude row_comparisons — stored separately in row_values.csv)
        metrics_path = results_dir / "metrics.json"
        metrics_path.write_text(validated_result.model_dump_json(
            indent=2,
            exclude={"column_values": {"__all__": {"row_comparisons"}}},
        ))

        # Emit per-row comparison data as row_values.csv
        row_values_path = results_dir / "row_values.csv"
        _write_row_values_csv(validated_result, row_values_path)
        logger.info(f"✓ Row values saved to: {row_values_path}")

        logger.info("\n" + "=" * 80)
        logger.info("METRICS SUMMARY")
        logger.info("=" * 80)
        logger.info(f"\nExperiment: {result.metadata.experiment_name}")
        logger.info(f"Timestamp: {result.metadata.timestamp}")

        if result.metadata.llm_provider:
            logger.info(f"LLM: {result.metadata.llm_provider} / {result.metadata.llm_model}")

        logger.info("\n--- Column Mapping Metrics ---")
        logger.info(f"Accuracy: {result.column_mapping.accuracy:.2%}")
        logger.info(f"Precision (excl null): {result.column_mapping.precision_excl_null:.2%}")
        logger.info(f"Precision (incl null): {result.column_mapping.precision_incl_null:.2%}")
        logger.info(f"Recall: {result.column_mapping.recall:.2%}")
        logger.info(f"Correct: {result.column_mapping.correct}/{result.column_mapping.total_expected}")
        logger.info(f"Wrong: {result.column_mapping.wrong}")
        logger.info(f"Missing: {result.column_mapping.missing}")
        logger.info(f"Explicitly null: {result.column_mapping.explicitly_null}")

        logger.info("\n--- Overall Value Metrics ---")
        logger.info(f"Columns evaluated: {result.overall_summary.total_columns}")
        logger.info(f"Avg accuracy (incl empty): {result.overall_summary.avg_accuracy_incl_empty:.2%}")
        logger.info(f"Avg accuracy (excl empty): {result.overall_summary.avg_accuracy_excl_empty:.2%}")
        logger.info(f"Avg precision (incl empty): {result.overall_summary.avg_precision_incl_empty:.2%}")
        logger.info(f"Avg recall (incl empty): {result.overall_summary.avg_recall_incl_empty:.2%}")
        logger.info(f"Avg F1 (incl empty): {result.overall_summary.avg_f1_incl_empty:.2%}")

        logger.info("\n--- Completeness ---")
        logger.info(f"Total hallucinations: {result.overall_summary.total_hallucinations}")
        logger.info(f"Total omissions: {result.overall_summary.total_omissions}")
        logger.info(f"Avg hallucination rate: {result.overall_summary.avg_hallucination_rate:.2%}")
        logger.info(f"Avg omission rate: {result.overall_summary.avg_omission_rate:.2%}")

        logger.info("\n--- Error Analysis ---")
        logger.info(f"Total errors: {result.overall_summary.total_errors}")
        logger.info(f"Whitespace-only: {result.overall_summary.total_whitespace_only}")
        logger.info(f"Case-only: {result.overall_summary.total_case_only}")
        logger.info(f"Whitespace + case: {result.overall_summary.total_whitespace_and_case}")
        logger.info(f"Genuine errors: {result.overall_summary.total_genuine}")

        if result.extra_columns_count > 0:
            logger.info("\n--- Extra Columns ---")
            logger.info(f"Count: {result.extra_columns_count}")
            logger.info(f"Columns: {result.extra_columns}")

        logger.info("\n" + "=" * 80)
        logger.info(f"✓ Metrics saved to: {metrics_path}")
        logger.info(f"✓ Log saved to: {log_file}")
        logger.info("=" * 80)

        return 0

    except Exception as e:
        logger.error(f"\n✗ Error calculating metrics: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
