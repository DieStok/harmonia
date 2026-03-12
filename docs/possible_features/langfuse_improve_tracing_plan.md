# Implementation Plan: Langfuse Integration for Harmonia Tracing and Observability

**Date:** 2026-03-03
**Status:** Plan (not yet implemented)
**Input:** `docs/possible_features/03_03_2026_research_into_LLM_tracing.md`

---

## 1. Framework Functionality Mapping

### 1.1 Trace Capture and Data Model

Langfuse organizes observability data in a three-level hierarchy: **Sessions > Traces > Observations**. A Harmonia experiment run maps naturally to this model:

| Langfuse Concept | Harmonia Equivalent | Notes |
|------------------|---------------------|-------|
| **Session** | Experiment batch (e.g., all runs of `dou_harmonization_code-context`) | Groups related traces by experiment config name |
| **Trace** | Single experiment run (one `trace.json`) | Identified by the 8-char hex run ID |
| **Generation** (observation type) | Individual LLM API call | Token counts, model params, cost, latency |
| **Span** (observation type) | Conversation turn (`TurnRecord`) | Parent for all observations within a turn |
| **Span: tool** | Beaker code execution (`beaker__execute_input`) | Input code, stdout/stderr, execution status |
| **Span: chain** | Retry loop in `_send_with_retries` | Tracks retry attempts, error codes, backoff |

Langfuse supports 10 observation types. The critical ones for Harmonia are `generation` (to fill the token/cost gap identified in the research report), `span` (for the nested hierarchy: Turn > LLM call > Tool use > Code execution), and `event` (for lightweight markers like decision points and status transitions).

### 1.2 GUI and Visualization Layer

The Langfuse web UI provides:

- **Trace tree view**: Hierarchical visualization of a run's spans and generations with timing waterfall. This directly addresses the P0 requirement for a turn-by-turn trace viewer with expandable details.
- **Trace table**: Filterable list of all traces with columns for model, status, latency, token count, cost. Supports search by metadata tags (experiment name, model, run ID).
- **Custom dashboards**: Aggregated charts (latency distributions, cost over time, error rates). Can be configured to show per-model comparisons.
- **Session view**: Groups all runs within an experiment for sequential browsing.
- **Prompt management**: Version-controlled prompt storage; not directly needed but could track prompt evolution across experiment configs.

**Not provided out of the box**: dedicated side-by-side trace comparison (two runs viewed in parallel columns), and click-through from external metrics plots (e.g., `visualize_metrics_cli.py` bar charts) into specific traces. Both require custom work regardless of framework choice.

### 1.3 Data Persistence and HPC Constraints

Langfuse v3 requires PostgreSQL + ClickHouse + MinIO + Redis, deployed as 6 Docker Compose containers with a minimum of 4 vCPUs and 16 GB RAM. This architecture is **incompatible with running directly on HPC compute nodes** (no Docker daemon, no persistent services between SLURM jobs, no root access).

**Viable deployment model**: Run Langfuse on a separate persistent machine (a lab workstation, a department VM, or a cloud instance). The Python SDK in the Apptainer container sends traces over HTTP to this external Langfuse server. This works because:

1. HPC compute nodes have outbound HTTP access (already used for OpenRouter API calls).
2. The SDK is async and non-blocking; trace data is batched and flushed in the background.
3. If the Langfuse server is unreachable, the SDK silently drops traces (no experiment failure).

**Data export**: Langfuse provides SDK-level export (`langfuse.get_trace()`, `langfuse.get_observations()`), UI JSON export, and scheduled blob storage exports (JSON/JSONL/CSV). This means existing post-hoc analysis tooling (`read_and_analyze_logs_and_traces_cli.py`) can ingest Langfuse data alongside local `trace.json` files.

### 1.4 SDK Integration Points

The Langfuse Python SDK v3 supports three instrumentation modes, all of which work without auto-patching a mainstream LLM framework:

1. **`@observe()` decorator**: Wrap any function to create a span. Nested calls automatically form parent-child relationships via Python context variables.
2. **Context managers**: `langfuse.trace()` and `trace.span()` for explicit scope control.
3. **Low-level SDK**: `langfuse.generation()` with manual `end()` calls for full control over observation lifecycle.

