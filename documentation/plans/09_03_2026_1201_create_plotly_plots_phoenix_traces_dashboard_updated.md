# Implementation Plan: Dash Dashboard for Phoenix Traces and Experiment Metrics

**Date**: 2026-03-09
**Updated**: 2026-03-09 (post-review)
**Status**: Approved for implementation
**Estimated effort**: 4-5 developer-days
**Depends on**: `09_03_2026_1201_implement_improved_tracing.md` (Phase 1 complete — verified implemented)

---

## Review Summary: Changes from Original Plan

The following issues were identified during code review and corrected in this updated plan:

### Critical fixes applied
- **[C1] `ExperimentTrace` lacks `run_id` field.** `trace.json` does not contain `run_id` at the top level (confirmed by inspecting actual files). The tracing plan mentioned adding it but it was not done. **This plan now includes a prerequisite task (Section 0.2) to add `run_id` to `ExperimentTrace.to_dict()`.**
- **[C2] Duplicate run_id → directory mapping.** 31/42 run_ids map to multiple directories (both `{name}_{YYYYMMDD}_{HHMMSS}_{run_id}` and `{name}_{slurm_job_id}_{run_id}` formats coexist). **Fix:** `find_results_dir()` now prefers the SLURM-job-ID format when duplicates exist, falling back to timestamp format.
- **[C3] `get_all_runs()` was Phoenix-only.** Runs without Phoenix spans (pre-tracing experiments) would be invisible. **Fix:** Data loader now uses dual-source discovery: scan `results/` directories AND query Phoenix, then outer-join on `run_id`.

### Important fixes applied
- **[I1] Reuse existing `io.py` utilities.** `extract_run_id()` and `discover_metrics_files()` from `src/evaluation/visualization/io.py` are now imported rather than reimplemented.
- **[I2] Import path strategy.** Changed from `python -m src.dashboard.app` to `sys.path.insert` pattern matching existing entry points. No `src/__init__.py` added (avoids breaking existing scripts).
- **[I3] Span attribute constants.** Dashboard must use `SpanAttributes.*` constants from `openinference.semconv.trace`, not hardcoded strings, to match `tracing.py`.
- **[I4] Pinned dependency versions** for reproducibility.
- **[I5] Thread safety.** `DashboardDataLoader` cache uses `threading.Lock`.
- **[I6] `metrics.json` schema mismatch.** The plan's Data Formats Reference incorrectly described `metadata` and `overall_summary` fields. Corrected to match actual `schemas.py`.

### Minor fixes applied
- **[M1]** Added schema version checking for `metrics.json`.
- **[M2]** Added turn pagination for 50+ turn runs in Trace Explorer.
- **[M3]** Added port-in-use detection on startup.
- **[M4]** Added explicit refresh button on every tab.
- **[M5]** Side-by-side comparison handles mismatched column sets via union with N/A fill.

---

## 0. Overview

A Plotly Dash web application that provides interactive visualization of Harmonia experiment data by combining:
- **Phoenix trace data** (via `phoenix.Client().get_spans_dataframe()`) — span hierarchy, token counts, cost, timing, errors
- **Existing metrics data** (from `metrics.json`) — column mapping accuracy, value accuracy, F1, precision, recall
- **Existing trace data** (from `trace.json`) — conversation turns, agent responses, code executions

The dashboard runs as either a submit-node process (lightweight usage) or a SLURM job (interactive sessions with many plots/large datasets).

---

## 0.1 Implementation Context for Fresh Claude Instances

This section provides all the context a new Claude instance needs to implement this dashboard without re-reading the research documents.

### Prerequisite

This plan depends on the tracing plan (`09_03_2026_1201_implement_improved_tracing.md`) Phase 1 being complete. **Verified: Phase 1 is implemented.** `TurnRecord` in `logger.py` has `input_tokens`, `output_tokens`, `cost_usd`, `code_executions`, `usage_records` fields. `tracing.py` has `experiment_span()`, `turn_span()`, `llm_call_span()`, `tool_span()`, `set_llm_usage()`, `extract_usage_records()`, `extract_code_executions()`, `calculate_turn_cost()`.

**One gap remains:** `ExperimentTrace.to_dict()` does not include `run_id`. See Section 0.2 for the prerequisite fix.

### Key Source Files (read these before implementing)

