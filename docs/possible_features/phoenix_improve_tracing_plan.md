# Implementation Plan: Arize Phoenix Integration for Harmonia Tracing

**Date**: 2026-03-03
**Status**: Proposed
**Estimated effort**: 8--12 developer-days

---

## 1. Framework Functionality Mapping

### 1.1 Trace Capture and Data Model

Phoenix uses OpenTelemetry (OTel) as its wire format and the **OpenInference** semantic conventions to give LLM-specific meaning to spans. The data model is hierarchical:

- **Trace**: one top-level unit of work, identified by a 128-bit trace ID. In Harmonia, one trace = one experiment run.
- **Span**: a timed operation within a trace. Spans nest via parent-child links. Phoenix defines 10 span kinds via the `openinference.semconv` attribute `openinference.span.kind`: `AGENT`, `LLM`, `TOOL`, `CHAIN`, `RETRIEVER`, `EMBEDDING`, `RERANKER`, `GUARDRAIL`, `EVALUATOR`, `UNKNOWN`.
- **Span attributes**: key-value pairs following OpenInference naming (e.g., `llm.input_messages`, `llm.output_messages`, `llm.token_count.prompt`, `llm.token_count.completion`, `llm.model_name`, `input.value`, `output.value`, `tool.name`).

For Harmonia the mapping is:

| Harmonia concept | Phoenix span kind | Key attributes |
|---|---|---|
| Full experiment run | `AGENT` (root span) | `experiment_name`, `run_id`, `llm.model_name`, `llm.provider` |
| Conversation turn | `CHAIN` (child of root) | `turn_number`, `input.value` (user message), `output.value` (agent response) |
| LLM API call inside a turn | `LLM` (child of turn) | `llm.input_messages`, `llm.output_messages`, token counts, model params |
| Beaker code execution | `TOOL` (child of turn) | `tool.name="beaker_execute"`, `input.value` (code), `output.value` (stdout/result) |
| Decision-point handling | `CHAIN` (child of turn) | `decision_mode`, `decision_text` |

The Python SDK provides three instrumentation mechanisms: (a) `@tracer.chain`, `@tracer.llm`, `@tracer.tool`, `@tracer.agent` decorators; (b) context managers via the standard OTel `tracer.start_as_current_span()`; (c) `phoenix.otel.register()` to configure a global `TracerProvider` that ships spans to the Phoenix collector. All three support manual attribute injection, which is essential because Harmonia's orchestrator (the automation runner) does not use LangChain or any auto-instrumentable framework -- it drives Beaker via raw WebSocket messages.

### 1.2 GUI and Visualization Layer

`phoenix serve` starts a web UI on port 6006 (configurable). It provides:

- **Traces table**: filterable list of all traces with status, latency, token counts, and error indicators.
- **Trace detail / waterfall**: hierarchical span tree with a latency timeline. Clicking a span shows its full attributes (prompt text, completion text, token counts, tool input/output).
- **Spans table**: flat, filterable view of all spans across traces, useful for aggregate analysis ("show me all TOOL spans where status = ERROR").
- **Agents tab**: agent-centric view grouping traces by the root AGENT span.
- **Annotations and evaluations**: attach human labels or programmatic evaluation scores to spans.
- **UMAP embedding visualization**: projects span embeddings for similarity analysis (useful for comparing prompt variations).

Absent from Phoenix out of the box: dedicated side-by-side trace comparison view, and click-through from external metric plots to specific traces. Both require a lightweight custom bridge (see Section 3).

### 1.3 Data Persistence on HPC

Phoenix defaults to **SQLite** stored at `~/.phoenix/` (configurable via `PHOENIX_WORKING_DIR`). This is the key property that makes it viable on HPC: no PostgreSQL, no Docker, no persistent service between jobs. Two deployment modes are relevant:

- **Embedded mode**: `phoenix.launch_app()` starts Phoenix inside the same Python process as the experiment. Spans are collected in-process. The SQLite database persists across runs. Suitable for single-experiment debugging, but ties the server lifetime to the experiment.
- **Standalone server mode**: `phoenix serve` runs as a separate process (or SLURM job) with its own lifetime. Experiments send spans via OTLP HTTP (port 6006) or gRPC (port 4317). The server can outlive individual experiment jobs, enabling cross-run analysis. On HPC, this would run as a persistent `srun` or `screen`-managed process on a submit node.

For Harmonia, **standalone mode is recommended** because it decouples tracing infrastructure from experiment jobs and allows the web UI to remain available between runs. The `PHOENIX_WORKING_DIR` environment variable should point to a directory under `results/` or a dedicated `.phoenix/` directory within the project tree (not `~/.phoenix/`, to avoid the 5 GB home quota).

Data export: `phoenix.Client().get_spans_dataframe()` returns a pandas DataFrame of all spans, queryable with the `SpanQuery` DSL. This integrates directly with the existing metrics pipeline.

### 1.4 SDK Integration Points

All instrumentation is manual (no auto-patching of Archytas/Beaker internals). The integration surface is:

1. **`phoenix.otel.register()`** -- called once at process start to configure the global `TracerProvider` with the Phoenix OTLP endpoint.
2. **`opentelemetry.trace.get_tracer("harmonia")`** -- returns a `Tracer` instance used throughout the code.
3. **`tracer.start_as_current_span(name, attributes={...})`** -- context manager for creating spans with custom attributes.
4. **`span.set_attribute(key, value)`** -- for setting attributes after span creation (e.g., token counts received asynchronously).
5. **`span.set_status(StatusCode.ERROR, description)`** -- for marking failed spans.

---

## 2. Codebase Integration -- Complete Change Specification

### (a) Core Tracing Instrumentation

**File 1: `src/automation/tracing.py` (NEW)**

New module encapsulating all Phoenix/OTel setup and span-creation helpers.

```python
# Key exports:
def init_tracing(endpoint: str, run_id: str, experiment_name: str) -> Tracer
def experiment_span(tracer, config: ExperimentConfig) -> ContextManager  # root AGENT span
def turn_span(tracer, turn_number: int, user_message: str) -> ContextManager  # CHAIN span
def tool_span(tracer, tool_name: str, code: str) -> ContextManager  # TOOL span
def set_llm_attributes(span, model: str, provider: str, token_counts: dict, model_params: dict)
def set_turn_attributes(span, response_type: str, duration: float, agent_response: str)
```

Dependencies introduced: `arize-phoenix-otel`, `opentelemetry-api`, `opentelemetry-sdk`, `openinference-semantic-conventions`. All pip-installable, no system dependencies.

**File 2: `src/automation/runner.py` (MODIFIED)**

- `ExperimentRunner.__init__()`: call `init_tracing()` with endpoint from env var `PHOENIX_ENDPOINT` (default `http://localhost:6006`). Store the `Tracer` instance.
- `ExperimentRunner.run()`: wrap the entire experiment loop in `experiment_span()`. Set final status/error on the root span at completion.
- `ExperimentRunner._run_turn()`: wrap each turn in `turn_span()`. After receiving the `AgentResponse`, call `set_turn_attributes()` to record `response_type`, `duration_seconds`, `agent_response`. Parse `raw_messages` to extract code-execution spans: for each `beaker__execute_input` / `execute_result` / `error` pair in `raw_messages`, create a child `tool_span()` with the code as input and the result/error as output.
- `ExperimentRunner._send_with_retries()`: on each retry, record a child span with `openinference.span.kind=LLM`, marking it with error status and the `error_code` from `_classify_retryable_error()`.

**File 3: `src/automation/manual_runner.py` (MODIFIED)**

