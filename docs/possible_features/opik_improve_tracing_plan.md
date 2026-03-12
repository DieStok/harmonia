# Implementation Plan: Opik Integration for Harmonia Tracing and Observability

**Date**: 2026-03-03
**Status**: Plan (not yet implemented)
**Input**: `docs/possible_features/03_03_2026_research_into_LLM_tracing.md`

---

## 1. Framework Functionality Mapping

### 1.1 Trace Capture and Data Model

Opik organises telemetry into a two-level hierarchy: **Traces** contain ordered **Spans**. Each span carries a `type` field drawn from four values: `general`, `tool`, `llm`, and `guardrail`. The `llm` span type has first-class fields for `input_tokens`, `output_tokens`, `total_tokens`, and `cost` -- exactly the token/cost accounting that Harmonia currently lacks. A trace object holds top-level metadata (project name, tags, timestamps, feedback scores) and acts as the container that groups all spans for a single experiment run.

Mapping to Harmonia's current data model:

| Harmonia concept | Opik equivalent |
|---|---|
| `ExperimentTrace` (one run) | One Opik `Trace` with metadata tags for run_id, experiment_name, model, provider |
| `TurnRecord` (one conversation turn) | One `general` span (parent) containing child spans |
| LLM API call within a turn | `llm` child span with token counts, model parameters, cost |
| Beaker code execution | `tool` child span with input code, stdout/stderr, status |
| Retry attempts | Sibling `llm` spans under the same parent, tagged `retry=N` |
| `full_prompt_composition.json` | Metadata/input field on the first `llm` span of the trace |

The Python SDK offers three instrumentation modes: (a) `@track` decorator for automatic span creation, (b) `client.trace()` / `trace.span()` low-level API for manual control, and (c) context managers that propagate parent-child relationships. Because Harmonia's logging happens across `ExperimentRunner._run_turn()`, `ManualExperimentRunner._handle_message()`, and `BeakerClient.send_message()` -- none of which are simple decorated functions -- the low-level `client.trace()` / `trace.span()` API is the correct integration point.

### 1.2 GUI and Visualization Layer

The Opik web UI (port 5173) provides:

- **Trace table**: Filterable list of all traces with OQL (Opik Query Language) for searching by tags, status, duration, cost. Maps directly to "find all runs for model X with status failed."
- **Single-trace drill-down**: Tree view of spans within a trace, showing the parent-child hierarchy, timing waterfall, input/output data, and token counts. This addresses the P0 requirement for a turn-by-turn trace viewer with expandable details.
- **Experiment comparison / leaderboard**: Side-by-side tabular comparison of experiment runs scored on configurable metrics. This partially addresses the side-by-side comparison requirement, though it compares aggregate scores rather than individual trace turns.
- **Dashboard templates**: Pre-built views for token usage, cost, latency distributions.
- **CSV/JSON export**: From UI and from `opik export` CLI.

What the GUI does **not** provide: click-through from external Plotly/seaborn charts (like those from `visualize_metrics_cli.py`) into Opik traces, and true side-by-side turn-level trace diff. These require custom bridging (see Section 3).

### 1.3 Data Persistence and HPC Constraints

Opik self-hosted requires ClickHouse, MySQL, Redis, MinIO, and Zookeeper -- eight containers total via Docker Compose. This is the heaviest infrastructure of any evaluated framework and poses the main deployment challenge on HPC.

**Deployment strategy**: Run the Opik stack as an Apptainer-based service on a dedicated SLURM interactive session or long-running job. The existing codebase already runs Beaker inside Apptainer (`exec_apptainer_harmonia.sh`), so the pattern is established. The Opik stack would run on a submit/transfer node (or a dedicated SLURM allocation) and persist data in `$HOME/opik` or `/hpc/compgen/users/dstoker/opik_data/`. Experiment jobs connect to it via HTTP -- the Opik Python SDK posts traces to `http://<opik-host>:5173/api`. If the Opik server is down, the SDK must fail gracefully without blocking the experiment (see Section 4, Risk 1).

Alternative: Use Opik's managed cloud (app.comet.com/opik) and avoid self-hosting entirely. This requires outbound HTTPS from compute nodes, which is available for OpenRouter calls already. The trade-off is data leaving the HPC; acceptable for experiment metadata but potentially not for patient-derived data.

### 1.4 SDK Integration Points

The `opik` Python package (`pip install opik`) provides:

- `opik.Opik()` client -- configurable via `OPIK_URL_OVERRIDE` and `OPIK_API_KEY` env vars.
- `client.trace(name, input, metadata, tags)` -- creates a trace, returns a `Trace` object.
- `trace.span(name, type, input, output, metadata)` -- creates a child span.
- `span.end(output, usage, metadata)` -- finalises a span with output data and token usage.
- `trace.end(output, metadata)` -- finalises the trace.
- `client.search_traces()`, `client.search_spans()` -- programmatic export.

All methods are synchronous (the SDK batches and flushes in a background thread), so they can be called from both sync and async code without blocking the event loop.

---

## 2. Codebase Integration -- Complete Change Specification

### 2a. Core Tracing Instrumentation

**File 1: `src/automation/opik_tracing.py` (NEW)**

New module encapsulating all Opik SDK interaction. This isolates the Opik dependency so the rest of the codebase can function without it installed.

```python
class HarmoniaOpikTracer:
    """Wraps Opik SDK to provide Harmonia-specific tracing."""

    def __init__(self, project_name: str = "harmonia")
    def start_trace(self, run_id: str, experiment_name: str, model: str,
                    provider: str, config_metadata: dict) -> None
    def start_turn_span(self, turn: int, user_message: str) -> None
    def log_llm_span(self, model: str, input_messages: list, output: str,
                     input_tokens: int, output_tokens: int, cost: float,
                     model_parameters: dict, duration_seconds: float) -> None
    def log_tool_span(self, tool_name: str, input_code: str, output: str,
                      status: str, duration_seconds: float) -> None
    def end_turn_span(self, agent_response: str, response_type: str,
                      duration_seconds: float) -> None
    def end_trace(self, status: str, error_message: str = None,
                  total_duration: float = 0.0) -> None
    def flush(self) -> None
```

Dependencies: `opik` (added to `.venv` via `pip install opik`). Graceful degradation: if `import opik` fails, all methods become no-ops and print a single warning.

**File 2: `src/automation/logger.py` (MODIFIED)**

Changes to `TraceLogger`:
- `__init__()`: Accept optional `opik_tracer: HarmoniaOpikTracer` parameter. Store as `self._opik`.
- `start_experiment()`: Call `self._opik.start_trace(...)` with experiment metadata.
- `log_turn()`: Call `self._opik.start_turn_span()`, then `self._opik.end_turn_span()`. Pass `raw_messages` through a new helper `_extract_structured_spans(raw_messages)` that parses WebSocket messages into `llm` and `tool` child spans.
- `end_experiment()`: Call `self._opik.end_trace(...)`.
- New private method `_extract_structured_spans(raw_messages: list[dict]) -> list[dict]`: Parses `raw_messages` to identify `beaker__execute_input` (tool invocations), `execute_result`/`stream`/`error` (tool outputs), and `llm_response` (LLM replies). Returns structured span data for each. This also fills in the currently-dead `tool_calls` field on `TurnRecord`.

Changes to `TurnRecord`:
- Add fields: `input_tokens: int = 0`, `output_tokens: int = 0`, `cost_usd: float = 0.0`, `model_parameters: dict = field(default_factory=dict)`.
- Update `ExperimentTrace.to_dict()` to include these new fields.

**File 3: `src/automation/runner.py` (MODIFIED)**

Changes to `ExperimentRunner.__init__()`:
- Instantiate `HarmoniaOpikTracer` (guarded by try/except ImportError).
- Pass it to `TraceLogger(output_dir, opik_tracer=tracer)`.

Changes to `ExperimentRunner._run_turn()`:
- After `self.client.send_message()` returns, pass the `AgentResponse.raw_messages` through the new `_extract_structured_spans()` pipeline before logging.
- For each identified LLM sub-call in `raw_messages`, call `opik_tracer.log_llm_span()`.
- For each identified code execution, call `opik_tracer.log_tool_span()`.

**File 4: `src/automation/manual_runner.py` (MODIFIED)**

Changes to `ManualExperimentRunner.__init__()`:
- Same pattern as `ExperimentRunner`: instantiate `HarmoniaOpikTracer`, pass to `TraceLogger`.

Changes to `ManualExperimentRunner._handle_message()`:
- When finalising a turn (on `llm_response`, `code_cell`, or `error` msg_type), call the same span-extraction and Opik logging methods.

**File 5: `src/automation/client.py` (MODIFIED)**

