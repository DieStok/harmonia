from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


MODEL_TOKEN_PATTERN = re.compile(
    r"(gemini-3-flash-preview|claude-sonnet-4\.6|minimax-m2\.5|deepseek-v3\.2|kimi-k2\.5|qwen3-coder|devstral(?:-small)?)",
    re.IGNORECASE,
)


def infer_context(experiment_name: str) -> str:
    name = experiment_name.lower()
    if "codeact" in name:
        return "codeact_context"
    if "bdikit" in name:
        return "bdikit_context"
    if "code_context" in name or "code-context" in name:
        return "code_context"
    return "unknown"


def infer_model_label(experiment_name: str, llm_model: str | None) -> str:
    if llm_model:
        return llm_model
    m = MODEL_TOKEN_PATTERN.search(experiment_name)
    return m.group(1).lower() if m else "unknown"


def infer_model_family(provider: str | None, model_label: str) -> str:
    p = (provider or "").lower()
    m = (model_label or "").lower()
    if "ollama" in p or m.startswith("ollama/"):
        return "local"
    if any(x in p for x in ["openrouter", "openai", "anthropic", "groq", "gemini", "together", "cohere"]):
        return "frontier"
    if any(x in m for x in ["gemini", "claude", "openrouter/"]):
        return "frontier"
    return "unknown"


def load_labels_file(labels_file: str | None) -> pd.DataFrame:
    if not labels_file:
        return pd.DataFrame()
    path = Path(labels_file)
    if not path.exists():
        raise FileNotFoundError(f"labels file not found: {labels_file}")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data = [{"run_id": k, **v} for k, v in data.items()]
        return pd.DataFrame(data)
    return pd.read_csv(path)


def merge_labels(runs_df: pd.DataFrame, labels_df: pd.DataFrame) -> pd.DataFrame:
    if runs_df.empty or labels_df.empty:
        return runs_df
    merged = runs_df.copy()
    if "run_id" in labels_df.columns:
        merged = merged.merge(labels_df, on="run_id", how="left", suffixes=("", "_label"))
    elif "experiment_name" in labels_df.columns:
        merged = merged.merge(labels_df, on="experiment_name", how="left", suffixes=("", "_label"))
    return merged
