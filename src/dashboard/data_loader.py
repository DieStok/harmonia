"""
Data loading for the Dash dashboard.
Dual-source: scans results/ directories AND queries Phoenix.
Outer-joins on run_id so runs are visible even if one source is missing.
"""

import json
import logging
import re
import threading
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from evaluation.visualization.io import (
    RUN_ID_PATTERN,
)

logger = logging.getLogger(__name__)

try:
    from openinference.semconv.trace import SpanAttributes
    _OPENINFERENCE_AVAILABLE = True
except ImportError:
    _OPENINFERENCE_AVAILABLE = False

try:
    import phoenix as px
    _PHOENIX_AVAILABLE = True
except ImportError:
    _PHOENIX_AVAILABLE = False

# Regex to distinguish SLURM job ID (all digits) from timestamp (YYYYMMDD_HHMMSS)
_SLURM_JOB_ID_RE = re.compile(r"^\d+$")
_TIMESTAMP_RE = re.compile(r"^\d{8}_\d{6}$")

# Expected metrics schema version
_EXPECTED_SCHEMA_VERSION = "1.1"


class DashboardDataLoader:
    """Loads experiment data from results directories and optionally Phoenix."""

    def __init__(self, phoenix_endpoint: str, results_base_dir: Path):
        self.phoenix_endpoint = phoenix_endpoint
        self.results_dir = Path(results_base_dir)
        self._phoenix_client = None
        self._phoenix_available = False
        self._cache_lock = threading.Lock()
        self._run_index: dict[str, Path] = {}  # run_id -> canonical results dir
        self._metrics_cache: dict[str, dict] = {}
        self._trace_cache: dict[str, dict] = {}

        self._init_phoenix()
        self._build_run_index()

    def _init_phoenix(self):
        """Try to connect to Phoenix. Set _phoenix_available flag."""
        if not _PHOENIX_AVAILABLE:
            return
        try:
            self._phoenix_client = px.Client(endpoint=self.phoenix_endpoint)
            self._phoenix_client.get_spans_dataframe(limit=1)
            self._phoenix_available = True
        except Exception:
            self._phoenix_available = False
            self._phoenix_client = None

    def _build_run_index(self):
        """
        Scan results/ directory names to build run_id -> directory mapping.
        When a run_id maps to multiple directories, prefer the SLURM-job-ID
        format (shorter middle segment) as canonical.
        """
        if not self.results_dir.is_dir():
            return

        # Collect all candidate dirs per run_id
        candidates: dict[str, list[Path]] = {}
        for d in sorted(self.results_dir.iterdir()):
            if not d.is_dir():
                continue
            m = RUN_ID_PATTERN.search(d.name)
            if m:
                rid = m.group(1)
                candidates.setdefault(rid, []).append(d)

        with self._cache_lock:
            for rid, dirs in candidates.items():
                if len(dirs) == 1:
                    self._run_index[rid] = dirs[0]
                else:
                    # Multiple dirs for same run_id (legacy duplication).
                    # Prefer the one that contains trace.json (the real results).
                    best = dirs[0]
                    for d in dirs:
                        if (d / "trace.json").exists():
                            best = d
                            break
                    self._run_index[rid] = best

    def _parse_dir_metadata(self, run_id: str, d: Path) -> dict:
        """Extract metadata from a results directory without loading large files."""
        meta = {
            "run_id": run_id,
            "results_dir": str(d),
            "has_metrics": (d / "metrics.json").exists(),
            "has_trace": (d / "trace.json").exists(),
            "has_config": (d / "config_snapshot.yaml").exists(),
        }

        # Try to get basic info from trace.json (lightweight: read top-level keys only)
        if meta["has_trace"]:
            try:
                with open(d / "trace.json") as f:
                    trace_data = json.load(f)
                meta["experiment_name"] = trace_data.get("experiment", {}).get("name", "")
                meta["model"] = trace_data.get("llm", {}).get("model", "")
                meta["provider"] = trace_data.get("llm", {}).get("provider", "")
                meta["status"] = trace_data.get("status", "unknown")
                meta["total_turns"] = len(trace_data.get("turns", []))
                meta["total_duration"] = trace_data.get("timing", {}).get("total_duration_seconds", 0)
                timing = trace_data.get("timing", {})
                meta["start_time"] = timing.get("start_time", "")

                # Sum token/cost from turns
                turns = trace_data.get("turns", [])
                meta["total_input_tokens"] = sum(t.get("input_tokens", 0) for t in turns)
                meta["total_output_tokens"] = sum(t.get("output_tokens", 0) for t in turns)
                meta["total_cost_usd"] = sum(t.get("cost_usd", 0) for t in turns)
            except Exception:
                pass

        # Try to get accuracy from metrics.json (small file)
        if meta["has_metrics"]:
            try:
                metrics = self.get_run_metrics(run_id)
                if metrics:
                    meta["accuracy"] = metrics.get("overall_summary", {}).get("avg_accuracy_excl_empty")
                    meta["column_mapping_accuracy"] = metrics.get("column_mapping", {}).get("accuracy")
                    md = metrics.get("metadata", {})
                    # Fill in model/provider from metrics if not from trace
                    if not meta.get("model"):
                        meta["model"] = md.get("llm_model", "")
                    if not meta.get("provider"):
                        meta["provider"] = md.get("llm_provider", "")
                    if not meta.get("experiment_name"):
                        meta["experiment_name"] = md.get("experiment_name", "")
            except Exception:
                pass

        # Fill defaults for missing fields
        meta.setdefault("experiment_name", d.name)
        meta.setdefault("model", "")
        meta.setdefault("provider", "")
        meta.setdefault("status", "unknown")
        meta.setdefault("total_turns", 0)
        meta.setdefault("total_duration", 0)
        meta.setdefault("total_input_tokens", 0)
        meta.setdefault("total_output_tokens", 0)
        meta.setdefault("total_cost_usd", 0)
        meta.setdefault("start_time", "")
        meta.setdefault("accuracy", None)
        meta.setdefault("column_mapping_accuracy", None)

        return meta

    def get_all_runs(self) -> pd.DataFrame:
        """
        Dual-source run discovery.
        Returns DataFrame with run metadata.
        """
        rows = []

        # Source 1: File-based discovery
        with self._cache_lock:
            index_copy = dict(self._run_index)
        for run_id, d in index_copy.items():
            meta = self._parse_dir_metadata(run_id, d)
            meta["has_phoenix_data"] = False
            rows.append(meta)

        # Source 2: Phoenix spans (if available)
        if self._phoenix_available and self._phoenix_client:
            try:
                spans_df = self._phoenix_client.get_spans_dataframe()
                if spans_df is not None and len(spans_df) > 0:
                    # Find root AGENT spans with harmonia.run_id
                    rid_col = "attributes.harmonia.run_id"
                    if rid_col in spans_df.columns:
                        root_spans = spans_df[spans_df[rid_col].notna()].copy()
                        phoenix_run_ids = set(root_spans[rid_col].unique())

                        # Mark existing runs as having Phoenix data
                        existing_ids = {r["run_id"] for r in rows}
                        for row in rows:
                            if row["run_id"] in phoenix_run_ids:
                                row["has_phoenix_data"] = True

                        # Add Phoenix-only runs (no local files)
                        for rid in phoenix_run_ids - existing_ids:
                            span = root_spans[root_spans[rid_col] == rid].iloc[0]
                            meta = {
                                "run_id": rid,
                                "results_dir": "",
                                "has_metrics": False,
                                "has_trace": False,
                                "has_config": False,
                                "has_phoenix_data": True,
                                "experiment_name": span.get("attributes.harmonia.experiment_name", ""),
                                "model": span.get(f"attributes.{SpanAttributes.LLM_MODEL_NAME}", "") if _OPENINFERENCE_AVAILABLE else span.get("attributes.llm.model_name", ""),
                                "provider": span.get("attributes.harmonia.llm_provider", ""),
                                "status": "unknown",
                                "total_turns": 0,
                                "total_duration": 0,
                                "total_input_tokens": 0,
                                "total_output_tokens": 0,
                                "total_cost_usd": 0,
                                "start_time": "",
                                "accuracy": None,
                                "column_mapping_accuracy": None,
                            }
                            rows.append(meta)
            except Exception as e:
                logger.warning(f"Error querying Phoenix: {e}")

        if not rows:
            return pd.DataFrame(columns=[
                "run_id", "experiment_name", "model", "provider", "status",
                "total_turns", "total_duration", "total_input_tokens",
                "total_output_tokens", "total_cost_usd", "start_time",
                "accuracy", "column_mapping_accuracy",
                "has_metrics", "has_trace", "has_config", "has_phoenix_data",
                "results_dir",
            ])

        return pd.DataFrame(rows)

    def get_run_spans(self, run_id: str) -> Optional[pd.DataFrame]:
        """Get all spans for a specific run from Phoenix. Returns None if Phoenix unavailable."""
        if not self._phoenix_available or not self._phoenix_client:
            return None
        try:
            spans_df = self._phoenix_client.get_spans_dataframe()
            if spans_df is None or len(spans_df) == 0:
                return None
            rid_col = "attributes.harmonia.run_id"
            if rid_col not in spans_df.columns:
                return None
            run_spans = spans_df[spans_df[rid_col] == run_id]
            return run_spans if len(run_spans) > 0 else None
        except Exception:
            return None

    def get_run_metrics(self, run_id: str) -> Optional[dict]:
        """Load metrics.json for a run from its results directory."""
        with self._cache_lock:
            if run_id in self._metrics_cache:
                return self._metrics_cache[run_id]

        d = self.find_results_dir(run_id)
        if d is None:
            return None

        metrics_path = d / "metrics.json"
        if not metrics_path.exists():
            return None

        try:
            data = json.loads(metrics_path.read_text())
            # Schema version check
            sv = data.get("schema_version", "")
            if sv and sv != _EXPECTED_SCHEMA_VERSION:
                logger.warning(
                    f"metrics.json for run {run_id} has schema_version={sv} "
                    f"(expected {_EXPECTED_SCHEMA_VERSION}). Loading best-effort."
                )
            with self._cache_lock:
                self._metrics_cache[run_id] = data
            return data
        except Exception as e:
            logger.warning(f"Error loading metrics for run {run_id}: {e}")
            return None

    def get_run_trace(self, run_id: str) -> Optional[dict]:
        """Load trace.json for a run from its results directory. Lazily loaded."""
        with self._cache_lock:
            if run_id in self._trace_cache:
                return self._trace_cache[run_id]

        d = self.find_results_dir(run_id)
        if d is None:
            return None

        trace_path = d / "trace.json"
        if not trace_path.exists():
            return None

        try:
            data = json.loads(trace_path.read_text())
            with self._cache_lock:
                self._trace_cache[run_id] = data
            return data
        except Exception as e:
            logger.warning(f"Error loading trace for run {run_id}: {e}")
            return None

    def get_run_config(self, run_id: str) -> Optional[dict]:
        """Load config_snapshot.yaml for a run. Returns None if missing."""
        d = self.find_results_dir(run_id)
        if d is None:
            return None

        config_path = d / "config_snapshot.yaml"
        if not config_path.exists():
            return None

        try:
            with open(config_path) as f:
                return yaml.safe_load(f)
        except Exception:
            return None

    def get_all_metrics(self) -> pd.DataFrame:
        """
        Aggregate metrics across all runs into a DataFrame.
        One row per run with key metrics columns.
        """
        rows = []
        with self._cache_lock:
            index_copy = dict(self._run_index)

        for run_id, d in index_copy.items():
            metrics = self.get_run_metrics(run_id)
            if metrics is None:
                continue

            md = metrics.get("metadata", {})
            cm = metrics.get("column_mapping", {})
            os_ = metrics.get("overall_summary", {})

            # Get token/cost from trace if available
            trace = self.get_run_trace(run_id)
            total_input = 0
            total_output = 0
            total_cost = 0.0
            total_turns = 0
            if trace:
                turns = trace.get("turns", [])
                total_turns = len(turns)
                total_input = sum(t.get("input_tokens", 0) for t in turns)
                total_output = sum(t.get("output_tokens", 0) for t in turns)
                total_cost = sum(t.get("cost_usd", 0) for t in turns)

            rows.append({
                "run_id": run_id,
                "experiment_name": md.get("experiment_name", ""),
                "model": md.get("llm_model", ""),
                "provider": md.get("llm_provider", ""),
                "model_family": md.get("model_family_group", ""),
                "parameter_count_b": md.get("parameter_count_b"),
                "column_mapping_accuracy": cm.get("accuracy"),
                "avg_accuracy_excl_empty": os_.get("avg_accuracy_excl_empty"),
                "avg_accuracy_incl_empty": os_.get("avg_accuracy_incl_empty"),
                "avg_f1_excl_empty": os_.get("avg_f1_excl_empty"),
                "avg_precision_excl_empty": os_.get("avg_precision_excl_empty"),
                "avg_recall_excl_empty": os_.get("avg_recall_excl_empty"),
                "total_hallucinations": os_.get("total_hallucinations", 0),
                "total_omissions": os_.get("total_omissions", 0),
                "total_columns": os_.get("total_columns", 0),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_cost_usd": total_cost,
                "total_turns": total_turns,
            })

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    def get_token_summary(self, group_by: str = "model") -> pd.DataFrame:
        """
        Aggregate token/cost data grouped by model, provider, or experiment.
        Primary source: trace.json turn-level data.
        """
        rows = []
        with self._cache_lock:
            index_copy = dict(self._run_index)

        for run_id, d in index_copy.items():
            trace = self.get_run_trace(run_id)
            if trace is None:
                continue

            turns = trace.get("turns", [])
            total_input = sum(t.get("input_tokens", 0) for t in turns)
            total_output = sum(t.get("output_tokens", 0) for t in turns)
            total_cost = sum(t.get("cost_usd", 0) for t in turns)

            rows.append({
                "run_id": run_id,
                "experiment_name": trace.get("experiment", {}).get("name", ""),
                "model": trace.get("llm", {}).get("model", ""),
                "provider": trace.get("llm", {}).get("provider", ""),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "total_cost_usd": total_cost,
                "total_turns": len(turns),
                "start_time": trace.get("timing", {}).get("start_time", ""),
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        return df

    def find_results_dir(self, run_id: str) -> Optional[Path]:
        """Find the canonical results directory for the given run_id."""
        with self._cache_lock:
            return self._run_index.get(run_id)

    def refresh(self):
        """Re-scan results directory and re-query Phoenix. Called by refresh buttons."""
        with self._cache_lock:
            self._run_index.clear()
            self._metrics_cache.clear()
            self._trace_cache.clear()
        self._init_phoenix()
        self._build_run_index()

    @property
    def phoenix_available(self) -> bool:
        return self._phoenix_available