Since Harmonia uses Archytas/Beaker (not LangChain, not OpenAI SDK directly), auto-instrumentation is not available. All instrumentation must be manual, using approach (3) above. This is well-supported and documented by Langfuse.

---

## 2. Codebase Integration -- Complete Change Specification

### (a) Core Tracing Instrumentation

**File 1: `src/automation/langfuse_tracing.py` (NEW)**

New module encapsulating all Langfuse SDK interaction. Isolates the dependency so that experiments can run without Langfuse configured.

```python
class HarmoniaLangfuseTracer:
    """Wrapper around Langfuse SDK for Harmonia experiment tracing."""

    def __init__(self, config: ExperimentConfig, run_id: str)
    def start_trace(self, experiment_name: str, llm_provider: str, llm_model: str) -> None
    def start_turn_span(self, turn: int, user_message: str) -> LangfuseSpan
    def log_generation(self, parent_span, model: str, input_messages: list,
                       output: str, usage: dict, model_parameters: dict) -> None
    def log_tool_execution(self, parent_span, code: str, output: str,
                           status: str, duration_seconds: float) -> None
    def log_retry(self, parent_span, error_code: str, attempt: int, delay: float) -> None
    def end_turn_span(self, span, agent_response: str, response_type: str) -> None
    def end_trace(self, status: str, metrics: dict = None) -> None
    def flush(self) -> None
```

Dependencies introduced: `langfuse>=3.0.0` (pip install into `.venv`).

The constructor reads `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` from environment variables. If any are missing, all methods become no-ops (graceful degradation). The `config.model_metadata` pricing fields are passed to `generation()` calls to enable cost tracking.

**File 2: `src/automation/runner.py` (MODIFY)**

Changes to `ExperimentRunner`:

- `__init__`: Instantiate `HarmoniaLangfuseTracer(self.config, run_id)` alongside existing `TraceLogger` and `ConversationLogger`. Call `self.langfuse_tracer.start_trace(...)` where `self.trace_logger.start_experiment(...)` is called (line 72).
- `_run_turn`: After calling `_send_with_retries`, call `self.langfuse_tracer.start_turn_span(turn, msg_config.content)`. Parse `response.raw_messages` to extract code executions (`beaker__execute_input` / `execute_result` pairs) and log each as `log_tool_execution()`. Call `end_turn_span()` after logging.
- `_send_with_retries`: On each retry, call `self.langfuse_tracer.log_retry(span, error_code, attempt, delay)`.
- `run()` cleanup block (line 123): Call `self.langfuse_tracer.end_trace(status, metrics)` then `self.langfuse_tracer.flush()`.

Existing `TraceLogger` and `ConversationLogger` calls are **not removed**. Langfuse tracing is additive; local `trace.json` and `conversation.md` remain the source of truth for offline/disconnected analysis.

**File 3: `src/automation/client.py` (MODIFY)**

Changes to `BeakerClient.send_message`:

- Extract token usage from raw WebSocket messages if present. Some LLM providers include `usage` metadata in responses. Expose this as a new field `usage: dict` on `AgentResponse` (default `{}`).
- This is a best-effort extraction; if the Beaker/Archytas layer does not pass through usage data, the field remains empty and Langfuse simply records the generation without token counts.

**File 4: `src/automation/manual_runner.py` (MODIFY)**

Analogous changes to `ManualExperimentRunner`:

- Instantiate `HarmoniaLangfuseTracer` in `__init__`.
- In the WebSocket monitoring loop, create spans for each observed turn and log tool executions extracted from monitored messages.
- Call `end_trace()` and `flush()` on shutdown (Ctrl+C handler).

**File 5: `src/prompt_logging.py` (MODIFY)**

In `register_prompt_json_logger`, after building the composition dict, also call `langfuse_tracer.log_prompt_composition(composition)` if a tracer instance is available. This attaches the full prompt composition as metadata on the Langfuse trace, making it searchable and viewable in the UI.

This requires passing the tracer instance through the call chain. Add an optional `langfuse_tracer` parameter to `register_prompt_json_logger()`.

### (b) Data Export and Persistence

**File 6: `src/automation/langfuse_export.py` (NEW)**

Utility to export Langfuse traces back to local JSON format compatible with the existing analysis CLI. Functions:

