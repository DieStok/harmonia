"""
Evaluation module for metadata harmonization metrics calculation.

This module provides tools for evaluating LLM metadata harmonization experiments
by comparing their output against gold-standard data.
"""

from .schemas import (
    MetricsResult,
    ExperimentMetadata,
    ColumnMappingMetrics,
    ColumnMappingDetail,
    ColumnValueMetrics,
    ErrorCategorization,
    Misclassification,
    OverallSummary,
)

__all__ = [
    "MetricsResult",
    "ExperimentMetadata",
    "ColumnMappingMetrics",
    "ColumnMappingDetail",
    "ColumnValueMetrics",
    "ErrorCategorization",
    "Misclassification",
    "OverallSummary",
]