- `ManualExperimentRunner.__init__()`: same `init_tracing()` call.
- `ManualExperimentRunner.start()`: open root `experiment_span()`.
- `ManualExperimentRunner._handle_message()`: when a turn completes (at the `llm_response`, `code_cell`, or `error` branch), create and close a `turn_span()` with the accumulated attributes. Extract tool spans from `raw_messages` the same way as in `runner.py`.

**File 4: `src/automation/client.py` (MODIFIED)**

- `BeakerClient.send_message()`: accept an optional `parent_span` argument. If tracing is active, create a child `LLM` span around the WebSocket request-response cycle. When the response arrives, set `llm.token_count.prompt` and `llm.token_count.completion` if the raw messages contain token usage data (some providers include this in the response metadata).
- `AgentResponse`: add optional fields `input_tokens: int = 0`, `output_tokens: int = 0`, `model_params: dict = field(default_factory=dict)`. Populate these by parsing the raw WebSocket messages for token-usage metadata where available.

**File 5: `src/automation/logger.py` (MODIFIED)**

- `TurnRecord`: add fields `input_tokens: int = 0`, `output_tokens: int = 0`, `cost_usd: float = 0.0`, `code_executions: list[dict] = field(default_factory=list)`. The `code_executions` list contains dicts with keys `code`, `stdout`, `stderr`, `status`, `duration_seconds`, extracted from `raw_messages`.
- `TraceLogger.log_turn()`: accept and store the new fields.
- `ExperimentTrace.to_dict()`: include the new fields in output.

This ensures the existing `trace.json` artifact is enriched alongside Phoenix, maintaining backward compatibility with the log analysis CLI.

**File 6: `src/prompt_logging.py` (MODIFIED)**

- `register_prompt_json_logger()`: inside the `logging_execute_wrapper`, after capturing the prompt composition, also create a `CHAIN` span named `prompt_composition` with the full `messages_sent_to_llm` as the `llm.input_messages` attribute and the content hashes as custom attributes. This captures the initial prompt in Phoenix's trace timeline.

### (b) Data Export and Persistence

**File 7: `src/automation/tracing.py` (same new file, additional exports)**

```python
def export_run_spans(run_id: str, output_dir: Path) -> Path:
    """Export all spans for a run_id to a parquet file in the results directory."""

def phoenix_to_trace_json(run_id: str) -> dict:
    """Convert Phoenix spans for a run back to trace.json format for backward compat."""
```

`export_run_spans()` uses `phoenix.Client().get_spans_dataframe(filter_condition=f"trace_id == '{run_id}'")` and writes the result to `{output_dir}/spans.parquet`. This preserves Phoenix data alongside existing artifacts.

**File 8: `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` (MODIFIED)**

- Add an optional `--phoenix` flag. When set, the tool also reads `spans.parquet` (if present in the results directory) and enriches its analysis with token counts, cost estimates, and per-span error data from Phoenix. The existing 13-category failure taxonomy remains unchanged; Phoenix data supplements it with quantitative detail (e.g., "Turn 3 used 14,200 input tokens at $0.021").

### (c) Configuration and Setup

**File 9: `src/automation/config.py` (MODIFIED)**

- Add `TracingConfig` dataclass:

```python
@dataclass
class TracingConfig:
    enabled: bool = False
    phoenix_endpoint: str = "http://localhost:6006"
    export_spans_parquet: bool = True
```

- Add `tracing: TracingConfig` field to `ExperimentConfig`.
- Update `from_dict()` to parse the `tracing:` YAML section.

**File 10: Experiment YAML configs (MODIFIED pattern)**

Add a `tracing:` block to experiment configs:

```yaml
tracing:
  enabled: true
  phoenix_endpoint: "http://localhost:6006"
  export_spans_parquet: true
```

**File 11: `exec_apptainer_harmonia.sh` (MODIFIED)**

- If `tracing.enabled` is true in the config (detectable via a quick `python -c "import yaml; ..."` one-liner), pass `PHOENIX_ENDPOINT` as an environment variable into the Apptainer container via `--env`.
- Add `--writable-tmpfs` or bind-mount `PHOENIX_WORKING_DIR` so the embedded Phoenix client can resolve the endpoint.

