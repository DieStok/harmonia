# Implementation Plan: Dash Dashboard for Phoenix Traces and Experiment Metrics

**Date**: 2026-03-09
**Status**: Approved for implementation
**Estimated effort**: 4-5 developer-days
**Depends on**: `09_03_2026_1201_implement_improved_tracing.md` (Phase 1 complete)

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

This plan depends on the tracing plan (`09_03_2026_1201_implement_improved_tracing.md`) being implemented first (at least Phase 1). The dashboard queries Phoenix for span data and reads enriched `trace.json` files.

### Key Source Files (read these before implementing)

| File | Absolute Path | Why |
|------|---------------|-----|
| `metrics.py` | `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/evaluation/metrics.py` | `calculate_all_metrics()` function. Produces the `MetricsResult` object that gets serialized to `metrics.json`. |
| `schemas.py` | `.../src/evaluation/schemas.py` | Pydantic models for `MetricsResult`, `ColumnMappingMetrics`, `ColumnValueMetrics`, `OverallSummary`. Defines the exact schema of `metrics.json`. |
| `visualize_metrics_cli.py` | `.../src/evaluation/visualize_metrics_cli.py` | Existing CLI for metrics visualization. Reference for how metrics data is currently loaded and plotted. The dashboard supersedes some of this functionality but does not replace it. |
| `logger.py` | `.../src/automation/logger.py` | `TurnRecord` and `ExperimentTrace` define the `trace.json` schema. After tracing plan Phase 1, `TurnRecord` will have `input_tokens`, `output_tokens`, `cost_usd`, `code_executions`, `usage_records` fields. |
| `config.py` | `.../src/automation/config.py` | `ExperimentConfig` and `ModelMetadataConfig`. The `config_snapshot.yaml` saved per run follows this structure. `ModelMetadataConfig` has `pricing_prompt_per_million_tokens` and `pricing_completion_per_million_tokens` for cost calculation. |
| `tracing.py` | `.../src/automation/tracing.py` | (Created by tracing plan) Contains `extract_code_executions()` and `extract_usage_records()` — reusable for the dashboard's trace parsing if needed. |

All `...` paths are relative to `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/`.

### Data Formats Reference

**`metrics.json` top-level keys**: `schema_version`, `metadata`, `column_mapping`, `column_values`, `extra_columns_count`, `extra_columns`, `overall_summary`, `gold_standard_file`, `llm_output_file`, `column_mapping_file_found`, `value_mapping_file_found`.

- `metadata` contains: `model`, `provider`, `experiment_name`, `run_id`, `context_type`, `total_turns`, `total_duration_seconds`, `status`.
- `overall_summary` contains: `column_mapping_accuracy`, `overall_value_accuracy`, `columns_evaluated`, plus per-metric averages.
- `column_mapping` contains per-column mapping correctness (dict of column name → mapping result dict).
- `column_values` contains per-column `accuracy`, `f1`, `precision`, `recall`, `confusion_matrix` (dict of column name → value metrics dict).

**`trace.json` structure**: Top-level keys: `experiment` (dict with `name`, `description`), `llm` (dict with `provider`, `model`), `timing` (dict with `start_time`, `end_time`, `total_duration_seconds`), `status` (string), `error_message` (string or null), `turns` (list of TurnRecord dicts). Each turn has: `turn`, `user_message`, `agent_response`, `response_type`, `tool_calls`, `duration_seconds`, `raw_messages`, `timestamp`. After tracing plan: also `input_tokens`, `output_tokens`, `cost_usd`, `code_executions`, `usage_records`.

**Results directory naming convention**: `{experiment_name}_{timestamp}_{run_id}`. The 8-char hex `run_id` is always the last `_`-delimited segment. Example: `dou_harmonization_code-context_kimi-k2.5_20260302_170757_8f25137b`. The results directory is at `.../harmonia/results/`.

**Phoenix span attributes** (set by the tracing plan): Root AGENT spans have `harmonia.run_id`, `harmonia.experiment_name`, `harmonia.trace_type`, `llm.model_name`, `harmonia.llm_provider`. CHAIN (turn) spans have `harmonia.turn_number`, `input.value`, `output.value`. LLM spans have `llm.token_count.prompt`, `llm.token_count.completion`, `harmonia.cost_usd`. TOOL spans have `tool.name`, `input.value`, `output.value`, `tool.status`. See the tracing plan's OpenTelemetry Span Schema table for the full attribute set.

### Gotchas

1. **Python environment**: Use `.venv` at `.../harmonia/.venv/` (Python 3.11). Do NOT use conda or system Python. Install deps with `.venv/bin/pip install`.

