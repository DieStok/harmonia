"""
Core metrics calculation functions for metadata harmonization evaluation.

This module provides functions to calculate various metrics that evaluate
the quality of LLM metadata harmonization by comparing against gold standards.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .schemas import (
    ColumnMappingDetail,
    ColumnMappingMetrics,
    ColumnValueMetrics,
    ErrorCategorization,
    ExperimentMetadata,
    MetricsResult,
    Misclassification,
    OverallSummary,
)

logger = logging.getLogger(__name__)


def _is_empty(value) -> bool:
    """Check if a value is empty (None, NaN, or empty string after stripping)."""
    if pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _normalize_value(value: str) -> str:
    """Normalize a value for comparison (strip whitespace, lowercase)."""
    if _is_empty(value):
        return ""
    return str(value).strip().lower()


def _categorize_error(expected: str, actual: str) -> str:
    """
    Categorize an error into one of four types:
    - whitespace_only: error disappears after strip()
    - case_only: error disappears after lower()
    - whitespace_and_case: error disappears after strip().lower()
    - genuine: error remains after normalization
    """
    expected_str = str(expected)
    actual_str = str(actual)

    # Check strip() alone
    if expected_str.strip() == actual_str.strip():
        return "whitespace_only"

    # Check lower() alone
    if expected_str.lower() == actual_str.lower():
        return "case_only"

    # Check strip().lower()
    if expected_str.strip().lower() == actual_str.strip().lower():
        return "whitespace_and_case"

    return "genuine"


def calculate_column_mapping_metrics(
    llm_column_mapping: dict[str, str | None],
    gold_column_mapping: dict[str, str],
    acceptable_columns: dict[str, list[str]] | None = None,
) -> ColumnMappingMetrics:
    """
    Calculate metrics for column mapping quality (schema harmonization).

    Args:
        llm_column_mapping: LLM-produced column mapping {source_col: target_col}
        gold_column_mapping: Gold standard column mapping {source_col: target_col}
        acceptable_columns: Optional dict of acceptable alternative mappings
                          {source_col: [acceptable_target1, acceptable_target2]}

    Returns:
        ColumnMappingMetrics with precision, recall, accuracy, and details
    """
    acceptable_columns = acceptable_columns or {}

    total_expected = len(gold_column_mapping)
    correct = 0
    wrong = 0
    missing = 0
    explicitly_null = 0
    details = []

    for source_col, expected_target in gold_column_mapping.items():
        actual_target = llm_column_mapping.get(source_col)

        is_correct = False
        is_acceptable = False
        is_missing = False
        is_explicitly_null = False
        is_wrong = False

        if source_col not in llm_column_mapping:
            # Column not mapped at all
            missing += 1
            is_missing = True
        elif actual_target is None:
            # Explicitly mapped to null
            explicitly_null += 1
            is_explicitly_null = True
        elif isinstance(actual_target, list):
            # One-to-many mapping not yet supported
            raise NotImplementedError(
                f"One-to-many column mapping not yet supported: {source_col} -> {actual_target}"
            )
        elif actual_target == expected_target:
            # Exact match
            correct += 1
            is_correct = True
        elif source_col in acceptable_columns and actual_target in acceptable_columns[source_col]:
            # Acceptable alternative
            correct += 1
            is_correct = True
            is_acceptable = True
        else:
            # Wrong mapping
            wrong += 1
            is_wrong = True

        details.append(ColumnMappingDetail(
            source_column=source_col,
            expected_target=expected_target,
            actual_target=actual_target,
            is_correct=is_correct,
            is_acceptable=is_acceptable,
            is_missing=is_missing,
            is_explicitly_null=is_explicitly_null,
            is_wrong=is_wrong,
        ))

    # Calculate metrics
    # Precision excluding null: correct / (correct + wrong)
    mapped_count_excl_null = correct + wrong
    precision_excl_null = correct / mapped_count_excl_null if mapped_count_excl_null > 0 else 0.0

    # Precision including null: correct / (correct + wrong + explicitly_null)
    mapped_count_incl_null = correct + wrong + explicitly_null
    precision_incl_null = correct / mapped_count_incl_null if mapped_count_incl_null > 0 else 0.0

    # Recall: correct / total_expected
    recall = correct / total_expected if total_expected > 0 else 0.0

    # Accuracy: correct / total_expected (same as recall for this use case)
    accuracy = recall

    return ColumnMappingMetrics(
        total_expected=total_expected,
        correct=correct,
        wrong=wrong,
        missing=missing,
        explicitly_null=explicitly_null,
        precision_excl_null=precision_excl_null,
        precision_incl_null=precision_incl_null,
        recall=recall,
        accuracy=accuracy,
        details=details,
    )


def calculate_column_value_metrics(
    gold_values: list[str],
    llm_values: list[str],
    column_name: str,
    source_column_name: str,
    numeric_tolerance: float | None = None,
) -> ColumnValueMetrics:
    """
    Calculate metrics for value harmonization quality in a single column.

    Args:
        gold_values: Gold standard column values (all rows)
        llm_values: LLM output column values (all rows)
        column_name: Gold standard column name
        source_column_name: Original source column name

    Returns:
        ColumnValueMetrics with accuracy, precision, recall, F1, and error details
    """
    if len(gold_values) != len(llm_values):
        raise ValueError(
            f"Length mismatch for column {column_name}: "
            f"gold has {len(gold_values)} rows, LLM has {len(llm_values)} rows"
        )

    total_cells = len(gold_values)

    # Counters for different cell types
    correct_filled = 0  # Both filled, match
    empty_empty = 0  # Both empty
    hallucination = 0  # Gold empty, LLM filled
    omission = 0  # Gold filled, LLM empty

    # Error categorization
    whitespace_only_errors = 0
    case_only_errors = 0
    whitespace_and_case_errors = 0
    genuine_errors = 0

    # Detailed tracking
    misclassifications = []
    confusion_matrix: dict[str, dict[str, int]] = {}

    # For multi-class metrics
    all_classes = set()
    class_tp = {}  # True positives per class
    class_fp = {}  # False positives per class
    class_fn = {}  # False negatives per class

    for i, (gold_val, llm_val) in enumerate(zip(gold_values, llm_values)):
        gold_empty = _is_empty(gold_val)
        llm_empty = _is_empty(llm_val)

        # Normalize for class tracking (use empty string for empty values)
        gold_normalized = "" if gold_empty else str(gold_val).strip()
        llm_normalized = "" if llm_empty else str(llm_val).strip()

        all_classes.add(gold_normalized)
        all_classes.add(llm_normalized)

        if gold_empty and llm_empty:
            empty_empty += 1
        elif gold_empty and not llm_empty:
            hallucination += 1
        elif not gold_empty and llm_empty:
            omission += 1
        elif gold_normalized == llm_normalized:
            correct_filled += 1
        else:
            # Try numeric comparison if tolerance is set
            if numeric_tolerance is not None:
                try:
                    gold_num = float(gold_normalized)
                    llm_num = float(llm_normalized)
                    if abs(gold_num - llm_num) <= numeric_tolerance:
                        correct_filled += 1
                        # Update confusion matrix and skip error categorization
                        if gold_normalized not in confusion_matrix:
                            confusion_matrix[gold_normalized] = {}
                        if llm_normalized not in confusion_matrix[gold_normalized]:
                            confusion_matrix[gold_normalized][llm_normalized] = 0
                        confusion_matrix[gold_normalized][llm_normalized] += 1
                        continue
                except (ValueError, TypeError):
                    pass  # Not numeric, fall through to error categorization

            # Misclassification - categorize the error
            error_type = _categorize_error(gold_val, llm_val)

            if error_type == "whitespace_only":
                whitespace_only_errors += 1
            elif error_type == "case_only":
                case_only_errors += 1
            elif error_type == "whitespace_and_case":
                whitespace_and_case_errors += 1
            else:
                genuine_errors += 1

            misclassifications.append(Misclassification(
                row_index=i,
                expected=gold_normalized,
                actual=llm_normalized,
                error_type=error_type,
            ))

        # Update confusion matrix (sparse representation)
        if gold_normalized not in confusion_matrix:
            confusion_matrix[gold_normalized] = {}
        if llm_normalized not in confusion_matrix[gold_normalized]:
            confusion_matrix[gold_normalized][llm_normalized] = 0
        confusion_matrix[gold_normalized][llm_normalized] += 1

    # Calculate per-class TP, FP, FN for macro-averaging
    for class_label in all_classes:
        tp = confusion_matrix.get(class_label, {}).get(class_label, 0)

        # FP: sum of predictions as this class when gold was something else
        fp = sum(
            confusion_matrix.get(other_class, {}).get(class_label, 0)
            for other_class in all_classes if other_class != class_label
        )

        # FN: sum of predictions as something else when gold was this class
        fn = sum(
            count for pred_class, count in confusion_matrix.get(class_label, {}).items()
            if pred_class != class_label
        )

        class_tp[class_label] = tp
        class_fp[class_label] = fp
        class_fn[class_label] = fn

    # Macro-averaged precision, recall, F1 (including empty class)
    precisions_incl = []
    recalls_incl = []
    f1s_incl = []

    for class_label in all_classes:
        tp = class_tp[class_label]
        fp = class_fp[class_label]
        fn = class_fn[class_label]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        precisions_incl.append(precision)
        recalls_incl.append(recall)
        f1s_incl.append(f1)

    precision_macro_incl = sum(precisions_incl) / len(precisions_incl) if precisions_incl else 0.0
    recall_macro_incl = sum(recalls_incl) / len(recalls_incl) if recalls_incl else 0.0
    f1_macro_incl = sum(f1s_incl) / len(f1s_incl) if f1s_incl else 0.0

    # Macro-averaged precision, recall, F1 (excluding empty class)
    non_empty_classes = [c for c in all_classes if c != ""]

    precisions_excl = []
    recalls_excl = []
    f1s_excl = []

    for class_label in non_empty_classes:
        tp = class_tp[class_label]
        fp = class_fp[class_label]
        fn = class_fn[class_label]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        precisions_excl.append(precision)
        recalls_excl.append(recall)
        f1s_excl.append(f1)

    precision_macro_excl = sum(precisions_excl) / len(precisions_excl) if precisions_excl else 0.0
    recall_macro_excl = sum(recalls_excl) / len(recalls_excl) if recalls_excl else 0.0
    f1_macro_excl = sum(f1s_excl) / len(f1s_excl) if f1s_excl else 0.0

    # Overall accuracy
    accuracy_incl_empty = (correct_filled + empty_empty) / total_cells if total_cells > 0 else 0.0

    # Accuracy excluding empty-empty matches
    non_empty_total = total_cells - empty_empty
    accuracy_excl_empty = correct_filled / non_empty_total if non_empty_total > 0 else 0.0

    # Error categorization totals
    total_errors = len(misclassifications)

    error_categorization = ErrorCategorization(
        total_errors=total_errors,
        whitespace_only=whitespace_only_errors,
        case_only=case_only_errors,
        whitespace_and_case=whitespace_and_case_errors,
        genuine=genuine_errors,
        whitespace_only_fraction=whitespace_only_errors / total_errors if total_errors > 0 else 0.0,
        case_only_fraction=case_only_errors / total_errors if total_errors > 0 else 0.0,
        whitespace_and_case_fraction=whitespace_and_case_errors / total_errors if total_errors > 0 else 0.0,
        genuine_fraction=genuine_errors / total_errors if total_errors > 0 else 0.0,
    )

    return ColumnValueMetrics(
        column_name=column_name,
        source_column_name=source_column_name,
        total_cells=total_cells,
        accuracy_incl_empty=accuracy_incl_empty,
        precision_macro_incl_empty=precision_macro_incl,
        recall_macro_incl_empty=recall_macro_incl,
        f1_macro_incl_empty=f1_macro_incl,
        accuracy_excl_empty=accuracy_excl_empty,
        precision_macro_excl_empty=precision_macro_excl,
        recall_macro_excl_empty=recall_macro_excl,
        f1_macro_excl_empty=f1_macro_excl,
        hallucination_count=hallucination,
        hallucination_rate=hallucination / total_cells if total_cells > 0 else 0.0,
        omission_count=omission,
        omission_rate=omission / total_cells if total_cells > 0 else 0.0,
        empty_empty_count=empty_empty,
        error_categorization=error_categorization,
        confusion_matrix=confusion_matrix,
        misclassifications=misclassifications,
    )


def calculate_all_metrics(
    gold_standard_csv: Path,
    llm_output_csv: Path,
    gold_column_mapping: dict[str, str],
    llm_column_mapping: dict[str, str | None] | None = None,
    gold_value_mapping: dict | None = None,
    acceptable_columns: dict[str, list[str]] | None = None,
    index_column: str | None = None,
    numeric_tolerance: float | None = None,
    trace_json: dict | None = None,
    value_mapping_file_found: bool = False,
) -> MetricsResult:
    """
    Calculate all metrics for a metadata harmonization experiment.

    Args:
        gold_standard_csv: Path to gold standard harmonized CSV
        llm_output_csv: Path to LLM-produced harmonized CSV
        gold_column_mapping: Gold standard column mapping
        llm_column_mapping: LLM-produced column mapping (None = fallback mode)
        gold_value_mapping: Gold standard value mapping (for reference/logging)
        acceptable_columns: Acceptable alternative column mappings
        index_column: Optional index column name for row alignment verification
        numeric_tolerance: Optional tolerance for numeric comparisons
        trace_json: Optional trace.json data for extracting metadata

    Returns:
        MetricsResult with all calculated metrics
    """
    logger.info(f"Loading gold standard CSV: {gold_standard_csv}")
    gold_df = pd.read_csv(gold_standard_csv)

    logger.info(f"Loading LLM output CSV: {llm_output_csv}")
    llm_df = pd.read_csv(llm_output_csv)

    logger.info(f"Gold standard shape: {gold_df.shape}")
    logger.info(f"LLM output shape: {llm_df.shape}")

    # Align rows by index column if provided
    index_aligned = False
    if index_column:
        if index_column not in gold_df.columns:
            logger.warning(f"Index column '{index_column}' not found in gold standard CSV")
        elif index_column not in llm_df.columns:
            logger.warning(f"Index column '{index_column}' not found in LLM output CSV")
        else:
            logger.info(f"Aligning rows using index column: {index_column}")

            gold_df = gold_df.set_index(index_column)
            llm_df = llm_df.set_index(index_column)

            # Find common indices
            common_idx = gold_df.index.intersection(llm_df.index)

            if len(common_idx) < len(gold_df):
                logger.warning(
                    f"Only {len(common_idx)} of {len(gold_df)} gold standard rows "
                    f"found in LLM output (by index column '{index_column}')"
                )
            if len(common_idx) < len(llm_df):
                logger.warning(
                    f"LLM output has {len(llm_df) - len(common_idx)} extra rows "
                    f"not in gold standard"
                )

            gold_df = gold_df.loc[common_idx].sort_index().reset_index()
            llm_df = llm_df.loc[common_idx].sort_index().reset_index()

            logger.info(f"Aligned {len(common_idx)} rows by index column '{index_column}'")
            index_aligned = True

    # Fallback mode if no LLM column mapping provided
    column_mapping_file_found = llm_column_mapping is not None

    if llm_column_mapping is None:
        logger.warning("=" * 80)
        logger.warning("NO LLM COLUMN MAPPING PROVIDED - USING FALLBACK MODE")
        logger.warning("Will attempt to match gold standard columns directly in LLM output")
        logger.warning("=" * 80)

        # Create a fallback mapping by matching column names
        llm_column_mapping = {}
        for source_col, target_col in gold_column_mapping.items():
            if target_col in llm_df.columns:
                llm_column_mapping[source_col] = target_col
            else:
                llm_column_mapping[source_col] = None

    # Calculate column mapping metrics
    logger.info("Calculating column mapping metrics...")
    column_mapping_metrics = calculate_column_mapping_metrics(
        llm_column_mapping=llm_column_mapping,
        gold_column_mapping=gold_column_mapping,
        acceptable_columns=acceptable_columns,
    )

    logger.info(f"Column mapping accuracy: {column_mapping_metrics.accuracy:.2%}")
    logger.info(f"  Correct: {column_mapping_metrics.correct}/{column_mapping_metrics.total_expected}")
    logger.info(f"  Wrong: {column_mapping_metrics.wrong}")
    logger.info(f"  Missing: {column_mapping_metrics.missing}")
    logger.info(f"  Explicitly null: {column_mapping_metrics.explicitly_null}")

    # Calculate per-column value metrics
    logger.info("Calculating per-column value metrics...")
    column_value_metrics = {}

    for source_col, gold_target in gold_column_mapping.items():
        llm_target = llm_column_mapping.get(source_col)

        # Skip if column not in gold standard (shouldn't happen, but be safe)
        if gold_target not in gold_df.columns:
            logger.warning(f"Gold target column '{gold_target}' not found in gold standard CSV")
            continue

        # Get LLM column (even if mapping is wrong, we can still evaluate values)
        llm_col = None
        if llm_target and llm_target in llm_df.columns:
            llm_col = llm_target
        elif llm_target is None and gold_target in llm_df.columns:
            # Fallback: if mapping missing, try gold column name directly
            llm_col = gold_target

        if llm_col is None:
            logger.warning(f"Cannot evaluate values for '{source_col}': no corresponding LLM column found")
            continue

        logger.info(f"  Evaluating column: {source_col} -> {gold_target} (LLM: {llm_col})")

        gold_values = gold_df[gold_target].tolist()
        llm_values = llm_df[llm_col].tolist()

        # Ensure same length (truncate if needed, only when not index-aligned)
        if not index_aligned and len(gold_values) != len(llm_values):
            min_len = min(len(gold_values), len(llm_values))
            logger.warning(
                f"    Length mismatch: gold={len(gold_values)}, llm={len(llm_values)}, "
                f"using first {min_len} rows"
            )
            gold_values = gold_values[:min_len]
            llm_values = llm_values[:min_len]

        metrics = calculate_column_value_metrics(
            gold_values=gold_values,
            llm_values=llm_values,
            column_name=gold_target,
            source_column_name=source_col,
            numeric_tolerance=numeric_tolerance,
        )

        column_value_metrics[gold_target] = metrics

        logger.info(f"    Accuracy (incl empty): {metrics.accuracy_incl_empty:.2%}")
        logger.info(f"    Accuracy (excl empty): {metrics.accuracy_excl_empty:.2%}")
        logger.info(f"    Hallucinations: {metrics.hallucination_count}")
        logger.info(f"    Omissions: {metrics.omission_count}")

    # Detect extra columns
    gold_target_columns = set(gold_column_mapping.values())
    llm_columns = set(llm_df.columns)

    # Exclude index column from extra columns
    if index_column:
        llm_columns.discard(index_column)

    extra_columns = sorted(llm_columns - gold_target_columns)

    logger.info(f"Extra columns in LLM output: {len(extra_columns)}")
    if extra_columns:
        logger.info(f"  {extra_columns}")

    # Calculate overall summary
    if column_value_metrics:
        avg_accuracy_incl = sum(m.accuracy_incl_empty for m in column_value_metrics.values()) / len(column_value_metrics)
        avg_accuracy_excl = sum(m.accuracy_excl_empty for m in column_value_metrics.values()) / len(column_value_metrics)
        avg_precision_incl = sum(m.precision_macro_incl_empty for m in column_value_metrics.values()) / len(column_value_metrics)
        avg_precision_excl = sum(m.precision_macro_excl_empty for m in column_value_metrics.values()) / len(column_value_metrics)
        avg_recall_incl = sum(m.recall_macro_incl_empty for m in column_value_metrics.values()) / len(column_value_metrics)
        avg_recall_excl = sum(m.recall_macro_excl_empty for m in column_value_metrics.values()) / len(column_value_metrics)
        avg_f1_incl = sum(m.f1_macro_incl_empty for m in column_value_metrics.values()) / len(column_value_metrics)
        avg_f1_excl = sum(m.f1_macro_excl_empty for m in column_value_metrics.values()) / len(column_value_metrics)

        total_hallucinations = sum(m.hallucination_count for m in column_value_metrics.values())
        total_omissions = sum(m.omission_count for m in column_value_metrics.values())
        avg_hallucination_rate = sum(m.hallucination_rate for m in column_value_metrics.values()) / len(column_value_metrics)
        avg_omission_rate = sum(m.omission_rate for m in column_value_metrics.values()) / len(column_value_metrics)

        total_errors = sum(m.error_categorization.total_errors for m in column_value_metrics.values())
        total_whitespace_only = sum(m.error_categorization.whitespace_only for m in column_value_metrics.values())
        total_case_only = sum(m.error_categorization.case_only for m in column_value_metrics.values())
        total_whitespace_and_case = sum(m.error_categorization.whitespace_and_case for m in column_value_metrics.values())
        total_genuine = sum(m.error_categorization.genuine for m in column_value_metrics.values())
    else:
        avg_accuracy_incl = avg_accuracy_excl = 0.0
        avg_precision_incl = avg_precision_excl = 0.0
        avg_recall_incl = avg_recall_excl = 0.0
        avg_f1_incl = avg_f1_excl = 0.0
        total_hallucinations = total_omissions = 0
        avg_hallucination_rate = avg_omission_rate = 0.0
        total_errors = total_whitespace_only = total_case_only = 0
        total_whitespace_and_case = total_genuine = 0

    overall_summary = OverallSummary(
        total_columns=len(column_value_metrics),
        avg_accuracy_incl_empty=avg_accuracy_incl,
        avg_accuracy_excl_empty=avg_accuracy_excl,
        avg_precision_incl_empty=avg_precision_incl,
        avg_precision_excl_empty=avg_precision_excl,
        avg_recall_incl_empty=avg_recall_incl,
        avg_recall_excl_empty=avg_recall_excl,
        avg_f1_incl_empty=avg_f1_incl,
        avg_f1_excl_empty=avg_f1_excl,
        total_hallucinations=total_hallucinations,
        total_omissions=total_omissions,
        avg_hallucination_rate=avg_hallucination_rate,
        avg_omission_rate=avg_omission_rate,
        total_errors=total_errors,
        total_whitespace_only=total_whitespace_only,
        total_case_only=total_case_only,
        total_whitespace_and_case=total_whitespace_and_case,
        total_genuine=total_genuine,
    )

    # Extract metadata from trace.json if available
    llm_provider = None
    llm_model = None
    timing_seconds = None
    experiment_name = llm_output_csv.parent.name

    if trace_json:
        # Try to extract provider/model info from trace
        # The structure may vary, so handle gracefully
        try:
            if "config" in trace_json:
                config = trace_json["config"]
                llm_provider = config.get("provider")
                llm_model = config.get("model")

            # Try to extract timing
            if "timing" in trace_json:
                timing_seconds = trace_json["timing"].get("total_seconds")
        except Exception as e:
            logger.warning(f"Failed to extract metadata from trace.json: {e}")

    # Create final result
    metadata = ExperimentMetadata(
        experiment_name=experiment_name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        llm_provider=llm_provider,
        llm_model=llm_model,
        timing_seconds=timing_seconds,
    )

    result = MetricsResult(
        metadata=metadata,
        column_mapping=column_mapping_metrics,
        column_values=column_value_metrics,
        extra_columns_count=len(extra_columns),
        extra_columns=extra_columns,
        overall_summary=overall_summary,
        gold_standard_file=str(gold_standard_csv),
        llm_output_file=str(llm_output_csv),
        column_mapping_file_found=column_mapping_file_found,
        value_mapping_file_found=value_mapping_file_found,
    )

    logger.info("✓ Metrics calculation complete")

    return result