Changes to `BeakerClient.send_message()`:
- After constructing `AgentResponse`, attempt to extract token usage from `raw_messages`. Look for `llm_response` messages that may contain `usage` fields (depends on Beaker/Archytas surfacing this data). Store in `AgentResponse`.

Changes to `AgentResponse`:
- Add fields: `input_tokens: int = 0`, `output_tokens: int = 0`.

**File 6: `src/prompt_logging.py` (MODIFIED)**

Changes to `register_prompt_json_logger()`:
- In the `logging_execute_wrapper`, after building the composition dict, also call `opik_tracer.log_llm_span()` for the first LLM invocation with the full prompt composition as input metadata. Requires receiving the tracer instance (pass via closure or env-based singleton).

### 2b. Data Export and Persistence

**File 7: `src/automation/opik_export.py` (NEW)**

Utility to export Opik traces back to the existing file-based format for backward compatibility with the log analysis CLI.

```python
def export_trace_to_json(opik_client, run_id: str, output_path: Path) -> Path:
    """Fetch trace from Opik and write as trace.json in existing format."""

def enrich_metrics_with_cost(opik_client, run_id: str, metrics_path: Path) -> None:
    """Add token_count and cost_usd fields to an existing metrics.json."""
```

This ensures that `read_and_analyze_logs_and_traces_cli.py` continues to work unchanged against file-based traces, while Opik provides the richer queryable store.

**File 8: `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` (MODIFIED)**

Minimal change: add an optional `--opik` flag that, when present, queries Opik via `client.search_traces()` instead of scanning the filesystem. The existing Pydantic output schema is preserved.

### 2c. Configuration and Setup

**File 9: `src/automation/config.py` (MODIFIED)**

Add a new dataclass:

```python
@dataclass
class OpikConfig:
    enabled: bool = False
    server_url: str = "http://localhost:5173"
    project_name: str = "harmonia"
    api_key: Optional[str] = None  # for cloud mode
```

Add `opik: OpikConfig` field to `ExperimentConfig`. Update `from_dict()` to parse `opik:` section from YAML.

**File 10: Experiment YAML configs (MODIFIED)**

Add optional `opik:` section to experiment configs:

```yaml
opik:
  enabled: true
  server_url: "http://localhost:5173"
  project_name: "harmonia"
```

**File 11: `opik_infra/docker-compose.yml` (NEW)**

Copy of the official Opik Docker Compose file with volume mounts pointed at `/hpc/compgen/users/dstoker/opik_data/`. Accompanied by a helper script `opik_infra/start_opik.sh` that wraps the Apptainer execution.

**File 12: `.venv` requirements update**

Add `opik>=1.0` to the project's dependency specification. The SDK is a pure-Python package with minimal transitive dependencies.

---

## 3. Visualisation and Cross-Referencing with Metrics

### 3.1 Unified Dashboard Architecture

The system will have two complementary visualization layers:

1. **Opik web UI** (port 5173): Primary interface for trace exploration, span drill-down, token/cost dashboards, and experiment leaderboard. Accessed via SSH port forwarding from the HPC (`ssh -L 5173:opik-node:5173`).

2. **Existing `visualize_metrics_cli.py`** (Plotly/seaborn): Continues to generate accuracy/F1 bar charts, heatmaps, and confusion matrices from `metrics.json` files. Enhanced with a link column.

### 3.2 Click-Through from Metrics to Traces

Modify `src/evaluation/visualization/plots.py` function `plot_global_bars()` and related functions:

- When generating Plotly (interactive) output, embed Opik trace URLs as `customdata` on each bar. The URL format is `http://<opik-host>:5173/<project>/traces/<trace_id>`.
- Add `on_click` JavaScript callback that opens the Opik trace in a new browser tab.
- The `trace_id` is resolved by matching `run_id` from the metrics file to the Opik trace tag. This lookup is performed by `opik_export.py`'s `build_run_id_to_trace_id_map()` function.

For seaborn (static) output, embed the trace URL in the figure title or annotation (no interactivity possible in PNG).

### 3.3 Side-by-Side Trace Comparison

Opik's experiment comparison view compares aggregate scores across runs in a leaderboard table. For turn-level side-by-side comparison (a P0 requirement), a lightweight custom solution is needed:

Add `src/evaluation/visualization/trace_compare.py` (NEW):