```python
def export_trace_to_local(langfuse_client, trace_id: str, output_dir: Path) -> Path
    """Fetch a Langfuse trace and write it as a trace.json file."""

def export_session_traces(langfuse_client, session_id: str, output_dir: Path) -> list[Path]
    """Export all traces in a Langfuse session to local trace.json files."""
```

This bridges Langfuse data back into the format consumed by `read_and_analyze_logs_and_traces_cli.py`, enabling the existing 13-category failure mode analysis on Langfuse-stored traces.

**File 7: `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` (MODIFY)**

Add a `--langfuse` flag that, when set, fetches traces from Langfuse instead of (or in addition to) scanning local `results/` directories. Uses `langfuse_export.py` under the hood. The existing analysis logic and failure mode taxonomy remain unchanged.

### (c) Configuration and Setup

**File 8: `src/automation/config.py` (MODIFY)**

Add an optional `LangfuseConfig` dataclass:

```python
@dataclass
class LangfuseConfig:
    enabled: bool = False
    host: Optional[str] = None  # Override LANGFUSE_HOST env var
    public_key: Optional[str] = None  # Override LANGFUSE_PUBLIC_KEY env var
    session_name: Optional[str] = None  # Custom session grouping
```

Add `langfuse: LangfuseConfig` field to `ExperimentConfig` (default: disabled). Parse from YAML `langfuse:` section in `from_dict()`.

**File 9: Experiment YAML configs (MODIFY pattern)**

Add optional `langfuse:` block to experiment configs:

```yaml
langfuse:
  enabled: true
  session_name: "experiment_batch_2026_03"
```

When `enabled: false` or the block is absent, no Langfuse dependency is required at runtime.

**File 10: `exec_apptainer_harmonia.sh` (MODIFY)**

Pass `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` environment variables into the Apptainer container via `--env` flags, reading from the host `.env` file. These are only needed when Langfuse is enabled.

**File 11: `.env.example` (MODIFY)**

Add commented-out Langfuse variables:

```bash
# LANGFUSE_HOST=http://labworkstation:3000
# LANGFUSE_PUBLIC_KEY=pk-...
# LANGFUSE_SECRET_KEY=sk-...
```

**File 12: `pyproject.toml` (MODIFY)**

Add `langfuse>=3.0.0` as an optional dependency:

```toml
[project.optional-dependencies]
tracing = ["langfuse>=3.0.0"]
```

---

## 3. Visualization and Cross-Referencing with Metrics

### 3.1 Unified Dashboard Architecture

The visualization strategy has two tiers:

**Tier 1 -- Langfuse native UI** (immediate value, no custom code): The Langfuse web UI provides trace exploration, search/filter by model/status/experiment, latency waterfall, and cost dashboards. Access via SSH port-forward from the machine hosting Langfuse. This replaces manual inspection of `trace.json` files for debugging individual runs.

**Tier 2 -- Custom bridge layer** (requires development): A lightweight Python script that generates deep-links from `visualize_metrics_cli.py` output into Langfuse traces. When the metrics CLI produces a comparison table or bar chart, each run's row/bar includes a clickable URL to `{LANGFUSE_HOST}/trace/{trace_id}`. This requires storing the Langfuse trace ID in the local `trace.json` (added by `HarmoniaLangfuseTracer` at trace creation time) and reading it during visualization.

### 3.2 Click-Through from Metrics to Traces

Modification to `src/evaluation/visualization/normalize.py`: when building the runs DataFrame, extract the `langfuse_trace_id` field from `trace.json` (if present) and include it as a column. The `visualize_metrics_cli.py` `summarize` subcommand then emits this as a hyperlink column in the output table.

For Plotly interactive plots (`--backend plotly`), bar chart hover-text includes the Langfuse trace URL, and clicking opens the trace in a new browser tab via `customdata` + `on_click` callback.

### 3.3 Side-by-Side Trace Comparison

Langfuse does not offer a dedicated side-by-side trace diff view. Two approaches:

1. **Langfuse experiments feature**: Group runs by experiment config, compare aggregate metrics (latency, cost, token usage) across models. This provides table-level comparison but not turn-by-turn alignment.
2. **Custom comparison script** (future work): A standalone Dash or Streamlit app that fetches two traces via the Langfuse SDK and renders them in parallel columns with turn alignment. This is independent of the core Langfuse integration and can be deferred to a later phase.