| File | Absolute Path | Why |
|------|---------------|-----|
| `metrics.py` | `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/evaluation/metrics.py` | `calculate_all_metrics()` function. Produces the `MetricsResult` object that gets serialized to `metrics.json`. |
| `schemas.py` | `.../src/evaluation/schemas.py` | Pydantic models for `MetricsResult`, `ColumnMappingMetrics`, `ColumnValueMetrics`, `OverallSummary`, `ExperimentMetadata`. Defines the exact schema of `metrics.json`. |
| `visualize_metrics_cli.py` | `.../src/evaluation/visualize_metrics_cli.py` | Existing CLI for metrics visualization. Reference for how metrics data is currently loaded and plotted. The dashboard supersedes some of this functionality but does not replace it. |
| `io.py` | `.../src/evaluation/visualization/io.py` | **Reuse this.** Contains `extract_run_id()`, `discover_metrics_files()`, `load_metrics_bundle()`. The dashboard data loader must import these rather than reimplementing. |
| `logger.py` | `.../src/automation/logger.py` | `TurnRecord` and `ExperimentTrace` define the `trace.json` schema. `TurnRecord` has `input_tokens`, `output_tokens`, `cost_usd`, `code_executions`, `usage_records` fields. |
| `config.py` | `.../src/automation/config.py` | `ExperimentConfig` and `ModelMetadataConfig`. The `config_snapshot.yaml` saved per run follows this structure. `ModelMetadataConfig` has `pricing_prompt_per_million_tokens` and `pricing_completion_per_million_tokens` for cost calculation. |
| `tracing.py` | `.../src/automation/tracing.py` | Contains `extract_code_executions()`, `extract_usage_records()`, `calculate_turn_cost()` — reusable for the dashboard's trace parsing. Also defines the OTel span schema using `SpanAttributes` constants. |

All `...` paths are relative to `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/`.

### Data Formats Reference

**`metrics.json` top-level keys**: `schema_version`, `metadata`, `column_mapping`, `column_values`, `extra_columns_count`, `extra_columns`, `overall_summary`, `gold_standard_file`, `llm_output_file`, `column_mapping_file_found`, `value_mapping_file_found`.

- `metadata` (ExperimentMetadata) contains: `experiment_name`, `timestamp`, `llm_provider`, `llm_model`, `timing_seconds`, `pricing_prompt_per_million_tokens`, `pricing_completion_per_million_tokens`, `parameter_count_b`, `model_family_group`, `supports_tools`. **Note:** does NOT contain `run_id`, `context_type`, `total_turns`, `total_duration_seconds`, or `status` — the original plan incorrectly listed these.
- `overall_summary` (OverallSummary) contains: `total_columns`, `avg_accuracy_incl_empty`, `avg_accuracy_excl_empty`, `avg_precision_incl_empty`, `avg_precision_excl_empty`, `avg_recall_incl_empty`, `avg_recall_excl_empty`, `avg_f1_incl_empty`, `avg_f1_excl_empty`, `total_hallucinations`, `total_omissions`, `avg_hallucination_rate`, `avg_omission_rate`, `total_errors`, `total_whitespace_only`, `total_case_only`, `total_whitespace_and_case`, `total_genuine`. **Note:** does NOT contain `column_mapping_accuracy` or `overall_value_accuracy` — these were incorrectly listed in the original plan.
- `column_mapping` (ColumnMappingMetrics) contains: `total_expected`, `correct`, `wrong`, `missing`, `explicitly_null`, `precision_excl_null`, `precision_incl_null`, `recall`, `accuracy`, `details` (list of ColumnMappingDetail).
- `column_values` (dict of column name → ColumnValueMetrics) contains per-column: `accuracy_incl_empty`, `accuracy_excl_empty`, `precision_macro_incl_empty`, `precision_macro_excl_empty`, `recall_macro_incl_empty`, `recall_macro_excl_empty`, `f1_macro_incl_empty`, `f1_macro_excl_empty`, `hallucination_count`, `hallucination_rate`, `omission_count`, `omission_rate`, `error_categorization`, `confusion_matrix`, `misclassifications`, `row_comparisons`.

**`trace.json` structure**: Top-level keys: `experiment` (dict with `name`, `description`), `llm` (dict with `provider`, `model`), `timing` (dict with `start_time`, `end_time`, `total_duration_seconds`), `status` (string), `error_message` (string or null), `config_snapshot` (dict or null), `turns` (list of TurnRecord dicts). Each turn has: `turn`, `user_message`, `agent_response`, `response_type`, `tool_calls`, `duration_seconds`, `raw_messages`, `timestamp`, `input_tokens`, `output_tokens`, `cost_usd`, `code_executions`, `usage_records`. **Note:** `trace.json` currently does NOT contain `run_id` — see Section 0.2.

**Results directory naming convention**: Two formats coexist:
1. `{experiment_name}_{YYYYMMDD}_{HHMMSS}_{run_id}` (timestamp format)
2. `{experiment_name}_{slurm_job_id}_{run_id}` (SLURM format)

