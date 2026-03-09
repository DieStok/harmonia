# Implementation Plan: Custom Dash Dashboard for LLM Agent Tracing

**Date**: 2026-03-03
**Status**: Proposed
**Estimated effort**: 7-9 developer-days

---

## 1. Framework Functionality Mapping

### 1.1 Dash Components and Data Model

The dashboard consumes two primary JSON artifacts per run, already produced by the existing pipeline:

| Artifact | Producer | Key fields consumed |
|----------|----------|---------------------|
| `trace.json` | `TraceLogger` in `src/automation/logger.py` | `experiment`, `llm`, `timing`, `status`, `error_message`, `turns[]` (each with `turn`, `user_message`, `agent_response`, `response_type`, `tool_calls`, `duration_seconds`, `raw_messages`, `timestamp`) |
| `metrics.json` | `src/evaluation/` pipeline | `column_mapping` (accuracy, precision, recall, per-column details), `column_values` (per-column F1/accuracy), `overall_summary` |
| `full_prompt_composition.json` | `src/prompt_logging.py` | `metadata`, `layers`, `messages_sent_to_llm`, `summary` |

The Dash app loads these files on startup via a data-loading module that walks `results/` directories matching the existing `RESULTS_FOLDER_PATTERN` regex from the log analyzer. Each discovered run becomes a row in an in-memory Pandas DataFrame (the "run index").

Component mapping:

| View | Primary Dash component | Data consumed |
|------|----------------------|---------------|
| Run overview table | `dash_ag_grid.AgGrid` | Run index DataFrame (one row per results directory) |
| Metrics bar charts | `dcc.Graph` with Plotly bar/grouped-bar | `metrics.json` aggregated across runs |
| Turn-by-turn trace viewer | `dbc.Accordion` with `dbc.AccordionItem` per turn | `trace.json` `turns[]` |
| Code execution detail | `dcc.Markdown` inside accordion items | Extracted `beaker__execute_input` / `execute_result` / `error` from `raw_messages` |
| Latency waterfall | `dcc.Graph` with Plotly Gantt/timeline | `turns[].duration_seconds` and `turns[].timestamp` |
| Side-by-side comparison | Two-column `dbc.Row`/`dbc.Col` layout | Two selected `trace.json` files |
| Prompt composition viewer | `dbc.Card` with collapsible sections | `full_prompt_composition.json` layers |

### 1.2 Dashboard Views

**View 1 -- Run Overview (landing page).** AG Grid table showing all discovered runs with columns: run_id, experiment_name, model, provider, status, total_duration, turn_count, column_mapping_accuracy, avg_value_f1, total_tokens, estimated_cost. Sortable and filterable. Row click navigates to the trace viewer for that run.

**View 2 -- Metrics Explorer.** Plotly bar charts reproducing the current `visualize_metrics_cli.py` output interactively: column mapping accuracy by model, value F1 by model, per-column heatmap. Each bar is clickable (via `clickData` callback) to jump to the trace viewer for that specific run.

**View 3 -- Trace Viewer.** Single-run deep dive. Header card shows run metadata (model, provider, timing, status, token/cost summary). Below: accordion of turns. Each turn expands to show user message, agent response, extracted code cells (syntax-highlighted via `dcc.Markdown` with fenced code blocks), execution output, errors, and timing. A latency waterfall chart at the top shows per-turn duration.

**View 4 -- Side-by-Side Comparison.** Two run selectors (dropdowns populated from the run index). Below: two-column layout with synchronized turn-by-turn accordions. A diff summary card at the top highlights which turns diverged in response type, duration, or error status.

### 1.3 Data Persistence

No database. The Dash app reads JSON files from `results/` at startup, building the run index DataFrame in memory. A "Refresh" button re-scans the directory. This aligns with the HPC file-based constraint.

### 1.4 Logger Enrichment Requirements

The existing `trace.json` lacks token counts, cost, structured tool calls, and model parameters. These must be added to `logger.py` so the dashboard can display them. The changes are detailed in Section 2.1 below. Critically, all new fields are **optional with defaults** so that existing trace files remain loadable; the dashboard gracefully shows "N/A" for missing fields.

---

## 2. Codebase Integration -- Complete Change Specification

### 2.1 Core Tracing Instrumentation (enriching existing logger.py)

**File: `src/automation/logger.py`**

**(a) Extend `TurnRecord` dataclass:**

Add optional fields (all with defaults so existing traces deserialize correctly):