### 3.4 GUI Deployment

Langfuse runs on a persistent machine outside the HPC cluster. Recommended setup:

- **Host**: A lab workstation or department VM with Docker Compose support.
- **Access**: SSH tunnel from user laptop to the Langfuse host (e.g., `ssh -L 3000:localhost:3000 labworkstation`). Langfuse UI is then at `http://localhost:3000`.
- **Persistence**: PostgreSQL and ClickHouse data persisted in Docker volumes. Standard backup via `docker compose` volume snapshots.
- **Resource requirements**: 4 vCPUs, 16 GB RAM minimum. The 6-container stack (web, worker, PostgreSQL, ClickHouse, MinIO, Redis) is stable for the expected load (tens of traces per day, not thousands).

---

## 4. Effort Estimate and Risks

### 4.1 Implementation Effort

| Work Package | Files | Effort |
|-------------|-------|--------|
| Core tracer module (`langfuse_tracing.py`) | 1 new | 1.5 days |
| Runner integration (runner.py, manual_runner.py, client.py) | 3 modified | 1.5 days |
| Config and setup (config.py, .env, pyproject.toml, exec script) | 4 modified | 0.5 days |
| Export bridge and CLI integration | 2 files (1 new, 1 modified) | 1 day |
| Metrics cross-referencing (normalize.py, visualize_metrics_cli.py) | 2 modified | 0.5 days |
| Langfuse server deployment and testing | Infrastructure | 1 day |
| **Total** | **13 files** | **6 developer-days** |

### 4.2 Top 3 Technical Risks

**Risk 1: Token usage data unavailability.**
Archytas/Beaker may not pass through LLM API usage metadata (input_tokens, output_tokens) in WebSocket messages. If the usage data never reaches `client.py`, Langfuse generations will lack token counts and cost cannot be computed.
*Mitigation*: Inspect Archytas source code for usage passthrough. If absent, instrument the LLM model classes in `src/bdikit_context/llm/litellm_model.py` directly, since liteLLM does return usage data from all providers. Alternatively, estimate tokens from message character counts using provider-specific tokenizers.

**Risk 2: Network connectivity from HPC compute nodes.**
While compute nodes can reach external APIs (proven by OpenRouter usage), a self-hosted Langfuse on a lab workstation may not be reachable from compute nodes due to firewall rules or network segmentation.
*Mitigation*: Test connectivity before development begins (`curl http://labworkstation:3000/api/public/health` from a compute node). If unreachable, options are: (a) deploy Langfuse on a machine in the same network segment, (b) use Langfuse Cloud (hosted SaaS, eliminates infrastructure but adds data residency considerations), or (c) buffer traces locally and sync post-job via a transfer node.

**Risk 3: Langfuse server maintenance burden.**
The 6-container Docker Compose stack requires ongoing maintenance (updates, disk monitoring, backups). If the server goes down between experiment batches, historical data could be lost.
*Mitigation*: Automate Docker Compose restarts via systemd. Set up weekly volume backups. Critically, the local `trace.json` files remain the authoritative record; Langfuse is an enhancement layer, not a replacement. If the server is lost, all experiment data is still available locally.

### 4.3 Limitations Requiring Custom Workarounds

1. **No side-by-side trace comparison**: Must be built as a separate visualization tool. Neither Langfuse nor any evaluated framework provides this out of the box.

2. **No native integration with `visualize_metrics_cli.py`**: The click-through from evaluation metrics to Langfuse traces requires custom glue code in the visualization pipeline. This is unavoidable regardless of framework choice.

3. **Dual-write overhead**: Every experiment writes both local `trace.json` (for offline analysis and the existing failure-mode CLI) and Langfuse traces (for the GUI). This is intentional redundancy but increases per-turn logging code complexity. The `HarmoniaLangfuseTracer` abstraction keeps this manageable.

4. **No SQLite/lightweight mode**: Unlike Arize Phoenix, Langfuse cannot run as a single-process SQLite-backed server. This means the tracing GUI is never available on the HPC node itself; it always requires a separate host. For users who want zero-infrastructure tracing with a GUI, Phoenix would be a simpler alternative at the cost of a less permissive license (ELv2 vs MIT).
