"""Bridge between the log/trace analysis CLI JSON output and visualization tables.

Loads an AnalysisReport JSON (produced by
``read_and_analyze_logs_and_traces_cli.py --json``) and merges it with
metrics tables from ``build_tables()`` to produce a unified DataFrame
that includes both successful and failed runs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from evaluation.visualization.enrich import infer_context, infer_model_label

logger = logging.getLogger(__name__)

# Severity ranking for picking the primary failure reason from a problems list.
_SEVERITY_RANK = {"critical": 0, "error": 1, "warning": 2, "info": 3}


def load_analysis_report(path: str | Path) -> dict:
    """Load and minimally validate an AnalysisReport JSON file.

    Returns the raw dict so callers are not forced to import the CLI's
    Pydantic models.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Analysis report not found: {path}")

    data = json.loads(path.read_text())

    if "runs" not in data:
        raise ValueError(f"Analysis report missing 'runs' key: {path}")
    if not isinstance(data["runs"], list):
        raise ValueError(f"'runs' must be a list in analysis report: {path}")

    return data


def _primary_failure_reason(problems: list[dict]) -> str:
    """Pick a single human-readable failure reason from a problems list.

    Returns the name of the most severe problem, or "Unknown" if empty.
    """
    if not problems:
        return "Unknown"

    # Sort by severity (most severe first), then by order of appearance.
    ranked = sorted(
        problems,
        key=lambda p: _SEVERITY_RANK.get(p.get("severity", "info"), 99),
    )
    return ranked[0].get("name", ranked[0].get("problem_id", "Unknown"))


def build_all_runs_table(
    analysis_report: dict,
    metrics_tables: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Merge failed runs from analysis report with successful runs from metrics.

    Parameters
    ----------
    analysis_report
        Dict loaded via :func:`load_analysis_report`.
    metrics_tables
        Optional dict returned by ``build_tables()``.  If provided the
        ``runs`` table is used to enrich successful-run rows with accuracy
        metrics.

    Returns
    -------
    pd.DataFrame
        One row per run with columns:
        ``run_id, experiment_name, model, context, has_output,
        failure_reason, column_mapping_accuracy, avg_value_accuracy, ...``
    """
    rows: list[dict] = []

    for run in analysis_report.get("runs", []):
        run_id = run.get("run_id")
        experiment_name = run.get("experiment_name", "")
        model = infer_model_label(experiment_name, run.get("llm_model"))
        context = infer_context(experiment_name)
        has_metrics = run.get("has_metrics", False)
        problems = run.get("problems", [])

        # Determine output status: has_metrics means it produced evaluable output
        has_output = has_metrics

        failure_reason = None
        if not has_output and problems:
            failure_reason = _primary_failure_reason(problems)
        elif not has_output:
            failure_reason = "Unknown"

        rows.append({
            "run_id": run_id,
            "experiment_name": experiment_name,
            "model": model,
            "context": context,
            "has_output": has_output,
            "failure_reason": failure_reason,
            "llm_provider": run.get("llm_provider"),
            "llm_model": run.get("llm_model"),
            "total_turns": run.get("total_turns", 0),
            "total_duration_seconds": run.get("total_duration_seconds"),
            "num_problems": len(problems),
        })

    all_runs = pd.DataFrame(rows)
    if all_runs.empty:
        return all_runs

    # Merge accuracy metrics from metrics_tables if available
    if metrics_tables is not None:
        metrics_runs = metrics_tables.get("runs", pd.DataFrame())
        if not metrics_runs.empty and "run_id" in metrics_runs.columns:
            metric_cols = [
                c for c in metrics_runs.columns
                if c not in all_runs.columns or c == "run_id"
            ]
            if metric_cols:
                all_runs = all_runs.merge(
                    metrics_runs[metric_cols],
                    on="run_id",
                    how="left",
                    suffixes=("", "_metrics"),
                )

    # Add display label
    all_runs["display_label"] = all_runs["model"] + " | " + all_runs["context"]

    return all_runs
