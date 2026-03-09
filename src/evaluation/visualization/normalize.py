from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .enrich import infer_context, infer_model_family, infer_model_label, merge_labels
from .io import extract_run_id

RUN_METRICS = {
    "column_mapping_accuracy": ("column_mapping", "accuracy"),
    "column_mapping_precision_excl_null": ("column_mapping", "precision_excl_null"),
    "column_mapping_recall": ("column_mapping", "recall"),
    "avg_value_accuracy_excl_empty": ("overall_summary", "avg_accuracy_excl_empty"),
    "avg_value_accuracy_incl_empty": ("overall_summary", "avg_accuracy_incl_empty"),
    "avg_value_f1_excl_empty": ("overall_summary", "avg_f1_excl_empty"),
    "avg_value_f1_incl_empty": ("overall_summary", "avg_f1_incl_empty"),
    "avg_hallucination_rate": ("overall_summary", "avg_hallucination_rate"),
    "avg_omission_rate": ("overall_summary", "avg_omission_rate"),
}

COLUMN_VALUE_FIELDS = [
    "accuracy_incl_empty",
    "precision_macro_incl_empty",
    "recall_macro_incl_empty",
    "f1_macro_incl_empty",
    "accuracy_excl_empty",
    "precision_macro_excl_empty",
    "recall_macro_excl_empty",
    "f1_macro_excl_empty",
    "hallucination_rate",
    "omission_rate",
    "hallucination_count",
    "omission_count",
    "empty_empty_count",
]


def _safe_nested(data: dict[str, Any], a: str, b: str, default=None):
    return data.get(a, {}).get(b, default)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _find_experiment_id_file(metrics_path: Path, run_id: str) -> Path | None:
    # New location: .runtime/.experiment_id
    new_path = metrics_path.parent / ".runtime" / ".experiment_id"
    if new_path.exists():
        return new_path
    # Old location: .experiment_id directly in results dir
    direct = metrics_path.parent / ".experiment_id"
    if direct.exists():
        return direct
    results_root = metrics_path.parent.parent
    for candidate in sorted(results_root.glob(f"*_{run_id}/.runtime/.experiment_id")):
        if candidate.exists():
            return candidate
    for candidate in sorted(results_root.glob(f"*_{run_id}/.experiment_id")):
        if candidate.exists():
            return candidate
    return None