2. **The `src/` directory is not a proper Python package with a top-level `__init__.py`.** The existing CLI entry points (e.g., `run_experiment.py`) use `sys.path.insert(0, str(Path(__file__).parent / "src"))`. The dashboard should follow the same pattern in its entry point script, or add `__init__.py` files to make `python -m src.dashboard.app` work.

3. **Phoenix client import**: `import phoenix as px; client = px.Client(endpoint="...")`. The `get_spans_dataframe()` method returns a pandas DataFrame with columns like `name`, `span_kind`, `parent_id`, `start_time`, `end_time`, `status_code`, `attributes`, `events`, `context.trace_id`, `context.span_id`. Custom attributes are nested under `attributes` as a dict — access with `df['attributes'].apply(lambda x: x.get('harmonia.run_id'))` or similar.

4. **Not all results directories have `metrics.json`.** Metrics are only calculated when the experiment has an `evaluation` config with `gold_standard` set AND the LLM successfully produces output files. Failed/timeout experiments typically lack metrics. The dashboard must handle this gracefully (show "N/A" for accuracy columns, exclude from accuracy plots).

5. **Not all results directories have the run_id suffix.** Older results from before the run_id system may use `{experiment_name}_{timestamp}` format without the `_{run_id}` suffix. The `find_results_dir()` function should handle both formats. Also, some results directories appear with SLURM job IDs instead of timestamps (e.g., `dou_harmonization_bdikit-tools_claude-sonnet-4.6_47437639_28b4291c`).

6. **Phoenix may not be running when the dashboard starts.** The data loader should handle `ConnectionRefusedError` or `ConnectionError` from `px.Client()` gracefully — fall back to loading only local file data (trace.json, metrics.json) without Phoenix span data. Show a warning banner in the UI: "Phoenix server not available. Showing local data only."

7. **SSH port forwarding and host binding**: Users access the dashboard via `ssh -L 8050:localhost:8050 <submit-node>` (submit mode) or `ssh -L 8050:<compute-node>:8050 <submit-node>` (SLURM mode). The dashboard **must** bind to `0.0.0.0` (not just `localhost`) to be reachable via port forwarding: `app.run(host="0.0.0.0", port=port, debug=False)`.

8. **AG Grid community edition only.** `dash-ag-grid` community edition is free and sufficient. Do NOT use enterprise-only features (row grouping, server-side row model, pivoting, etc.). Basic sorting, filtering, column resizing, and CSV export are all available in community.

9. **Results directory can be large.** With 100+ runs, each with 200-300KB trace.json files, scanning all results at startup could be slow. Use a two-level loading strategy: (a) on startup, scan directory names only to build the run index; (b) load `metrics.json` (small) for all runs to populate the overview table; (c) load `trace.json` (large) lazily only when a specific run is selected in Trace Explorer.

10. **The `run_id` is the universal join key.** It appears in: results directory name (last `_`-delimited segment), `metrics.json` (in `metadata.run_id`), and Phoenix spans (as `harmonia.run_id` attribute on the root AGENT span). Always join on this key. Note: `trace.json` currently does NOT contain `run_id` — the tracing plan adds it to `ExperimentTrace`.

11. **Dash callback circular dependencies.** The click-through pattern (click bar chart → switch tab → update trace explorer) requires `suppress_callback_exceptions=True` on the Dash app, because the Trace Explorer components don't exist in the DOM until that tab is rendered. Use `dash.callback_context` to distinguish which input triggered a callback.

12. **Plotly figures should use `fig.update_layout(template="plotly_white")` for consistency.** This matches the FLATLY bootstrap theme.

---

## 1. Dashboard Architecture

```
┌────────────────────────────────────────────────────────┐
│  Dash App (src/dashboard/app.py)                        │
│                                                         │
│  Data Layer                                             │
│    ├─ phoenix.Client() → spans DataFrame                │
│    ├─ results/*/metrics.json → metrics DataFrame        │
│    ├─ results/*/trace.json → turn-level data            │
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
```

---

## 2. Tab Specifications

### 2.1 Tab: Experiment Overview

**Purpose**: Entry point. Shows all experiment runs with key metadata and status.

**Data sources**: Phoenix spans (root AGENT spans) + `metrics.json` files from results directories.

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Runs table | Dash AG Grid | Columns: run_id, experiment_name, model, provider, status, total_turns, total_duration, total_tokens, total_cost_usd, accuracy (from metrics), timestamp. Sortable, filterable. Row click navigates to Trace Explorer tab for that run. |
| Summary cards | `dbc.Card` | Total runs, success rate, average accuracy, total cost, total tokens. Filterable by experiment name and date range. |
| Status distribution | Plotly pie chart | Completed / failed / timeout / cancelled breakdown. |

**Interactions**:
- Click row in AG Grid → Trace Explorer tab opens for that run
- Filter by experiment name, model, provider, date range, status
- Bulk select runs for side-by-side comparison

### 2.2 Tab: Metrics Comparison