**File 12: `scripts/phoenix_server.sh` (NEW)**

Convenience script to start and manage the Phoenix server on the HPC:

```bash
#!/bin/bash
# Usage: ./scripts/phoenix_server.sh start|stop|status
# Runs phoenix serve with SQLite storage under project tree
export PHOENIX_WORKING_DIR="$(pwd)/.phoenix_data"
export PHOENIX_PORT="${PHOENIX_PORT:-6006}"
```

Uses `screen` or `nohup` on a submit node. Not a SLURM job (the server must persist across experiment jobs).

**File 13: `pyproject.toml` or `requirements-tracing.txt` (NEW/MODIFIED)**

Add optional tracing dependencies:

```
arize-phoenix[evals]>=8.0
opentelemetry-api>=1.20
opentelemetry-sdk>=1.20
openinference-semantic-conventions>=0.1.5
```

These should be an optional install group so non-tracing runs remain lightweight.

---

## 3. Visualization and Cross-Referencing with Metrics

### 3.1 Unified Dashboard Architecture

The architecture uses **two complementary layers**:

1. **Phoenix UI (port 6006)**: primary trace exploration interface. Provides the trace table, span waterfall, agent view, and annotation capabilities. Accessed via SSH port forwarding (`ssh -L 6006:localhost:6006 hpc-submit-node`).

2. **Enhanced `visualize_metrics_cli.py` (existing)**: remains the primary quantitative analysis tool. Extended with two new capabilities:
   - **Trace links in output**: when `--backend plotly` is used, bar charts and tables include clickable hyperlinks to the corresponding Phoenix trace URL (`http://localhost:6006/traces/{trace_id}`). The `trace_id` is read from `spans.parquet` or from a new `phoenix_trace_id` field added to `metrics.json`.
   - **Token/cost columns**: the summary table gains `input_tokens`, `output_tokens`, `total_cost_usd` columns pulled from the exported span data.

### 3.2 Click-Through from Metrics to Traces

The `run_id` (8-char hex) is already the universal join key across logs, results directories, and metrics. The bridge works as follows:

1. `tracing.py` records the OTel `trace_id` alongside the Harmonia `run_id` in a small JSON sidecar file (`{results_dir}/.phoenix_trace_id`).
2. `visualize_metrics_cli.py` reads this sidecar when building the runs table and adds a `phoenix_url` column.
3. In Plotly interactive mode, clicking a bar in the accuracy chart opens the Phoenix trace detail for that run. In static (seaborn) mode, the summary CSV includes the URL.

### 3.3 Side-by-Side Trace Comparison

Phoenix does not provide a built-in side-by-side view. Two approaches, in order of increasing effort:

- **Short-term (zero code)**: use Phoenix's spans table with filters. Select two `run_id` values and compare span timelines in separate browser tabs. Not ideal but functional immediately.
- **Medium-term (2--3 days additional)**: build a lightweight `compare_traces.py` CLI that uses `phoenix.Client().get_spans_dataframe()` to fetch two runs, aligns them by turn number, and produces a Plotly HTML report with side-by-side span timelines and diff-highlighted attribute tables. This is a standalone script in `code_development_tools_agents/monitoring_and_evaluation/`, not a modification to Phoenix itself.

### 3.4 GUI Deployment

Phoenix runs as a single Python process with no additional services. Deployment on HPC:

1. Start once on a submit node: `screen -S phoenix -d -m .venv/bin/phoenix serve --port 6006`.
2. SSH port-forward from local machine: `ssh -L 6006:localhost:6006 <submit-node>`.
3. Open `http://localhost:6006` in browser.
4. The SQLite database in `.phoenix_data/` accumulates traces across experiment runs. Periodic cleanup via `phoenix.Client().delete_traces(older_than=...)` if storage grows.