def _load_json_file(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _config_abs_path(config_path: str | None) -> Path | None:
    if not config_path:
        return None
    root = _project_root()
    p = Path(config_path)
    abs_path = p if p.is_absolute() else (root / p)
    return abs_path if abs_path.exists() else None


def _extract_model_metadata(config_abs_path: Path | None, exp_id: dict[str, Any]) -> dict[str, Any]:
    """Extract model_metadata fields from config YAML or .experiment_id."""
    fields = {
        "pricing_prompt_per_million_tokens": None,
        "pricing_completion_per_million_tokens": None,
        "parameter_count_b": None,
        "model_family_group": None,
        "supports_tools": None,
        "model_metadata_context_length": None,
        "model_metadata_source": None,
    }
    # Try config YAML first
    if config_abs_path:
        try:
            cfg = yaml.safe_load(config_abs_path.read_text()) or {}
            mm = cfg.get("model_metadata", {}) or {}
            if mm:
                fields["pricing_prompt_per_million_tokens"] = mm.get("pricing_prompt_per_million_tokens")
                fields["pricing_completion_per_million_tokens"] = mm.get("pricing_completion_per_million_tokens")
                fields["parameter_count_b"] = mm.get("parameter_count_b")
                fields["model_family_group"] = mm.get("model_family_group")
                fields["supports_tools"] = mm.get("supports_tools")
                fields["model_metadata_context_length"] = mm.get("context_length")
                fields["model_metadata_source"] = mm.get("source")
                return fields
        except Exception:
            pass
    # Fallback: check .experiment_id for enriched metadata
    mm = exp_id.get("model_metadata", {}) or {}
    if mm:
        fields["pricing_prompt_per_million_tokens"] = mm.get("pricing_prompt_per_million_tokens")
        fields["pricing_completion_per_million_tokens"] = mm.get("pricing_completion_per_million_tokens")
        fields["parameter_count_b"] = mm.get("parameter_count_b")
        fields["model_family_group"] = mm.get("model_family_group")
        fields["supports_tools"] = mm.get("supports_tools")
        fields["model_metadata_context_length"] = mm.get("context_length")
        fields["model_metadata_source"] = mm.get("source")
    return fields


def _extract_prompt_fields(config_abs_path: Path | None) -> dict[str, Any]:
    fields = {
        "config_path": str(config_abs_path) if config_abs_path else None,
        "prompts_base_dir": None,
        "system_prompt_dir": None,
        "react_prelude": None,
        "code_context_prompt": None,
        "codeact_prompt": None,
        "codeact_summary_template": None,
        "tool_prompts_dir": None,
    }
    if not config_abs_path:
        return fields
    try:
        cfg = yaml.safe_load(config_abs_path.read_text()) or {}
        prompts = cfg.get("prompts", {}) or {}
        for key in [
            "prompts_base_dir",
            "system_prompt_dir",
            "react_prelude",
            "code_context_prompt",
            "codeact_prompt",
            "codeact_summary_template",
            "tool_prompts_dir",
        ]:
            fields[key] = prompts.get(key)
    except Exception:
        pass
    return fields


def _find_prompt_composition_file(metrics_path: Path, experiment_id_file: Path | None) -> Path | None:
    direct = metrics_path.parent / "full_prompt_composition.json"
    if direct.exists():
        return direct
    if experiment_id_file:
        alt = experiment_id_file.parent / "full_prompt_composition.json"
        if alt.exists():
            return alt
    return None


def _extract_prompt_composition_fields(prompt_file: Path | None) -> dict[str, Any]:
    out = {
        "full_prompt_composition_file": str(prompt_file) if prompt_file else None,
        "prompt_hash_system_message": None,
        "prompt_hash_auto_context": None,
        "uses_custom_prompts": None,
        "has_custom_prelude": None,
    }
    data = _load_json_file(prompt_file)
    if not data:
        return out
    out["prompt_hash_system_message"] = data.get("layers", {}).get("system_message", {}).get("content_hash")
    out["prompt_hash_auto_context"] = data.get("layers", {}).get("auto_context_message", {}).get("content_hash")
    out["uses_custom_prompts"] = data.get("summary", {}).get("uses_custom_prompts")
    out["has_custom_prelude"] = data.get("summary", {}).get("has_custom_prelude")
    return out


def _run_row(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    md = data.get("metadata", {})
    run_id = extract_run_id(path, data)

    exp_id_file = _find_experiment_id_file(path, run_id)
    exp_id = _load_json_file(exp_id_file)

    experiment_name = exp_id.get("experiment_name") or md.get("experiment_name") or path.parent.name
    llm_provider = exp_id.get("llm_provider") or md.get("llm_provider")
    llm_model = exp_id.get("llm_model") or md.get("llm_model")
    model_label = infer_model_label(experiment_name, llm_model)
    context = infer_context(experiment_name)

    config_abs = _config_abs_path(exp_id.get("config_path"))
    prompt_file = _find_prompt_composition_file(path, exp_id_file)

    row = {
        "run_id": run_id,
        "metrics_file": str(path),
        "results_dir": str(path.parent),
        "experiment_name": experiment_name,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "model_label": model_label,
        "context": context,
        "model_family": infer_model_family(llm_provider, model_label),
        "timing_seconds": md.get("timing_seconds"),
        "extra_columns_count": data.get("extra_columns_count", 0),
        "slurm_job_id": exp_id.get("slurm_job_id"),
        "timestamp_utc": exp_id.get("timestamp_utc"),
        "hostname": exp_id.get("hostname"),
        "beaker_port": exp_id.get("beaker_port"),
        "mode": exp_id.get("mode"),
        "log_stdout": exp_id.get("log_files", {}).get("stdout"),
        "log_stderr": exp_id.get("log_files", {}).get("stderr"),
        "bdikit_llm_instance_matching": exp_id.get("bdikit_llm_instance_matching"),
        "bdikit_llm_schema_matching": exp_id.get("bdikit_llm_schema_matching"),
    }
    for out_key, (k1, k2) in RUN_METRICS.items():
        row[out_key] = _safe_nested(data, k1, k2)
    row["display_label"] = f"{row['model_label']} | {row['context']}"

    row.update(_extract_model_metadata(config_abs, exp_id))
    row.update(_extract_prompt_fields(config_abs))
    row.update(_extract_prompt_composition_fields(prompt_file))

    # Derived columns for visualization grouping
    pricing = row.get("pricing_prompt_per_million_tokens")
    provider_lower = (llm_provider or "").lower()
    row["is_local"] = "ollama" in provider_lower or (pricing is not None and pricing == 0.0)
    # Cost tier derivation
    if pricing is None:
        row["cost_tier"] = "unknown"
    elif pricing == 0.0:
        row["cost_tier"] = "free"
    elif pricing < 0.5:
        row["cost_tier"] = "cheap"
    elif pricing < 5.0:
        row["cost_tier"] = "moderate"
    else:
        row["cost_tier"] = "expensive"

    return row


def build_tables(bundle: list[tuple[Path, dict[str, Any]]], labels_df: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    runs, mapping_rows, column_rows, confusion_rows = [], [], [], []

    for path, data in bundle:
        run = _run_row(path, data)
        run_id = run["run_id"]
        runs.append(run)

        for detail in data.get("column_mapping", {}).get("details", []):
            mapping_rows.append(
                {
                    "run_id": run_id,
                    "experiment_name": run["experiment_name"],
                    "model_label": run["model_label"],
                    "context": run["context"],
                    "source_column": detail.get("source_column"),
                    "expected_target": detail.get("expected_target"),
                    "actual_target": detail.get("actual_target"),
                    "is_correct": detail.get("is_correct", False),
                    "is_acceptable": detail.get("is_acceptable", False),
                    "is_missing": detail.get("is_missing", False),
                    "is_explicitly_null": detail.get("is_explicitly_null", False),
                    "is_wrong": detail.get("is_wrong", False),
                }
            )

        for col_name, payload in data.get("column_values", {}).items():
            entry = {
                "run_id": run_id,
                "experiment_name": run["experiment_name"],
                "model_label": run["model_label"],
                "context": run["context"],
                "column_name": col_name,
                "source_column_name": payload.get("source_column_name"),
            }
            for key in COLUMN_VALUE_FIELDS:
                entry[key] = payload.get(key)
            errors = payload.get("error_categorization", {})
            entry["error_total"] = errors.get("total_errors")
            entry["error_whitespace_only"] = errors.get("whitespace_only")
            entry["error_case_only"] = errors.get("case_only")
            entry["error_whitespace_and_case"] = errors.get("whitespace_and_case")
            entry["error_genuine"] = errors.get("genuine")
            column_rows.append(entry)

            for expected, preds in (payload.get("confusion_matrix") or {}).items():
                for predicted, count in (preds or {}).items():
                    confusion_rows.append(
                        {
                            "run_id": run_id,
                            "column_name": col_name,
                            "expected_value": expected,
                            "predicted_value": predicted,
                            "count": count,
                        }
                    )

    runs_df = pd.DataFrame(runs)
    if not runs_df.empty and labels_df is not None and not labels_df.empty:
        runs_df = merge_labels(runs_df, labels_df)

    mapping_df = pd.DataFrame(mapping_rows)
    columns_df = pd.DataFrame(column_rows)
    confusion_df = pd.DataFrame(confusion_rows)

    merge_cols = ["run_id", "display_label", "model_family"]
    for extra in ["model_family_group", "cost_tier", "is_local"]:
        if extra in runs_df.columns:
            merge_cols.append(extra)

    if not runs_df.empty and not columns_df.empty:
        columns_df = columns_df.merge(
            runs_df[merge_cols],
            on="run_id",
            how="left",
        )
    if not runs_df.empty and not mapping_df.empty:
        mapping_df = mapping_df.merge(
            runs_df[merge_cols],
            on="run_id",
            how="left",
        )

    tables = {
        "runs": runs_df,
        "column_mapping": mapping_df,
        "column_values": columns_df,
        "confusion": confusion_df,
    }

    # Add row_values if any row_values.csv files exist
    if not runs_df.empty:
        row_values_df = build_row_values_table(runs_df)
        if not row_values_df.empty:
            tables["row_values"] = row_values_df

    return tables


def build_row_values_table(runs_df: pd.DataFrame) -> pd.DataFrame:
    """Discover and concatenate row_values.csv files from each run's results_dir.

    Merges in run metadata (model_label, context, display_label).

    Returns long-format DataFrame with columns:
        run_id, model_label, context, display_label, column_name,
        source_column_name, row_index, gold_value, predicted_value,
        classification, error_type
    """
    frames = []
    for _, run in runs_df.iterrows():
        results_dir = run.get("results_dir")
        if not results_dir:
            continue
        rv_path = Path(results_dir) / "row_values.csv"
        if not rv_path.exists():
            continue
        df = pd.read_csv(rv_path, dtype=str)
        df["run_id"] = run["run_id"]
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    row_values = pd.concat(frames, ignore_index=True)

    # Merge run metadata
    merge_cols = ["run_id", "model_label", "context", "display_label"]
    merge_cols = [c for c in merge_cols if c in runs_df.columns]
    row_values = row_values.merge(
        runs_df[merge_cols],
        on="run_id",
        how="left",
    )
    return row_values