The 8-char hex `run_id` is always the last `_`-delimited segment. When a run_id maps to multiple directories, **prefer the SLURM-job-ID format** as the canonical directory. The results directory is at `.../harmonia/results/`.

**Phoenix span attributes** (set by `tracing.py`): These are set using `SpanAttributes.*` constants from `openinference.semconv.trace`. The dashboard MUST use the same constants, not hardcoded strings.
- Root AGENT spans: `harmonia.run_id`, `harmonia.experiment_name`, `harmonia.trace_type`, `SpanAttributes.LLM_MODEL_NAME` (resolves to `llm.model_name`), `harmonia.llm_provider`, `harmonia.config_snapshot`.
- CHAIN (turn) spans: `harmonia.turn_number`, `SpanAttributes.INPUT_VALUE` (resolves to `input.value`).
- LLM spans: `SpanAttributes.LLM_MODEL_NAME`, `SpanAttributes.LLM_TOKEN_COUNT_PROMPT`, `SpanAttributes.LLM_TOKEN_COUNT_COMPLETION`, `SpanAttributes.LLM_TOKEN_COUNT_TOTAL`, `harmonia.cost_usd`.
- TOOL spans: `tool.name`, `SpanAttributes.INPUT_VALUE`.

### Gotchas

1. **Python environment**: Use `.venv` at `.../harmonia/.venv/` (Python 3.11). Do NOT use conda or system Python. Install deps with `.venv/bin/uv pip install`.

2. **The `src/` directory is not a proper Python package with a top-level `__init__.py`.** The existing CLI entry points (e.g., `run_experiment.py`) use `sys.path.insert(0, str(Path(__file__).parent / "src"))`. The dashboard entry point MUST follow the same pattern. Do NOT add `src/__init__.py` — it would break existing import resolution.

3. **Phoenix client import**: `import phoenix as px; client = px.Client(endpoint="...")`. The `get_spans_dataframe()` method returns a pandas DataFrame. Custom attributes set via `span.set_attribute("harmonia.run_id", ...)` appear as columns. **Verify the exact column names at implementation time** by calling `get_spans_dataframe()` against a live Phoenix instance with test data and printing `df.columns.tolist()`. The installed version is `arize-phoenix==13.11.0` with `arize-phoenix-client==1.31.0`.

4. **Not all results directories have `metrics.json`.** Metrics are only calculated when the experiment has an `evaluation` config with `gold_standard` set AND the LLM successfully produces output files. Failed/timeout experiments typically lack metrics. The dashboard must handle this gracefully (show "N/A" for accuracy columns, exclude from accuracy plots).

5. **Not all results directories have the run_id suffix.** Older results from before the run_id system may use `{experiment_name}_{timestamp}` format without the `_{run_id}` suffix. The `find_results_dir()` function should handle both formats. **Additionally, many run_ids map to multiple directories** (see Results directory naming convention above).

6. **Phoenix may not be running when the dashboard starts.** The data loader should handle `ConnectionRefusedError` or `ConnectionError` from `px.Client()` gracefully — fall back to loading only local file data (trace.json, metrics.json) without Phoenix span data. Show a warning banner in the UI: "Phoenix server not available. Showing local data only."

7. **SSH port forwarding and host binding**: Users access the dashboard via `ssh -L 8050:localhost:8050 <submit-node>` (submit mode) or `ssh -L 8050:<compute-node>:8050 <submit-node>` (SLURM mode). The dashboard **must** bind to `0.0.0.0` (not just `localhost`) to be reachable via port forwarding: `app.run(host="0.0.0.0", port=port, debug=False)`.

8. **AG Grid community edition only.** `dash-ag-grid` community edition is free and sufficient. Do NOT use enterprise-only features (row grouping, server-side row model, pivoting, etc.). Basic sorting, filtering, column resizing, and CSV export are all available in community.

9. **Results directory can be large.** With 100+ runs, each with 200-300KB trace.json files, scanning all results at startup could be slow. Use a two-level loading strategy: (a) on startup, scan directory names only to build the run index; (b) load `metrics.json` (small) for all runs to populate the overview table; (c) load `trace.json` (large) lazily only when a specific run is selected in Trace Explorer.