```python
@dataclass
class TurnRecord:
    # ... existing fields ...
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    model_parameters: dict = field(default_factory=dict)  # temperature, top_p, etc.
    code_cells: list[dict] = field(default_factory=list)   # extracted from raw_messages
    code_outputs: list[dict] = field(default_factory=list)  # extracted from raw_messages
    code_errors: list[dict] = field(default_factory=list)   # extracted from raw_messages
```

**(b) Extend `ExperimentTrace` dataclass:**

```python
@dataclass
class ExperimentTrace:
    # ... existing fields ...
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    config_snapshot: dict = field(default_factory=dict)  # copy of experiment YAML
```

Update `to_dict()` to serialize the new fields and update `end_experiment()` to sum token/cost totals from turns.

**(c) Extend `TraceLogger.log_turn()` signature:**

Add keyword arguments `input_tokens`, `output_tokens`, `cost_usd`, `model_parameters` passed through to `TurnRecord`.

**(d) Add `extract_code_spans()` helper (new function):**

Parses `raw_messages` list to extract structured code cells, outputs, and errors from `beaker__execute_input`, `execute_result`, `stream`, and `error` msg_types. Called inside `log_turn()` to populate the new `code_cells`/`code_outputs`/`code_errors` fields automatically.

```python
def extract_code_spans(raw_messages: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Extract structured code execution data from raw Beaker WebSocket messages."""
```

**File: `src/automation/run_experiment.py`** (or wherever `log_turn` is called)

Pass token counts from the LLM response to `log_turn()`. The exact source depends on the provider: OpenRouter returns usage in the response headers/body; Ollama returns it in the response JSON. This requires extracting usage data from the Archytas/Beaker agent response before logging.

**File: `src/prompt_logging.py`** -- No changes needed. The existing `full_prompt_composition.json` is consumed as-is.

### 2.2 Dashboard Application Code (new files)

All new files live under `src/dashboard/`.

**File: `src/dashboard/__init__.py`** -- Empty package init.

**File: `src/dashboard/app.py`** -- Main Dash application entry point.

- `create_app(results_dir: Path, port: int = 8050) -> dash.Dash`: Factory function. Creates the Dash app, registers layout and callbacks, returns the app instance.
- `main()`: CLI entry point. Parses `--results-dir`, `--port`, `--host` arguments, calls `create_app()`, runs `app.run(debug=False, host=host, port=port)`.

Dependencies: `dash >= 2.17`, `dash-bootstrap-components >= 1.6`, `dash-ag-grid >= 31.0`, `plotly >= 5.22`, `pandas`.

**File: `src/dashboard/data_loading.py`** -- Data ingestion from results directories.

- `discover_runs(results_dir: Path) -> pd.DataFrame`: Walks results directories, loads `trace.json` and `metrics.json` from each, builds the run index DataFrame. Reuses the `RESULTS_FOLDER_PATTERN` regex from the log analyzer.
- `load_trace(results_dir: Path, run_id: str) -> dict`: Loads and returns the full `trace.json` for a given run.
- `load_metrics(results_dir: Path, run_id: str) -> dict`: Loads `metrics.json`.
- `load_prompt_composition(results_dir: Path, run_id: str) -> dict | None`: Loads `full_prompt_composition.json` if present.
- `extract_code_from_raw_messages(raw_messages: list[dict]) -> list[dict]`: Extracts structured code cell data. Delegates to `logger.extract_code_spans()` if available, otherwise performs its own extraction for backward compatibility with old traces.

**File: `src/dashboard/layouts.py`** -- Page layouts as functions returning Dash component trees.

- `overview_layout(run_index_df: pd.DataFrame) -> html.Div`: AG Grid table with filter row, plus summary statistics cards (total runs, success rate, avg accuracy).
- `metrics_layout() -> html.Div`: Placeholder `dcc.Graph` components for bar charts and heatmap, plus dropdown selectors for metric type and grouping.
- `trace_viewer_layout() -> html.Div`: Run metadata card, latency waterfall graph, accordion container for turns.
- `comparison_layout(run_options: list[dict]) -> html.Div`: Two dropdown selectors, two-column turn accordion containers, diff summary card.

**File: `src/dashboard/callbacks.py`** -- All Dash callback registrations.

- `register_callbacks(app: dash.Dash, results_dir: Path)`: Master registration function called by `create_app()`. Contains:
  - `update_metrics_charts(metric_selection, group_by)`: Callback for metrics explorer. Returns updated Plotly figures.
  - `navigate_to_trace(click_data, cell_clicked)`: Callback triggered by bar chart `clickData` or AG Grid row click. Extracts run_id, redirects to trace viewer tab.
  - `render_trace(run_id)`: Callback that loads trace.json, builds the turn accordion, latency waterfall, and metadata card.
  - `render_comparison(run_id_left, run_id_right)`: Callback that loads two traces and renders them side by side.
  - `refresh_data(n_clicks)`: Re-scans results directory and updates the run index store.