**Purpose**: Compare quantitative performance across runs and models.

**Data sources**: `metrics.json` from results directories, enriched with token/cost from Phoenix spans.

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Accuracy bar chart | Plotly bar | X-axis: run_id or model name, Y-axis: overall accuracy. Color by provider. `customdata` carries run_id for click-through. |
| Per-column accuracy heatmap | Plotly heatmap | Rows: target columns, Columns: runs/models. Cell color: accuracy. Hover shows value. |
| Cost vs. accuracy scatter | Plotly scatter | X: total_cost_usd, Y: accuracy. Size: total_tokens. Color: model. Labels: run_id. |
| Token usage bar chart | Plotly grouped bar | Per-run breakdown of input vs. output tokens. |
| F1 / precision / recall radar | Plotly radar/spider | Per-column breakdown for selected runs (max 5). |
| Metrics summary table | Dash AG Grid | Full metrics detail with CSV export. |

**Interactions**:
- Click bar in accuracy chart → Trace Explorer tab opens for that run (via Dash callback on `clickData`)
- Select subset of runs via checkboxes or date range
- Toggle between "group by model" and "group by run"

### 2.3 Tab: Trace Explorer

**Purpose**: Deep-dive into a single experiment run. Shows span hierarchy, conversation turns, code executions, and token usage.

**Data sources**: Phoenix spans for the selected run + `trace.json` for raw conversation data.

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Run header | `dbc.Card` | Run ID, experiment name, model, provider, status, total duration, total tokens, total cost. Link to Phoenix UI trace view. |
| Span waterfall | Plotly Gantt/timeline | Horizontal bars showing span duration. Nested by parent-child. Color by span kind (AGENT=blue, CHAIN=green, LLM=orange, TOOL=purple). Click to expand details. |
| Turn accordion | `dbc.Accordion` | One item per turn. Each shows: user message, agent response, code executed (syntax-highlighted), code output, token counts, cost, duration. Expandable/collapsible. |
| Token usage per turn | Plotly bar | Stacked bar: input tokens (blue) + output tokens (orange) per turn number. |
| Cost per turn | Plotly line | Cumulative cost across turns. |
| Error indicators | Badge/alert | If any span has error status, show red badge on the turn and a summary alert. |

**Interactions**:
- Select run from dropdown (populated from Phoenix root spans)
- Click span in waterfall → accordion scrolls to that turn
- Click "Open in Phoenix" → opens Phoenix UI in new tab at `http://<phoenix_endpoint>/traces/{trace_id}`

### 2.4 Tab: Token & Cost Analysis

**Purpose**: Aggregate token usage and cost analysis across runs, models, and providers.

**Data sources**: Phoenix LLM spans aggregated by model/provider.

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Cost per model | Plotly bar | Total cost by model across all runs. |
| Tokens per model | Plotly grouped bar | Input vs. output tokens per model. |
| Cost vs. turns | Plotly scatter | X: number of turns, Y: total cost. One point per run. Color: model. |
| Token efficiency | Plotly scatter | X: total tokens, Y: accuracy. Shows which models achieve better accuracy with fewer tokens. |
| Cost breakdown table | Dash AG Grid | Per-run detail: run_id, model, input_tokens, output_tokens, prompt_cost, completion_cost, total_cost. Sortable. |
| Cost over time | Plotly line | Cumulative cost across experiments (X: date, Y: cumulative cost). Useful for budget tracking. |

### 2.5 Tab: Side-by-Side Comparison

**Purpose**: Compare two experiment runs turn-by-turn.

**Data sources**: Phoenix spans + `trace.json` for both selected runs.

**Components**:

| Component | Type | Details |
|-----------|------|---------|
| Run selectors | Two dropdowns | Select Run A and Run B. Dropdowns populated from Phoenix root spans. |
| Diff summary card | `dbc.Card` | Delta in: accuracy, total tokens, total cost, number of turns, duration. Green/red arrows for better/worse. |
| Synchronized turn accordions | Two-column layout | Left: Run A turns. Right: Run B turns. Aligned by turn number. Differences highlighted (e.g., different response_type, different code executed). Scrolling synchronized. |
| Metric comparison | Plotly grouped bar | Per-column accuracy side by side for the two runs. |
| Token comparison | Plotly grouped bar | Per-turn token usage side by side. |
| Timeline overlay | Plotly dual Gantt | Both span waterfalls overlaid with transparency, aligned by turn number. |

---

## 3. Data Loading Layer

### 3.1 `src/dashboard/data_loader.py`