10. **The `run_id` is the universal join key.** It appears in: results directory name (last `_`-delimited segment), `metrics.json` (extractable via `io.py`'s `extract_run_id()`), and Phoenix spans (as `harmonia.run_id` attribute on the root AGENT span). Always join on this key. **After Section 0.2 is implemented**, `trace.json` will also contain `run_id` at the top level.

11. **Dash callback circular dependencies.** The click-through pattern (click bar chart → switch tab → update trace explorer) requires `suppress_callback_exceptions=True` on the Dash app, because the Trace Explorer components don't exist in the DOM until that tab is rendered. Use `dash.callback_context` to distinguish which input triggered a callback.

12. **Plotly figures should use `fig.update_layout(template="plotly_white")` for consistency.** This matches the FLATLY bootstrap theme.

13. **Thread safety.** Dash runs on Flask which can serve concurrent requests. The `DashboardDataLoader` must use `threading.Lock` around any mutable shared state (cache dicts).

14. **Port-in-use detection.** On startup, check if the port is available before launching. Use `socket.bind()` test and provide a clear error message if the port is taken.

15. **Explicit refresh button.** Every tab must have a "Refresh Data" button. The "refresh on tab switch" strategy alone is insufficient for users staying on one tab during long sessions.

---

## 0.2 Prerequisite: Add `run_id` to `ExperimentTrace`

**Problem:** `ExperimentTrace.to_dict()` in `logger.py` does not include `run_id`. The `trace.json` output therefore lacks `run_id`, making it impossible to join trace data with Phoenix/metrics data by `run_id` without parsing the directory name.

**Fix:** Add `run_id` field to `ExperimentTrace` and include it in `to_dict()` output.

```python
# In logger.py, ExperimentTrace dataclass:
@dataclass
class ExperimentTrace:
    """Complete trace of an experiment run."""
    experiment_name: str
    description: str
    llm_provider: str
    llm_model: str
    start_time: str
    end_time: Optional[str] = None
    turns: list[TurnRecord] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    status: str = "running"
    error_message: Optional[str] = None
    config_snapshot: Optional[dict] = None
    run_id: Optional[str] = None  # ADD THIS

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,  # ADD THIS
            "experiment": {
                "name": self.experiment_name,
                "description": self.description,
            },
            # ... rest unchanged
        }
```

**Also update `TraceLogger.start_experiment()`** to accept and store `run_id`:

```python
def start_experiment(self, experiment_name, description, llm_provider, llm_model, run_id=None):
    self.trace = ExperimentTrace(
        experiment_name=experiment_name,
        description=description,
        llm_provider=llm_provider,
        llm_model=llm_model,
        start_time=datetime.utcnow().isoformat(),
        run_id=run_id,
    )
```

**Callers to update:** Find all calls to `TraceLogger.start_experiment()` and pass `run_id` where available. The `run_experiment.py` automated runner and `run_manual_experiment.py` monitor both have access to `run_id`.

---

## 1. Dashboard Architecture

```
┌────────────────────────────────────────────────────────┐
│  Dash App (src/dashboard/app.py)                        │
│                                                         │
│  Data Layer (dual-source)                               │
│    ├─ phoenix.Client() → spans DataFrame (if available) │
│    ├─ results/*/metrics.json → metrics DataFrame        │
│    ├─ results/*/trace.json → turn-level data (lazy)     │
│    └─ results/*/config_snapshot.yaml → run configs      │
│                                                         │
│  Tabs                                                   │
│    ├─ Experiment Overview (runs table + summary stats)   │
│    ├─ Metrics Comparison (bar charts, scatter, heatmap) │
│    ├─ Trace Explorer (span hierarchy per run)           │
│    ├─ Token & Cost Analysis (per-model, per-turn)       │
│    └─ Side-by-Side Comparison (two runs aligned)        │
│                                                         │
│  Port: 8050 (configurable)                              │
└────────────────────────────────────────────────────────┘
        │                              │
        ▼                              ▼
  Phoenix Server               Results Directory
  (SQLite, port 6006)          (trace.json, metrics.json)
  (optional — degrades          (always available)
   gracefully if absent)
```

---

## 2. Tab Specifications

### 2.1 Tab: Experiment Overview

**Purpose**: Entry point. Shows all experiment runs with key metadata and status.

**Data sources**: Results directory scan (always) + Phoenix spans (if available) + `metrics.json` files. Dual-source: runs discovered from file system are outer-joined with Phoenix span data.

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Runs table | Dash AG Grid | Columns: run_id, experiment_name, model, provider, status, total_turns, total_duration, total_tokens, total_cost_usd, accuracy (from metrics), timestamp. Sortable, filterable. Row click navigates to Trace Explorer tab for that run. |
| Summary cards | `dbc.Card` | Total runs, success rate, average accuracy, total cost, total tokens. Filterable by experiment name and date range. |
| Status distribution | Plotly pie chart | Completed / failed / timeout / cancelled breakdown. |
| Refresh button | `dbc.Button` | Manually refresh all data sources. |

**Interactions**:
- Click row in AG Grid → Trace Explorer tab opens for that run
- Filter by experiment name, model, provider, date range, status
- Bulk select runs for side-by-side comparison

**Empty state**: When no runs exist, show a centered message: "No experiment runs found. Run experiments first, then refresh."

### 2.2 Tab: Metrics Comparison

**Purpose**: Compare quantitative performance across runs and models.

**Data sources**: `metrics.json` from results directories, enriched with token/cost from Phoenix spans (if available) or from `trace.json` token fields.

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Accuracy bar chart | Plotly bar | X-axis: run_id or model name, Y-axis: column mapping accuracy (`column_mapping.accuracy`) and avg value accuracy (`overall_summary.avg_accuracy_excl_empty`). Color by provider. `customdata` carries run_id for click-through. |
| Per-column accuracy heatmap | Plotly heatmap | Rows: target columns, Columns: runs/models. Cell color: `accuracy_excl_empty` from `column_values`. Hover shows value. |
| Cost vs. accuracy scatter | Plotly scatter | X: total_cost_usd, Y: accuracy. Size: total_tokens. Color: model. Labels: run_id. |
| Token usage bar chart | Plotly grouped bar | Per-run breakdown of input vs. output tokens. |
| F1 / precision / recall radar | Plotly radar/spider | Per-column breakdown for selected runs (max 5). Uses `f1_macro_excl_empty`, `precision_macro_excl_empty`, `recall_macro_excl_empty`. |
| Metrics summary table | Dash AG Grid | Full metrics detail with CSV export. |
| Refresh button | `dbc.Button` | Manually refresh data. |

**Interactions**:
- Click bar in accuracy chart → Trace Explorer tab opens for that run (via Dash callback on `clickData`)
- Select subset of runs via checkboxes or date range
- Toggle between "group by model" and "group by run"

### 2.3 Tab: Trace Explorer

**Purpose**: Deep-dive into a single experiment run. Shows span hierarchy, conversation turns, code executions, and token usage.

**Data sources**: Phoenix spans for the selected run (if available) + `trace.json` for raw conversation data.

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Run header | `dbc.Card` | Run ID, experiment name, model, provider, status, total duration, total tokens, total cost. Link to Phoenix UI trace view (if Phoenix available). |
| Span waterfall | Plotly Gantt/timeline | Horizontal bars showing span duration. Nested by parent-child. Color by span kind (AGENT=blue, CHAIN=green, LLM=orange, TOOL=purple). Click to expand details. **Only shown if Phoenix data available for this run.** |
| Turn accordion | `dbc.Accordion` | One item per turn. Each shows: user message, agent response, code executed (syntax-highlighted), code output, token counts, cost, duration. Expandable/collapsible. **Paginated: show 20 turns at a time with next/prev controls for runs with 50+ turns.** |
| Token usage per turn | Plotly bar | Stacked bar: input tokens (blue) + output tokens (orange) per turn number. Source: `trace.json` turn-level `input_tokens`/`output_tokens`. |
| Cost per turn | Plotly line | Cumulative cost across turns. Source: `trace.json` turn-level `cost_usd`. |
| Error indicators | Badge/alert | If any span has error status, show red badge on the turn and a summary alert. |
| Refresh button | `dbc.Button` | Manually refresh data. |

**Interactions**:
- Select run from dropdown (populated from all discovered runs, not just Phoenix)
- Click span in waterfall → accordion scrolls to that turn
- Click "Open in Phoenix" → opens Phoenix UI in new tab at `http://<phoenix_endpoint>/traces/{trace_id}`

**Empty/missing data handling**:
- Run with no `trace.json`: show "Trace data not available for this run" message
- Run with 0 turns: show "Experiment completed with no conversation turns" message
- Run with no Phoenix spans: hide span waterfall, show token/cost charts from `trace.json` data only

### 2.4 Tab: Token & Cost Analysis

**Purpose**: Aggregate token usage and cost analysis across runs, models, and providers.

**Data sources**: `trace.json` turn-level token/cost data (primary) + Phoenix LLM spans (supplementary, if available).

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Cost per model | Plotly bar | Total cost by model across all runs. |
| Tokens per model | Plotly grouped bar | Input vs. output tokens per model. |
| Cost vs. turns | Plotly scatter | X: number of turns, Y: total cost. One point per run. Color: model. |
| Token efficiency | Plotly scatter | X: total tokens, Y: accuracy. Shows which models achieve better accuracy with fewer tokens. |
| Cost breakdown table | Dash AG Grid | Per-run detail: run_id, model, input_tokens, output_tokens, prompt_cost, completion_cost, total_cost. Sortable. |
| Cost over time | Plotly line | Cumulative cost across experiments (X: date, Y: cumulative cost). Useful for budget tracking. |
| Refresh button | `dbc.Button` | Manually refresh data. |

### 2.5 Tab: Side-by-Side Comparison

**Purpose**: Compare two experiment runs turn-by-turn.

**Data sources**: `trace.json` for both selected runs + `metrics.json` for both (if available) + Phoenix spans (if available).

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Run selectors | Two dropdowns | Select Run A and Run B. Dropdowns populated from all discovered runs. |
| Diff summary card | `dbc.Card` | Delta in: accuracy, total tokens, total cost, number of turns, duration. Green/red arrows for better/worse. |
| Synchronized turn accordions | Two-column layout | Left: Run A turns. Right: Run B turns. Aligned by turn number. Differences highlighted (e.g., different response_type, different code executed). Scrolling synchronized. |
| Metric comparison | Plotly grouped bar | Per-column accuracy side by side for the two runs. **Handles mismatched column sets:** uses union of both column sets, shows N/A for columns only present in one run. |
| Token comparison | Plotly grouped bar | Per-turn token usage side by side. |
| Timeline overlay | Plotly dual Gantt | Both span waterfalls overlaid with transparency, aligned by turn number. Only shown if Phoenix data available for both runs. |

---

## 3. Data Loading Layer

### 3.1 `src/dashboard/data_loader.py`

```python
"""
Data loading for the Dash dashboard.
Dual-source: scans results/ directories AND queries Phoenix.
Outer-joins on run_id so runs are visible even if one source is missing.
"""

import threading
from pathlib import Path
from typing import Optional

import pandas as pd

# Reuse existing utilities
from evaluation.visualization.io import extract_run_id, discover_metrics_files, load_metrics_bundle

# Use SpanAttributes constants, not hardcoded strings
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


class DashboardDataLoader:
    def __init__(self, phoenix_endpoint: str, results_base_dir: Path):
        self.phoenix_endpoint = phoenix_endpoint
        self.results_dir = results_base_dir
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
            # Test connection
            self._phoenix_client.get_spans_dataframe(limit=1)
            self._phoenix_available = True
        except Exception:
            self._phoenix_available = False

    def _build_run_index(self):
        """
        Scan results/ directory names to build run_id -> directory mapping.
        When a run_id maps to multiple directories, prefer the SLURM-job-ID
        format (shorter middle segment) as canonical.
        """

    def get_all_runs(self) -> pd.DataFrame:
        """
        Dual-source run discovery:
        1. Scan results/ directories for all runs (file-based)
        2. Query Phoenix for root AGENT spans (if available)
        3. Outer-join on run_id
        Returns DataFrame with: run_id, experiment_name, model, provider,
        status, duration, total_input_tokens, total_output_tokens,
        total_cost, start_time, has_metrics, has_phoenix_data.
        """

    def get_run_spans(self, run_id: str) -> Optional[pd.DataFrame]:
        """Get all spans for a specific run from Phoenix. Returns None if Phoenix unavailable."""

    def get_run_metrics(self, run_id: str) -> Optional[dict]:
        """Load metrics.json for a run from its results directory."""

    def get_run_trace(self, run_id: str) -> Optional[dict]:
        """Load trace.json for a run from its results directory. Lazily loaded."""

    def get_run_config(self, run_id: str) -> Optional[dict]:
        """Load config_snapshot.yaml for a run. Returns None if missing (older runs)."""

    def get_all_metrics(self) -> pd.DataFrame:
        """
        Aggregate metrics across all runs.
        Outer-joins file-based metrics with Phoenix span data via run_id.
        Handles runs that have metrics but no Phoenix data, and vice versa.
        """

    def get_token_summary(self, group_by: str = "model") -> pd.DataFrame:
        """
        Aggregate token/cost data grouped by model, provider, or experiment.
        Primary source: trace.json turn-level data.
        Supplementary: Phoenix LLM span data.
        """

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
```

### 3.2 Run ID to Results Directory Mapping

The results directory naming convention has two formats:
1. `{experiment_name}_{YYYYMMDD}_{HHMMSS}_{run_id}` (timestamp format)
2. `{experiment_name}_{slurm_job_id}_{run_id}` (SLURM format)

The 8-char hex `run_id` is always the last `_`-delimited segment. The loader uses `io.py`'s `RUN_ID_PATTERN = re.compile(r"_([0-9a-f]{8})$")` to extract it. When multiple directories share the same `run_id`, **prefer the SLURM-job-ID format** as canonical.

### 3.3 Graceful Degradation Matrix

| Phoenix | metrics.json | trace.json | Result |
|---------|-------------|------------|--------|
| Available | Present | Present | Full functionality |
| Available | Missing | Present | Overview + Trace Explorer, no Metrics tab data for this run |
| Available | Present | Missing | Overview + Metrics, Trace Explorer shows Phoenix spans only |
| Unavailable | Present | Present | Full functionality except span waterfall |
| Unavailable | Missing | Present | Overview + Trace Explorer (no metrics, no spans) |
| Unavailable | Present | Missing | Overview + Metrics only |
| Unavailable | Missing | Missing | Run appears in overview (from dir scan) with "No data" |

---

## 4. Application Structure

### File Layout

```
src/dashboard/
    __init__.py
    app.py                  # Main Dash app, layout, tab routing
    data_loader.py          # Phoenix + file data loading (dual-source)
    tabs/
        __init__.py
        overview.py         # Experiment Overview tab
        metrics.py          # Metrics Comparison tab
        trace_explorer.py   # Trace Explorer tab
        token_cost.py       # Token & Cost Analysis tab
        comparison.py       # Side-by-Side Comparison tab
    components/
        __init__.py
        span_waterfall.py   # Plotly Gantt chart for span hierarchy
        turn_accordion.py   # Accordion component for conversation turns
        run_table.py        # AG Grid configuration for runs table
        diff_card.py        # Summary diff card for comparison
```

### Entry Point

```python
# src/dashboard/app.py

import sys
from pathlib import Path

# Follow existing codebase pattern — do NOT add src/__init__.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dash
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
)

app.layout = dbc.Container([
    dbc.NavbarSimple(brand="Harmonia Experiment Dashboard", color="primary", dark=True),
    # Phoenix status banner (shown when Phoenix unavailable)
    html.Div(id="phoenix-status-banner"),
    dbc.Tabs([
        dbc.Tab(label="Overview", tab_id="overview"),
        dbc.Tab(label="Metrics", tab_id="metrics"),
        dbc.Tab(label="Trace Explorer", tab_id="trace"),
        dbc.Tab(label="Tokens & Cost", tab_id="tokens"),
        dbc.Tab(label="Comparison", tab_id="comparison"),
    ], id="tabs", active_tab="overview"),
    html.Div(id="tab-content"),
], fluid=True)
```

### CLI Launch

```bash
# Submit node (lightweight)
cd harmonia_metadata_agent/analysis/dstoker/harmonia
.venv/bin/python src/dashboard/app.py \
    --phoenix-endpoint http://localhost:6006 \
    --results-dir results/ \
    --port 8050

# SLURM job (heavy interactive use)
srun --time=04:00:00 --mem=8G --cpus-per-task=2 --account=compgen \
    .venv/bin/python src/dashboard/app.py \
    --phoenix-endpoint http://localhost:6006 \
    --results-dir results/ \
    --port 8050
```

Access via SSH port forwarding:
```bash
ssh -L 8050:localhost:8050 <submit-node-or-compute-node>
```

---

## 5. Dependencies

Add to project `.venv` (pinned for reproducibility):
```
dash==2.18.2
dash-bootstrap-components==1.6.0
dash-ag-grid==31.2.0
plotly==5.24.1
```

These are compatible with Python 3.11 and the existing `pandas==2.3.3`, `pydantic==2.12.5`, `arize-phoenix==13.11.0`.

**Note:** Verify exact latest compatible versions at installation time with:
```bash
.venv/bin/uv pip install dash==2.18.2 dash-bootstrap-components==1.6.0 dash-ag-grid==31.2.0 plotly==5.24.1
```

---

## 6. Key Interactions and Callbacks

### Click-Through: Accuracy Bar → Trace Explorer

```python
@app.callback(
    Output("tabs", "active_tab"),
    Output("trace-run-selector", "value"),
    Input("accuracy-bar-chart", "clickData"),
)
def click_bar_to_trace(click_data):
    if click_data:
        run_id = click_data["points"][0]["customdata"][0]
        return "trace", run_id
    raise dash.exceptions.PreventUpdate
```

### Synchronized Scroll in Comparison Tab

```python
@app.callback(
    Output("run-b-accordion", "active_item"),
    Input("run-a-accordion", "active_item"),
)
def sync_accordions(active_item):
    return active_item
```

### Refresh Data

```python
@app.callback(
    Output("tab-content", "children"),
    Input("refresh-button", "n_clicks"),
    State("tabs", "active_tab"),
)
def refresh_data(n_clicks, active_tab):
    if n_clicks:
        data_loader.refresh()
    return render_tab(active_tab)
```

### Live Data Refresh

The data loader caches results and refreshes on explicit "Refresh" button click (available on every tab). No automatic polling — experiments are batch-oriented, not real-time.

---

## 7. Deployment Options

### Option A: Submit Node (default, lightweight)

```bash
screen -dmS harmonia-dashboard \
    .venv/bin/python src/dashboard/app.py --port 8050
```

Suitable for: browsing results, quick comparisons, < 100 runs loaded.

### Option B: SLURM Job (heavy interactive sessions)

```bash
srun --job-name=harmonia-dashboard --account=compgen \
    --time=04:00:00 --mem=8G --cpus-per-task=2 \
    .venv/bin/python src/dashboard/app.py --port 8050
```

Suitable for: large datasets (hundreds of runs), many concurrent plots, AG Grid with heavy filtering.

Note: When running as a SLURM job, the SSH port forward must target the compute node where the job runs:
```bash
# Find the node
squeue -u $USER --name=harmonia-dashboard -o "%N"
# Port forward
ssh -L 8050:<compute-node>:8050 <submit-node>
```

### Convenience Script: `scripts/dashboard.sh`

```bash
#!/bin/bash
# Usage: ./scripts/dashboard.sh [start|stop|status] [--slurm]
# Default: submit node. --slurm: launch as SLURM job.
```

---

## 8. Relationship to Phoenix UI

The Dash dashboard and the Phoenix UI are **complementary**, not competing:

| Capability | Dash Dashboard | Phoenix UI |
|-----------|---------------|------------|
| Experiment overview with metrics | Yes (primary) | No (traces only) |
| Click-through from metrics to traces | Yes (native callbacks) | No |
| Side-by-side run comparison | Yes (built-in tab) | No (manual browser tabs) |
| Cost/token aggregate analysis | Yes (dedicated tab) | Limited |
| Span waterfall drill-down | Yes (Plotly Gantt) | Yes (native, better) |
| Annotation/labeling | No | Yes (native) |
| UMAP embedding visualization | No | Yes (native) |
| Search/filter individual spans | Limited | Yes (powerful SpanQuery) |

The Dash dashboard provides **"Open in Phoenix"** links for any run, enabling seamless handoff to Phoenix for deep span-level inspection.

---

## 9. File Change Summary

### New Files

| File | Purpose |
|------|---------|
| `src/dashboard/__init__.py` | Package init |
| `src/dashboard/app.py` | Main Dash app, layout, CLI entry point |
| `src/dashboard/data_loader.py` | Phoenix + file data loading (dual-source, thread-safe) |
| `src/dashboard/tabs/__init__.py` | Tab package init |
| `src/dashboard/tabs/overview.py` | Experiment Overview tab |
| `src/dashboard/tabs/metrics.py` | Metrics Comparison tab |
| `src/dashboard/tabs/trace_explorer.py` | Trace Explorer tab |
| `src/dashboard/tabs/token_cost.py` | Token & Cost Analysis tab |
| `src/dashboard/tabs/comparison.py` | Side-by-Side Comparison tab |
| `src/dashboard/components/__init__.py` | Components package init |
| `src/dashboard/components/span_waterfall.py` | Span waterfall Plotly chart |
| `src/dashboard/components/turn_accordion.py` | Accordion component for conversation turns |
| `src/dashboard/components/run_table.py` | AG Grid run table config |
| `src/dashboard/components/diff_card.py` | Comparison diff summary |
| `scripts/dashboard.sh` | Dashboard start/stop convenience script |

### Modified Files

| File | Change |
|------|--------|
| `src/automation/logger.py` | Add `run_id` field to `ExperimentTrace`, update `to_dict()` and `start_experiment()` (Section 0.2) |

---

## 10. Testing Plan

1. **Data loading**: Verify `DashboardDataLoader` correctly queries Phoenix and reads results files. Test with 3+ runs from different models. Test with Phoenix unavailable.

2. **Tab rendering**: Each tab renders without errors when data is available. Test with: 0 runs (empty state), 1 run, 10+ runs.

3. **Click-through**: Click accuracy bar → Trace Explorer opens with correct run. Verify `customdata` propagation.

4. **Comparison**: Select two runs → side-by-side view aligns turns correctly. Test with runs of different turn counts. Test with runs that have different column sets.

5. **SLURM deployment**: Launch as SLURM job, verify port forwarding works from local machine.

6. **Performance**: Load 50+ runs, verify AG Grid and plots remain responsive. If slow, add pagination to AG Grid and lazy-loading for trace data.

7. **Graceful degradation**: Test each row in the degradation matrix (Section 3.3). Verify no tracebacks, appropriate "N/A" or "not available" messages shown.

8. **Duplicate run_id directories**: Verify `find_results_dir()` returns the SLURM-format directory when duplicates exist.

9. **Schema version checking**: Test with a `metrics.json` that has an unexpected `schema_version`. Verify warning is shown but data is still loaded best-effort.

10. **Port conflict**: Start two dashboard instances on the same port. Verify the second one fails with a clear error message.