```python
def generate_side_by_side_html(
    run_ids: list[str],
    opik_client,
    output_path: Path,
) -> Path:
    """Generate an HTML page with two traces displayed side by side."""
```

This fetches spans for each trace via `opik_client.search_spans()`, renders them in a two-column HTML layout with aligned turn numbers, and highlights differences in response content and timing. The output is a self-contained HTML file viewable via SSH port-forwarded browser.

### 3.4 GUI Deployment

The Opik UI is bundled with the server and requires no separate deployment. Access pattern:

1. Start Opik server via `opik_infra/start_opik.sh` on the HPC (SLURM allocation or persistent node).
2. From the local machine: `ssh -L 5173:<opik-node>:5173 user@hpc`.
3. Open `http://localhost:5173` in browser.

This mirrors the existing Beaker access pattern (SSH port-forward to port 8100).

---

## 4. Effort Estimate and Risks

### 4.1 Implementation Effort

| Task | Developer-days |
|---|---|
| `opik_tracing.py` + `opik_export.py` (new modules) | 2 |
| `logger.py` + `client.py` modifications (span extraction from raw_messages) | 2 |
| `runner.py` + `manual_runner.py` integration | 1 |
| `config.py` + YAML config updates | 0.5 |
| Opik infrastructure setup (Docker Compose to Apptainer, storage, startup scripts) | 2 |
| Click-through from Plotly charts to Opik traces | 1 |
| Side-by-side HTML trace comparison tool | 1.5 |
| Testing and validation across automated + manual experiment modes | 2 |
| **Total** | **12 developer-days** |

### 4.2 Top 3 Technical Risks

**Risk 1: Opik server unavailability during experiment runs.**
The Opik server runs as a separate SLURM job or on a shared node. If it goes down (OOM, SLURM preemption, network partition), trace submission fails. **Mitigation**: The `HarmoniaOpikTracer` must catch all SDK exceptions and fall through to no-op behavior. The existing file-based `trace.json` output remains the primary record; Opik is an enrichment layer, not a replacement. Add a `_fallback_buffer: list[dict]` that queues failed submissions for retry on `flush()`.

**Risk 2: Eight-container infrastructure overhead on HPC without Docker.**
The Opik stack requires ClickHouse, MySQL, Redis, MinIO, Zookeeper, plus three application containers. Running these inside Apptainer requires converting Docker Compose to individual Apptainer instances with shared networking -- a non-trivial systems engineering task. **Mitigation**: Phase 1 uses Opik cloud (app.comet.com/opik) with the `OPIK_API_KEY` env var, avoiding self-hosting entirely. Phase 2 explores Apptainer-ised deployment only if the cloud tier's data-residency constraints are unacceptable. Alternatively, evaluate whether a single-container "opik-all-in-one" build is feasible.

**Risk 3: Token counts not available from Archytas/Beaker.**
Opik's primary value-add is token/cost tracking, but the current Beaker WebSocket protocol does not surface `usage` data (input_tokens, output_tokens) from the underlying LLM API calls. Archytas handles LLM calls internally and does not expose token counts in its responses. **Mitigation**: For OpenRouter models, query the OpenRouter `/api/v1/generation` endpoint post-hoc to retrieve token usage by request ID. For Ollama models, the response body includes `eval_count` and `prompt_eval_count` -- patch the Archytas model wrapper to propagate these through a new `_usage_metadata` field on WebSocket messages. This is the highest-risk item because it may require upstream changes to Archytas.

### 4.3 Limitations Requiring Custom Workarounds

1. **No turn-level diff view**: Opik's experiment comparison is aggregate-level. The `trace_compare.py` HTML generator described in Section 3.3 is a custom workaround.

2. **No native integration with `visualize_metrics_cli.py`**: The click-through from Plotly charts to Opik traces (Section 3.2) requires custom JavaScript callbacks and a run-to-trace-ID mapping layer.

3. **No SQLite/file-based backend**: Unlike Phoenix, Opik has no lightweight single-process mode. Every deployment requires the full container stack or cloud access. This makes "quick local testing" cumbersome -- developers must either have the Opik server running or work with Opik disabled (file-only mode).

4. **Backward compatibility with log analysis CLI**: The existing `read_and_analyze_logs_and_traces_cli.py` reads file-based traces. Even with Opik, the file-based `trace.json` must continue to be written so that the CLI tool works without an Opik server dependency. This means dual-write (files + Opik) is permanent, not transitional.