- Uses `dcc.Store` for client-side state (selected run_id, run index JSON).
- Uses `dcc.Tabs` for navigation between the four views.

**File: `src/dashboard/components.py`** -- Reusable component builders.

- `build_turn_accordion(turns: list[dict], run_id: str) -> dbc.Accordion`: Builds expandable turn items with syntax-highlighted code, output, and error sections.
- `build_metadata_card(trace: dict) -> dbc.Card`: Run header card with model, provider, timing, token/cost summary.
- `build_latency_waterfall(turns: list[dict]) -> dcc.Graph`: Plotly horizontal bar chart of per-turn duration.
- `build_code_block(code: str, language: str = "python") -> dcc.Markdown`: Fenced code block rendering.

### 2.3 Configuration and Setup

**File: `src/dashboard/requirements.txt`** (new)

```
dash>=2.17
dash-bootstrap-components>=1.6
dash-ag-grid>=31.0
plotly>=5.22
pandas>=2.0
```

**File: `run_dashboard.sh`** (new, project root) -- Convenience wrapper.

```bash
#!/bin/bash
# Launch the Harmonia tracing dashboard
# Usage: ./run_dashboard.sh [--port PORT]
cd "$(dirname "$0")"
.venv/bin/python -m src.dashboard.app \
    --results-dir results/ \
    --port "${1:-8050}" \
    --host 0.0.0.0
```

**File: `run_dashboard_slurm.sh`** (new) -- SBATCH script for running the dashboard as a SLURM job.

```bash
#!/bin/bash
#SBATCH --job-name=harmonia_dashboard
#SBATCH --account=compgen
#SBATCH --time=08:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/dashboard_%j.out

PORT=8050
echo "Dashboard starting on $(hostname):${PORT}"
echo "SSH tunnel: ssh -L ${PORT}:$(hostname):${PORT} <user>@hpcs05"
./run_dashboard.sh --port $PORT
```

---

## 3. Visualisation and Cross-Referencing with Metrics

### 3.1 Unified Dashboard Architecture

The app uses `dcc.Tabs` with four tabs (Overview, Metrics, Trace Viewer, Comparison). A `dcc.Store(id="run-index-store")` holds the serialized run index DataFrame as JSON, populated on load and refreshable. A second `dcc.Store(id="selected-run-store")` tracks the currently selected run_id, enabling cross-tab navigation.

Bootstrap theme (`dbc.themes.FLATLY`) provides consistent styling. The layout skeleton:

```
dbc.Container([
    dbc.NavbarSimple(brand="Harmonia Trace Dashboard"),
    dcc.Store(id="run-index-store"),
    dcc.Store(id="selected-run-store"),
    dcc.Tabs(id="main-tabs", children=[
        dcc.Tab(label="Overview",   children=[overview_layout(...)]),
        dcc.Tab(label="Metrics",    children=[metrics_layout()]),
        dcc.Tab(label="Trace",      children=[trace_viewer_layout()]),
        dcc.Tab(label="Comparison", children=[comparison_layout(...)]),
    ])
])
```

### 3.2 Click-Through from Metrics to Traces

The metrics bar charts use Plotly's `clickData` property. The callback pattern:

```python
@app.callback(
    Output("main-tabs", "value"),
    Output("selected-run-store", "data"),
    Input("accuracy-bar-chart", "clickData"),
    prevent_initial_call=True,
)
def on_bar_click(click_data):
    if not click_data:
        raise PreventUpdate
    # customdata[0] contains the run_id, embedded when building the figure
    run_id = click_data["points"][0]["customdata"][0]
    return "Trace", run_id
```

The trace viewer tab has a callback on `selected-run-store` that triggers `render_trace()`, loading the full trace.json and building the accordion. This creates a seamless flow: click a model's accuracy bar, land on its full conversation trace.

### 3.3 Side-by-Side Trace Comparison

The comparison tab renders two `dbc.Col(width=6)` columns. Each column contains an independent turn accordion built from a different trace. A diff summary card at the top computes:

- Turn count difference
- Total duration difference
- Status match/mismatch
- Per-turn duration delta (highlighted if > 2x)
- Token/cost comparison (when available)

Turn alignment is by turn number (both experiments use the same scripted prompts in automated mode, so turns correspond 1:1). For runs with different turn counts, missing turns show a placeholder card.

### 3.4 Deployment

