"""
Pydantic schemas for metadata harmonization metrics output.

Defines the structure of metrics.json that is produced by the evaluation pipeline.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Misclassification(BaseModel):
    """A single misclassified value."""
    row_index: int = Field(..., description="Row number (0-indexed) where the error occurred")
    expected: str = Field(..., description="Expected (gold standard) value")
    actual: str = Field(..., description="Actual (LLM-produced) value")
    error_type: str = Field(..., description="Type of error: whitespace_only, case_only, whitespace_and_case, or genuine")


class RowComparison(BaseModel):
    """Per-row comparison result for a single cell."""
    row_index: int = Field(..., description="Row number (0-indexed)")
    gold_value: str = Field(..., description="Normalized gold standard value (stripped, empty→'')")
    predicted_value: str = Field(..., description="Normalized LLM-predicted value (stripped, empty→'')")
    classification: str = Field(..., description="One of: correct, empty_empty, hallucination, omission, error")
    error_type: Optional[str] = Field(None, description="Error subtype if classification=='error': whitespace_only, case_only, whitespace_and_case, genuine")


class ErrorCategorization(BaseModel):
    """Breakdown of errors by type."""
    total_errors: int = Field(..., description="Total number of misclassified values")

    # Counts
    whitespace_only: int = Field(..., description="Errors that disappear after strip()")
    case_only: int = Field(..., description="Errors that disappear after lower()")
    whitespace_and_case: int = Field(..., description="Errors that disappear after strip().lower()")
    genuine: int = Field(..., description="Errors that remain after normalization")

    # Fractions
    whitespace_only_fraction: float = Field(..., description="Fraction of errors that are whitespace-only")
    case_only_fraction: float = Field(..., description="Fraction of errors that are case-only")
    whitespace_and_case_fraction: float = Field(..., description="Fraction of errors that are whitespace and case")
    genuine_fraction: float = Field(..., description="Fraction of errors that are genuine")


class ColumnValueMetrics(BaseModel):
    """Metrics for value harmonization quality in a single column."""
    column_name: str = Field(..., description="Gold standard column name")
    source_column_name: str = Field(..., description="Original source column name")
    total_cells: int = Field(..., description="Total number of cells evaluated")

    # Accuracy metrics (with empty-empty counted as correct)
    accuracy_incl_empty: float = Field(..., description="Accuracy including empty-empty matches")
    precision_macro_incl_empty: float = Field(..., description="Macro-averaged precision including empty-empty")
    recall_macro_incl_empty: float = Field(..., description="Macro-averaged recall including empty-empty")
    f1_macro_incl_empty: float = Field(..., description="Macro-averaged F1 score including empty-empty")

    # Accuracy metrics (without empty-empty)
    accuracy_excl_empty: float = Field(..., description="Accuracy excluding empty-empty matches")
    precision_macro_excl_empty: float = Field(..., description="Macro-averaged precision excluding empty-empty")
    recall_macro_excl_empty: float = Field(..., description="Macro-averaged recall excluding empty-empty")
    f1_macro_excl_empty: float = Field(..., description="Macro-averaged F1 score excluding empty-empty")

    # Completeness metrics
    hallucination_count: int = Field(..., description="Number of hallucinations (gold empty, LLM filled)")
    hallucination_rate: float = Field(..., description="Hallucination rate as fraction of total cells")
    omission_count: int = Field(..., description="Number of omissions (gold filled, LLM empty)")
    omission_rate: float = Field(..., description="Omission rate as fraction of total cells")
    empty_empty_count: int = Field(..., description="Number of cells where both are empty")

    # Error categorization
    error_categorization: ErrorCategorization = Field(..., description="Breakdown of errors by type")

    # Detailed diagnostics
    confusion_matrix: dict[str, dict[str, int]] = Field(
        ...,
        description="Sparse confusion matrix: {expected_value: {predicted_value: count}}"
    )
    misclassifications: list[Misclassification] = Field(
        ...,
        description="List of all misclassified cells with details"
    )
    row_comparisons: list[RowComparison] = Field(
        default_factory=list,
        description="Complete per-row comparison results (all cells, not just errors)"
    )


class ColumnMappingDetail(BaseModel):
    """Details for a single column mapping."""
    source_column: str = Field(..., description="Original source column name")
    expected_target: str = Field(..., description="Expected GDC column name from gold standard")
    actual_target: Optional[str] = Field(None, description="Actual GDC column name from LLM (null if missing)")
    is_correct: bool = Field(..., description="Whether the mapping is correct (exact or acceptable match)")
    is_acceptable: bool = Field(..., description="Whether the mapping is an acceptable alternative")
    is_missing: bool = Field(..., description="Whether the column was not mapped at all")
    is_explicitly_null: bool = Field(..., description="Whether the column was explicitly mapped to null")
    is_wrong: bool = Field(..., description="Whether the column was mapped to the wrong target")


class ColumnMappingMetrics(BaseModel):
    """Metrics for schema mapping quality (column name harmonization)."""
    total_expected: int = Field(..., description="Number of columns in gold standard")
    correct: int = Field(..., description="Number of correctly mapped columns (exact or acceptable)")
    wrong: int = Field(..., description="Number of columns mapped to wrong GDC column")
    missing: int = Field(..., description="Number of columns absent from mapping entirely")
    explicitly_null: int = Field(..., description="Number of columns explicitly mapped to null")

    precision_excl_null: float = Field(
        ...,
        description="Precision excluding null mappings: correct / (correct + wrong)"
    )
    precision_incl_null: float = Field(
        ...,
        description="Precision including null mappings: correct / (correct + wrong + explicitly_null)"
    )
    recall: float = Field(..., description="Recall: correct / total_expected")
    accuracy: float = Field(..., description="Accuracy: correct / total_expected")

    details: list[ColumnMappingDetail] = Field(..., description="Per-column mapping details")


class ExperimentMetadata(BaseModel):
    """Metadata about the experiment being evaluated."""
    experiment_name: str = Field(..., description="Name of the experiment")
    timestamp: str = Field(..., description="ISO timestamp of evaluation")
    llm_provider: Optional[str] = Field(None, description="LLM provider (e.g., 'openai', 'anthropic')")
    llm_model: Optional[str] = Field(None, description="LLM model name")
    timing_seconds: Optional[float] = Field(None, description="Experiment duration in seconds")
    pricing_prompt_per_million_tokens: Optional[float] = Field(None, description="Input pricing per million tokens")
    pricing_completion_per_million_tokens: Optional[float] = Field(None, description="Output pricing per million tokens")
    parameter_count_b: Optional[float] = Field(None, description="Model parameter count in billions")
    model_family_group: Optional[str] = Field(None, description="Model family group (Claude, Gemini, etc.)")
    supports_tools: Optional[bool] = Field(None, description="Whether the model supports tool use")


class OverallSummary(BaseModel):
    """Aggregate summary statistics across all columns."""
    total_columns: int = Field(..., description="Total number of columns evaluated")

    # Aggregate value metrics
    avg_accuracy_incl_empty: float = Field(..., description="Average accuracy across columns (incl empty)")
    avg_accuracy_excl_empty: float = Field(..., description="Average accuracy across columns (excl empty)")
    avg_precision_incl_empty: float = Field(..., description="Average precision across columns (incl empty)")
    avg_precision_excl_empty: float = Field(..., description="Average precision across columns (excl empty)")
    avg_recall_incl_empty: float = Field(..., description="Average recall across columns (incl empty)")
    avg_recall_excl_empty: float = Field(..., description="Average recall across columns (excl empty)")
    avg_f1_incl_empty: float = Field(..., description="Average F1 across columns (incl empty)")
    avg_f1_excl_empty: float = Field(..., description="Average F1 across columns (excl empty)")

    # Aggregate completeness
    total_hallucinations: int = Field(..., description="Total hallucinations across all columns")
    total_omissions: int = Field(..., description="Total omissions across all columns")
    avg_hallucination_rate: float = Field(..., description="Average hallucination rate across columns")
    avg_omission_rate: float = Field(..., description="Average omission rate across columns")

    # Aggregate error categorization
    total_errors: int = Field(..., description="Total errors across all columns")
    total_whitespace_only: int = Field(..., description="Total whitespace-only errors")
    total_case_only: int = Field(..., description="Total case-only errors")
    total_whitespace_and_case: int = Field(..., description="Total whitespace and case errors")
    total_genuine: int = Field(..., description="Total genuine errors")


class MetricsResult(BaseModel):
    """Top-level metrics result for a metadata harmonization experiment."""
    schema_version: str = Field(default="1.1", description="Schema version for this metrics format")

    # Experiment metadata
    metadata: ExperimentMetadata = Field(..., description="Experiment metadata")

    # Core metrics
    column_mapping: ColumnMappingMetrics = Field(..., description="Schema mapping metrics")
    column_values: dict[str, ColumnValueMetrics] = Field(
        ...,
        description="Per-column value harmonization metrics"
    )

    # Extra columns (not in gold standard)
    extra_columns_count: int = Field(..., description="Number of extra columns in LLM output")
    extra_columns: list[str] = Field(..., description="Names of extra columns")

    # Overall summary
    overall_summary: OverallSummary = Field(..., description="Aggregate summary statistics")

    # Diagnostic info
    gold_standard_file: str = Field(..., description="Path to gold standard CSV file")
    llm_output_file: str = Field(..., description="Path to LLM output CSV file")
    column_mapping_file_found: bool = Field(..., description="Whether column_mapping.json was found")
    value_mapping_file_found: bool = Field(..., description="Whether value_mapping.json was found")