```python
"""
Data loading for the Dash dashboard.
Queries Phoenix and reads local result files.
"""

class DashboardDataLoader:
    def __init__(self, phoenix_endpoint: str, results_base_dir: Path):
        self.client = px.Client(endpoint=phoenix_endpoint)
        self.results_dir = results_base_dir

    def get_all_runs(self) -> pd.DataFrame:
        """
        Get all experiment runs from Phoenix (root AGENT spans).
        Returns DataFrame with: run_id, experiment_name, model, provider,
        status, duration, total_input_tokens, total_output_tokens,
        total_cost, trace_type, parent_run_id, start_time.
        """

    def get_run_spans(self, run_id: str) -> pd.DataFrame:
        """Get all spans for a specific run, ordered by start time."""

    def get_run_metrics(self, run_id: str) -> Optional[dict]:
        """Load metrics.json for a run from its results directory."""

    def get_run_trace(self, run_id: str) -> Optional[dict]:
        """Load trace.json for a run from its results directory."""

    def get_run_config(self, run_id: str) -> Optional[dict]:
        """Load config_snapshot.yaml for a run."""

    def get_all_metrics(self) -> pd.DataFrame:
        """
        Aggregate metrics across all runs.
        Joins Phoenix span data with metrics.json data via run_id.
        """

    def get_token_summary(self, group_by: str = "model") -> pd.DataFrame:
        """
        Aggregate token/cost data grouped by model, provider, or experiment.
        """

    def find_results_dir(self, run_id: str) -> Optional[Path]:
        """Find the results directory containing the given run_id."""
```

### 3.2 Run ID to Results Directory Mapping

The results directory naming convention is `{experiment_name}_{timestamp}_{run_id}`. The loader scans `results/` for directories containing the 8-char run_id suffix and caches the mapping.

---

## 4. Application Structure

### File Layout

```
src/dashboard/
    __init__.py
    app.py                  # Main Dash app, layout, tab routing
    data_loader.py          # Phoenix + file data loading
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
.venv/bin/python -m src.dashboard.app \
    --phoenix-endpoint http://localhost:6006 \
    --results-dir results/ \
    --port 8050

# SLURM job (heavy interactive use)
srun --time=04:00:00 --mem=8G --cpus-per-task=2 --account=compgen \
    .venv/bin/python -m src.dashboard.app \
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

Add to project `.venv`:
```
dash>=2.14
dash-bootstrap-components>=1.5
dash-ag-grid>=2.3
plotly>=5.18
```

These are already compatible with Python 3.11.

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

### Live Data Refresh

The data loader caches results and refreshes on tab switch or explicit "Refresh" button click. No automatic polling — experiments are batch-oriented, not real-time.

---

## 7. Deployment Options

### Option A: Submit Node (default, lightweight)

```bash
screen -dmS harmonia-dashboard \
    .venv/bin/python -m src.dashboard.app --port 8050
```

Suitable for: browsing results, quick comparisons, < 100 runs loaded.

### Option B: SLURM Job (heavy interactive sessions)

```bash
srun --job-name=harmonia-dashboard --account=compgen \
    --time=04:00:00 --mem=8G --cpus-per-task=2 \
    .venv/bin/python -m src.dashboard.app --port 8050
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
| `src/dashboard/data_loader.py` | Phoenix + file data loading |
| `src/dashboard/tabs/__init__.py` | Tab package init |
| `src/dashboard/tabs/overview.py` | Experiment Overview tab |
| `src/dashboard/tabs/metrics.py` | Metrics Comparison tab |
| `src/dashboard/tabs/trace_explorer.py` | Trace Explorer tab |
| `src/dashboard/tabs/token_cost.py` | Token & Cost Analysis tab |
| `src/dashboard/tabs/comparison.py` | Side-by-Side Comparison tab |
| `src/dashboard/components/__init__.py` | Components package init |
| `src/dashboard/components/span_waterfall.py` | Span waterfall Plotly chart |
| `src/dashboard/components/turn_accordion.py` | Turn accordion component |
| `src/dashboard/components/run_table.py` | AG Grid run table config |
| `src/dashboard/components/diff_card.py` | Comparison diff summary |
| `scripts/dashboard.sh` | Dashboard start/stop convenience script |

### Modified Files

None — the dashboard is a new standalone module.

---

## 10. Testing Plan

1. **Data loading**: Verify `DashboardDataLoader` correctly queries Phoenix and reads results files. Test with 3+ runs from different models.

2. **Tab rendering**: Each tab renders without errors when data is available. Test with: 0 runs (empty state), 1 run, 10+ runs.

3. **Click-through**: Click accuracy bar → Trace Explorer opens with correct run. Verify `customdata` propagation.

4. **Comparison**: Select two runs → side-by-side view aligns turns correctly. Test with runs of different turn counts.

5. **SLURM deployment**: Launch as SLURM job, verify port forwarding works from local machine.

6. **Performance**: Load 50+ runs, verify AG Grid and plots remain responsive. If slow, add pagination to AG Grid and lazy-loading for trace data.