---

## 4. Effort Estimate and Risks

### 4.1 Implementation Effort

| Work package | Days | Dependencies |
|---|---|---|
| `tracing.py` module + `init_tracing` + span helpers | 1.5 | Phoenix SDK installed |
| `runner.py` + `manual_runner.py` instrumentation | 2.0 | `tracing.py` complete |
| `client.py` token extraction + `logger.py` enrichment | 1.5 | WebSocket message format analysis |
| `config.py` + YAML schema + `exec_apptainer_harmonia.sh` | 1.0 | -- |
| `phoenix_server.sh` + deployment documentation | 0.5 | -- |
| `visualize_metrics_cli.py` trace links + cost columns | 1.5 | Span export working |
| Log analysis CLI `--phoenix` enrichment | 1.0 | Span export working |
| Testing across 3+ LLM providers (OpenRouter, Ollama, Anthropic) | 1.5 | Full instrumentation |
| `compare_traces.py` side-by-side report | 1.5 | Optional, deferred |
| **Total** | **10--12** | |

### 4.2 Top 3 Technical Risks

**Risk 1: Token counts unavailable for some providers.**
Archytas/Beaker does not uniformly expose token usage in WebSocket messages. OpenRouter includes `usage` in its API response, but Ollama may not propagate it through Beaker's Jupyter protocol layer. **Mitigation**: Implement token-count extraction as best-effort. When raw counts are unavailable, estimate from character/word counts using tiktoken or provider-specific tokenizer approximations. Log a warning when estimation is used. The `model_metadata.pricing_*` fields from the config already exist and enable cost calculation once token counts are obtained.

**Risk 2: Phoenix server lifecycle management on HPC.**
There is no container orchestration or systemd on compute nodes. If the Phoenix server process dies (submit node reboot, OOM), traces from in-flight experiments are lost (they buffer in the OTel SDK and flush on shutdown). **Mitigation**: (a) Configure the OTel `BatchSpanProcessor` with a short `schedule_delay_millis` (e.g., 5000 ms) so spans flush frequently. (b) Enable `SimpleSpanProcessor` as a fallback for critical spans (root experiment span). (c) The `phoenix_server.sh` script wraps the server in a `while true` restart loop. (d) The `tracing.enabled` config flag means experiments still produce `trace.json` via the existing logger even if Phoenix is down -- Phoenix is additive, not a replacement.

**Risk 3: Apptainer network isolation blocks OTLP export.**
The Beaker container may not be able to reach the Phoenix server on the host's port 6006 if Apptainer's network namespace isolates it. **Mitigation**: Apptainer by default shares the host network namespace (unlike Docker), so `localhost:6006` inside the container should resolve to the host process. If a custom network namespace is in use, the `exec_apptainer_harmonia.sh` script already bind-mounts host directories and can be extended to pass `--net --network-args "portmap=6006:6006/tcp"` or use the host IP instead of localhost.

### 4.3 Limitations Requiring Custom Workarounds

1. **No native side-by-side trace comparison**: requires the custom `compare_traces.py` script described in Section 3.3. Phoenix's experiment comparison feature compares evaluation scores, not trace structures.

2. **No native click-through from external plots**: the `visualize_metrics_cli.py` must explicitly construct Phoenix URLs and embed them in Plotly outputs. Phoenix has no API for "open trace by custom attribute" -- the URL format is `http://host:port/traces/{trace_id}`, requiring the `run_id` to `trace_id` mapping maintained by the sidecar file.

3. **No auto-instrumentation for Archytas/Beaker**: unlike LangChain or LlamaIndex, there is no Phoenix auto-instrumentor for the Archytas agent framework. All span creation is manual. This is acceptable because the instrumentation points are concentrated in four files (`runner.py`, `manual_runner.py`, `client.py`, `prompt_logging.py`) and the manual approach gives full control over what is captured.