**Interactive on HPC via SSH port forwarding:**

1. Submit `run_dashboard_slurm.sh` via `sbatch`. The job prints the hostname and port.
2. From local machine: `ssh -L 8050:<compute-node>:8050 user@hpcs05`.
3. Open `http://localhost:8050` in a local browser.

**No static export.** Dash requires a running server; there is no HTML-only export mode. This is an inherent limitation documented in the research report. If offline sharing is needed, the existing `visualize_metrics_cli.py` generates static PNG/HTML plots for metrics; the dashboard is complementary, not a replacement.

**Resource footprint.** The Dash server is lightweight (single process, < 1 GB RAM). A 4G memory reservation is conservative. The SLURM job can run for up to 8 hours, sufficient for an analysis session.

---

## 4. Effort Estimate and Risks

### 4.1 Effort Breakdown

| Task | Days | Details |
|------|------|---------|
| Logger enrichment (`logger.py` + call sites) | 1.5 | Add token/cost/code fields to `TurnRecord`, `ExperimentTrace`, extract code spans, wire token extraction from provider responses |
| Data loading module | 1.0 | `data_loading.py`: directory scanning, trace/metrics loading, backward-compatible parsing of old traces without new fields |
| Dashboard layout and components | 2.0 | `layouts.py`, `components.py`: AG Grid table, turn accordion, code rendering, latency waterfall, metadata cards |
| Callbacks and interactivity | 1.5 | `callbacks.py`: metrics charts, click-through navigation, trace rendering, comparison rendering, refresh logic |
| SLURM integration and testing | 0.5 | `run_dashboard.sh`, `run_dashboard_slurm.sh`, SSH tunnel testing, dependency installation into `.venv` |
| End-to-end testing with real data | 0.5 | Load actual results directories, verify all views render correctly, test backward compatibility with old traces |
| **Total** | **7.0** | |

Buffer for unforeseen issues (token extraction varies by provider, raw_messages parsing edge cases): +1-2 days, giving a realistic range of **7-9 developer-days**.

### 4.2 Top 3 Technical Risks

**Risk 1: Token count extraction is provider-dependent.**
OpenRouter, Ollama, and other providers return usage metadata in different formats and at different levels (per-request vs. per-stream-chunk). The Archytas/Beaker agent layer may not expose raw provider responses to the orchestrator.
*Mitigation:* Start with OpenRouter (which returns `usage` in the response body via the OpenAI-compatible API). Add a provider-specific adapter pattern in `logger.py`. For providers that do not expose token counts, leave fields as `None` and display "N/A" in the dashboard. Do not block the dashboard on full provider coverage.

**Risk 2: Large results directories cause slow startup.**
A results directory with hundreds of runs, each containing 200-300KB trace files, means loading 50-100MB of JSON at startup.
*Mitigation:* Build a lightweight index on first scan that caches only top-level metadata (experiment name, model, status, timing, metrics summary) and defer full trace loading to on-demand callbacks. Store the index as `.dashboard_cache.json` in the results directory; invalidate by checking directory mtime.

**Risk 3: Raw message parsing fragility.**
The `raw_messages` structure is dictated by Beaker/Jupyter protocol internals and has no stability guarantee. The `extract_code_spans()` function depends on specific `msg_type` values (`beaker__execute_input`, `execute_result`, `stream`, `error`).
*Mitigation:* Wrap extraction in try/except per message, skip unparseable messages gracefully, and log warnings. Write targeted unit tests against real raw_messages samples from existing trace files to detect regressions when Beaker is updated.

### 4.3 Limitations Requiring Custom Workarounds

1. **No static HTML export for Dash.** Unlike Plotly figures (which support `write_html`), the full Dash app requires a running Python server. Workaround: for offline sharing, the dashboard includes a "Export current view" button that serializes the currently displayed trace/metrics into a standalone Plotly HTML file using `plotly.io.to_html()`. This covers charts but not the interactive table or accordion.

2. **No built-in annotation/evaluation framework.** Unlike Langfuse or Phoenix, Dash has no concept of human annotations or LLM-as-judge evaluations. Workaround: add a simple "Notes" text area per run in the trace viewer that writes to a `annotations.json` sidecar file in the results directory. This is minimal but sufficient for qualitative notes.

3. **Backward compatibility with existing traces.** Existing `trace.json` files lack the new fields (tokens, cost, code_cells). The data loading layer must handle both old and new formats. Workaround: all new `TurnRecord` fields have `None`/empty defaults; `data_loading.py` uses `.get()` with fallbacks; the dashboard renders "N/A" for missing data. No migration of old files is required.
