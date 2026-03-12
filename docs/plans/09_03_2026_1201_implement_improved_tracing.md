# Implementation Plan: Phoenix Tracing for Harmonia

**Date**: 2026-03-09
**Status**: Approved for implementation
**Estimated effort**: 6-8 developer-days (Phase 1), 3-4 developer-days (Phase 2)

---

## 0. Summary of Design Decisions

| Decision | Resolution |
|----------|-----------|
| Phoenix mode | Standalone server, OTLP HTTP export from container |
| Server lifecycle | Python CLI script (`ensure_phoenix_server.py`) called from `exec_apptainer_harmonia.sh`; manages a SLURM job (or submit-node screen session) |
| LLM isolation | Container sends spans over network to Phoenix; no `.phoenix/` files visible to the LLM agent |
| Token counts | Modify forked Archytas + Beaker to forward `usage_metadata` through WebSocket protocol, rebuild `.sif` |
| `raw_messages` | Keep writing as-is (no changes) |
| `.phoenix/` in git | Added to `.gitignore` |
| Critic future-proofing | `harmonia.trace_type` and `harmonia.parent_run_id` span attributes from the start |
| Concurrency | Phoenix with SQLite handles parallel experiments; `BatchSpanProcessor` on client side buffers spans |
| Dash dashboard | Separate plan (see `09_03_2026_1201_create_plotly_plots_phoenix_traces_dashboard.md`) |

---

## 0.1 Implementation Context for Fresh Claude Instances

This section provides all the context a new Claude instance needs to implement this plan without re-reading the research documents.

### Key Source Files (read these before implementing)

| File | Absolute Path | Why |
|------|---------------|-----|
| `runner.py` | `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/automation/runner.py` | Main automation runner. `ExperimentRunner.__init__()`, `run()`, `_run_turn()`, `_send_with_retries()` are the primary instrumentation points. |
| `manual_runner.py` | `.../src/automation/manual_runner.py` | Manual experiment monitor. `ManualExperimentRunner.start()`, `_handle_message()`, `_finalize()` need span wrapping. |
| `client.py` | `.../src/automation/client.py` | `BeakerClient` and `AgentResponse` dataclass. `send_message()` returns `AgentResponse` with `raw_messages` — this is where `usage_records` will appear after Beaker changes. |
| `logger.py` | `.../src/automation/logger.py` | `TurnRecord` and `ExperimentTrace` dataclasses, `TraceLogger` and `ConversationLogger` classes. Enrichment target. |
| `config.py` | `.../src/automation/config.py` | `ExperimentConfig` with `from_dict()` parser. Add `TracingConfig` here. Already has `ModelMetadataConfig` with `pricing_prompt_per_million_tokens` and `pricing_completion_per_million_tokens`. |
| `prompt_logging.py` | `.../src/prompt_logging.py` | Example of the monkey-patching pattern used inside the container (`register_prompt_json_logger`). Reference for understanding how in-container hooks work. |
| `run_experiment.py` | `.../run_experiment.py` | CLI entry point for automated experiments. Creates `ExperimentRunner`, calls `runner.run()`. Config path is `args.config` (Path). Does NOT currently pass config path to `ExperimentRunner`. |
| `run_manual_experiment.py` | `.../run_manual_experiment.py` | CLI entry point for manual experiments. Creates `ManualExperimentRunner`, calls `runner.start()`. |
| `exec_apptainer_harmonia.sh` | `.../exec_apptainer_harmonia.sh` | Shell script that launches Apptainer container. Already parses config YAML to extract experiment name (line 156-161). Generates RUN_ID (line 166-168). This is where the Phoenix server management call goes. |
| `archytas/agent.py` | `/hpc/compgen/projects/llm_GEO_project/archytas/archytas/agent.py` | Forked Archytas. Line 286-292: `execute()` method where `usage_metadata` is extracted from `raw_result` (AIMessage) and printed to console. This is where to add the accumulator. |
| `archytas/models/ollama.py` | `/hpc/compgen/projects/llm_GEO_project/archytas/archytas/models/ollama.py` | Forked Archytas Ollama model. Does NOT extract `usage_metadata` from response. Needs fix. |
| `litellm_model.py` | `.../src/bdikit_context/llm/litellm_model.py` | LiteLLM model wrapper. Lines 215-227 show the pattern for extracting `usage_metadata` from `response.usage` — reference for the Ollama fix. |
| `beaker kernel.py` | `/hpc/compgen/projects/llm_GEO_project/beaker-kernel/beaker_kernel/kernel.py` | Forked Beaker. `llm_request()` method (line 570-639): line 572 is `result = await task`, lines 612-631 construct and send `code_cell`/`llm_response` WebSocket messages. |
| `build_harmonia_apptainer.sh` | `.../build_harmonia_apptainer.sh` | Container build script. Copies from `/hpc/compgen/projects/llm_GEO_project/archytas` and `/hpc/compgen/projects/llm_GEO_project/beaker-kernel` into the image. Run with: `srun --time=02:00:00 --mem=32G --gres=tmpspace:100G --account=compgen bash build_harmonia_apptainer.sh` |
| `.gitignore` | `.../harmonia/.gitignore` | Repo-relative paths only (absolute paths silently fail). Already ignores `logs/`, `results/`, `.venv/`. Add `.phoenix/` here. |

### Critical Gotchas

1. **Automation runner runs OUTSIDE the container.** `runner.py`, `manual_runner.py`, `client.py`, `logger.py` all run on the host (or submit node). The OTel tracing instrumentation goes here, NOT inside the container. The container only needs the Archytas/Beaker token forwarding changes.

2. **`ExperimentRunner` does not receive the config file path.** It receives a parsed `ExperimentConfig` object. To save `config_snapshot.yaml`, either: (a) add `config_source_path: Optional[str] = None` to `ExperimentConfig` and set it in `load_config()`, or (b) serialize the config back to YAML via `dataclasses.asdict()` + `yaml.dump()`. Option (a) is cleaner.

3. **`run_experiment.py` uses `sys.path.insert(0, str(Path(__file__).parent / "src"))` for imports.** The `from automation import ...` pattern means `src/automation/__init__.py` must export any new classes (like from `tracing.py`).

4. **The `raw_messages` list in `AgentResponse` contains ALL WebSocket messages for a turn.** After the Beaker changes, the `usage_records` field will appear in the LAST message of type `llm_response` or `code_cell`. The `extract_usage_records()` function should scan `raw_messages` in reverse for the first message containing `usage_records`.

5. **ReAct loop makes multiple `execute()` calls per turn.** Each call is a separate LLM invocation (thought → action → observation cycle). The accumulator `_turn_usage_records` collects ALL of them. The list is reset by `get_and_reset_usage_records()` when Beaker reads it after the full turn completes. So multiple LLM calls within one turn produce multiple entries in `usage_records`.

6. **`ExperimentConfig.from_dict()` is the YAML parser.** Any new config sections (like `tracing:`) must be parsed here. Follow the existing pattern (see how `retry_policy` or `model_metadata` are parsed).

7. **The `.venv` is at `.../harmonia/.venv/` (Python 3.11).** All new Python dependencies go here. Do NOT use conda or system Python.

8. **`PHOENIX_ENDPOINT` environment variable** is set by `exec_apptainer_harmonia.sh` after calling `ensure_phoenix_server.py`. The automation runner (`run_experiment.py` / `run_manual_experiment.py`) reads it from the environment OR from the config YAML. The env var takes precedence (set by the server management script) over the config value (which is a default/fallback).

9. **Line numbers in Archytas/Beaker may shift.** The forked repos may have been modified since the analysis. Always read the actual files before editing. The key landmarks: in `agent.py` search for `"Actual usage for query"` (the print statement); in `kernel.py` search for `llm_response` message construction.

10. **Beaker's `kernel.py` has a complex message flow in `llm_request()`.** The response handling (lines 570-639) processes the `result` from the agent task. There are multiple code paths: the result can be a string, a dict with `action: "code_cell"`, or iterable. The `usage_records` should be attached to whichever final message is sent (`llm_response` or `code_cell`). Read the full method before modifying.

11. **`ModelMetadataConfig` already has pricing fields.** `pricing_prompt_per_million_tokens` and `pricing_completion_per_million_tokens` in `config.py:121-122`. Use these to calculate `cost_usd` from token counts: `cost = (input_tokens * pricing_prompt / 1_000_000) + (output_tokens * pricing_completion / 1_000_000)`.

12. **Results directory naming convention**: `{experiment_name}_{timestamp}_{run_id}` — the 8-char hex `run_id` is always the last segment. This is how `find_results_dir()` in the dashboard data loader locates results by run_id.

13. **`metrics.json` structure**: Top-level keys are `schema_version`, `metadata`, `column_mapping`, `column_values`, `extra_columns_count`, `extra_columns`, `overall_summary`, `gold_standard_file`, `llm_output_file`, `column_mapping_file_found`, `value_mapping_file_found`. The `overall_summary` contains accuracy scores. The `metadata` contains `model`, `provider`, `experiment_name`, `run_id`.

14. **Apptainer shares host network namespace by default.** `localhost:6006` inside the container resolves to the host. No special networking config needed for OTLP export from within the container, BUT the tracing code runs outside the container (see gotcha #1), so this is only relevant if you ever move tracing inside.

15. **`exec_apptainer_harmonia.sh` is ~1500 lines.** The Phoenix management block should go AFTER the RUN_ID generation (line 168) and config parsing (line 156-161), but BEFORE the Apptainer exec call. Search for the section that constructs the `apptainer exec` command.

### Token Usage Data Flow (current state → target state)

```
CURRENT:
  LLM API → litellm/toki → AIMessage(usage_metadata={...})
    → archytas agent.execute() prints it → DISCARDED
    → Beaker kernel sends llm_response with text only
    → client.py receives text, no tokens
    → trace.json has no token data

TARGET:
  LLM API → litellm/toki → AIMessage(usage_metadata={...})
    → archytas agent.execute() appends to _turn_usage_records[]
    → Beaker kernel calls get_and_reset_usage_records()
    → Beaker includes usage_records in llm_response/code_cell message
    → client.py receives raw_messages containing usage_records
    → tracing.py extract_usage_records() parses them
    → OTel LLM spans get llm.token_count.* attributes
    → TurnRecord gets input_tokens, output_tokens, cost_usd
    → trace.json has full token data
```

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Apptainer Container (per experiment job)                │
│                                                         │
│  Archytas Agent                                         │
│    └─ agent.execute() captures usage_metadata           │
│       └─ stores in _turn_usage_records[]                │
│                                                         │
│  Beaker Kernel                                          │
│    └─ llm_request() reads usage_metadata from agent     │
│       └─ includes in llm_response / code_cell messages  │
│                                                         │
│  Automation Runner (runner.py / manual_runner.py)        │
│    └─ OTel TracerProvider configured with OTLP exporter │
│    └─ Creates spans: AGENT → CHAIN (turn) → LLM / TOOL │
│    └─ Extracts usage_metadata from WebSocket messages   │
│    └─ Sets llm.token_count.* attributes on LLM spans   │
│                                                         │
│  ──── OTLP HTTP ────────────────────────────────────▶   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Phoenix Server (SLURM job or submit-node process)       │
│    phoenix serve --port 6006                             │
│    PHOENIX_WORKING_DIR=.phoenix/                         │
│    SQLite storage, accumulates across runs               │
│    Web UI accessible via SSH port forwarding             │
└─────────────────────────────────────────────────────────┘
```

### OpenTelemetry Span Schema (OpenInference Conventions)

Recorded here for future reference when querying the `.phoenix/` SQLite database directly.

| Harmonia concept | OTel span kind | Span name | Key attributes |
|---|---|---|---|
| Full experiment run | `AGENT` (root span) | `experiment:{name}` | `harmonia.run_id`, `harmonia.experiment_name`, `harmonia.trace_type` (`annotation` / `critic_evaluation` / `re_annotation`), `harmonia.parent_run_id` (if critic), `llm.model_name`, `harmonia.llm_provider`, `harmonia.config_snapshot` (YAML) |
| Conversation turn | `CHAIN` | `turn:{N}` | `harmonia.turn_number`, `input.value` (user message), `output.value` (agent response), `harmonia.response_type`, `harmonia.decision_mode` (if decision turn), `harmonia.duration_seconds` |
| LLM API call within a turn | `LLM` | `llm_call:{N}` | `llm.input_messages`, `llm.output_messages`, `llm.token_count.prompt`, `llm.token_count.completion`, `llm.token_count.total`, `llm.model_name`, `harmonia.cost_usd` |
| Beaker code execution | `TOOL` | `beaker_execute` | `tool.name="beaker_execute"`, `input.value` (code), `output.value` (stdout/result), `tool.status` |
| Retry attempt | `LLM` | `retry:{N}` | `harmonia.error_code`, `harmonia.retry_attempt`, `harmonia.retry_delay_seconds`, status=ERROR |
| Decision-point handling | `CHAIN` | `decision` | `harmonia.decision_mode`, `input.value` (agent question), `output.value` (decision text) |

Custom attribute namespace: all Harmonia-specific attributes use the `harmonia.*` prefix to avoid collision with OpenInference standard attributes.

---

## 2. Phase 1: Core Tracing + Token Forwarding (~6-8 days)

### 2.1 Modify Forked Archytas — Token Usage Forwarding

**File**: `/hpc/compgen/projects/llm_GEO_project/archytas/archytas/agent.py`

**Change A** — Add accumulator in `__init__()`:
```python
self._turn_usage_records: list[dict] = []
```

**Change B** — In `execute()`, after line 292 where `usage_metadata` is extracted and printed:
```python
if usage_metadata and isinstance(usage_metadata, dict):
    self._turn_usage_records.append({
        "input_tokens": usage_metadata.get("input_tokens", 0),
        "output_tokens": usage_metadata.get("output_tokens", 0),
        "total_tokens": usage_metadata.get("total_tokens", 0),
    })
```

**Change C** — Add accessor + reset methods:
```python
def get_and_reset_usage_records(self) -> list[dict]:
    """Return accumulated token usage records and reset."""
    records = self._turn_usage_records
    self._turn_usage_records = []
    return records
```

**File**: `/hpc/compgen/projects/llm_GEO_project/archytas/archytas/models/ollama.py`

**Change D** — Add `usage_metadata` extraction (Ollama's API does return token counts but the model class doesn't extract them). Pattern from `litellm_model.py:215-227`:
```python
usage_metadata = None
if hasattr(response, 'usage') and response.usage:
    usage_metadata = {
        'input_tokens': response.usage.prompt_tokens,
        'output_tokens': response.usage.completion_tokens,
        'total_tokens': response.usage.total_tokens,
    }
return AIMessage(content=content, tool_calls=tool_calls, usage_metadata=usage_metadata)
```

### 2.2 Modify Forked Beaker Kernel — Forward Usage to WebSocket

**File**: `/hpc/compgen/projects/llm_GEO_project/beaker-kernel/beaker_kernel/kernel.py`

**Change E** — In `llm_request()`, after `result = await task` (line 572):
```python
usage_records = []
if hasattr(self.context, 'agent') and hasattr(self.context.agent, 'get_and_reset_usage_records'):
    usage_records = self.context.agent.get_and_reset_usage_records()
```

**Change F** — In the `send_response()` calls for both `llm_response` (line 621-623) and `code_cell` (line 613-618), add `usage_records` to `stream_content`:
```python
if usage_records:
    stream_content["usage_records"] = usage_records
```

### 2.3 New File: `src/automation/tracing.py`

Encapsulates all Phoenix/OTel setup and span-creation helpers.

```python
"""
Phoenix/OpenTelemetry tracing for Harmonia experiments.

Exports OTel spans to a Phoenix server via OTLP HTTP.
All instrumentation is manual — no auto-patching.
"""

# Key exports:

def init_tracing(
    phoenix_endpoint: str,
    run_id: str,
    experiment_name: str,
    service_name: str = "harmonia",
) -> tuple[Tracer, bool]:
    """
    Configure OTel TracerProvider with OTLP HTTP exporter.

    Returns (Tracer, tracing_active: bool).
    If Phoenix is unreachable, returns a no-op tracer and False.
    """

@contextmanager
def experiment_span(
    tracer: Tracer,
    config: ExperimentConfig,
    run_id: str,
    trace_type: str = "annotation",
    parent_run_id: str | None = None,
) -> Generator[Span, None, None]:
    """
    Root AGENT span for the full experiment.
    Sets harmonia.run_id, harmonia.trace_type, harmonia.parent_run_id,
    llm.model_name, harmonia.llm_provider, harmonia.config_snapshot.
    """

@contextmanager
def turn_span(
    tracer: Tracer,
    turn_number: int,
    user_message: str,
) -> Generator[Span, None, None]:
    """CHAIN span for a conversation turn."""

@contextmanager
def llm_call_span(
    tracer: Tracer,
    call_index: int,
    model_name: str,
) -> Generator[Span, None, None]:
    """LLM span for an individual LLM API call within a turn."""

@contextmanager
def tool_span(
    tracer: Tracer,
    tool_name: str,
    code: str,
) -> Generator[Span, None, None]:
    """TOOL span for a Beaker code execution."""

def set_llm_usage(
    span: Span,
    usage: dict,
    pricing: ModelMetadataConfig,
) -> None:
    """Set token count and cost attributes on an LLM span."""

def extract_code_executions(raw_messages: list[dict]) -> list[dict]:
    """
    Parse raw WebSocket messages to extract structured code executions.

    Returns list of dicts with keys: code, stdout, stderr, status, duration_seconds.
    Looks for beaker__execute_input → execute_result/stream/error sequences.
    """

def extract_usage_records(raw_messages: list[dict]) -> list[dict]:
    """
    Extract usage_records from the final llm_response or code_cell message.

    Returns list of dicts with keys: input_tokens, output_tokens, total_tokens.
    """
```

Dependencies to add to `.venv`:
```
arize-phoenix-otel
opentelemetry-api>=1.20
opentelemetry-sdk>=1.20
opentelemetry-exporter-otlp-proto-http
openinference-semantic-conventions>=0.1.5
```

These are installed in the project `.venv` (not inside the container) because the automation runner runs outside the container.

### 2.4 Modified: `src/automation/logger.py`

**Enrich `TurnRecord`** with new optional fields (backward-compatible defaults):

```python
@dataclass
class TurnRecord:
    turn: int
    user_message: str
    agent_response: str
    response_type: str
    tool_calls: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    raw_messages: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # New fields (Phase 1)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    code_executions: list[dict] = field(default_factory=list)
    usage_records: list[dict] = field(default_factory=list)  # per-LLM-call breakdown
```

**Enrich `ExperimentTrace.to_dict()`** to include the new fields in output.

**Add `config_snapshot`** field to `ExperimentTrace`:
```python
config_snapshot: Optional[dict] = None  # full YAML config that produced this run
```

**Enrich `TraceLogger.log_turn()`** to accept and store the new fields.

### 2.5 Modified: `src/automation/runner.py`

**In `__init__()`**:
- Call `init_tracing()` with endpoint from `TracingConfig`. Store `Tracer` and `tracing_active` flag.
- Snapshot the config YAML into the trace logger.

**In `run()`**:
- Wrap the experiment loop in `experiment_span()`. Set final status/error on the root span at completion.
- After saving `trace.json`, also copy the experiment YAML config to the results directory as `config_snapshot.yaml`.

**In `_run_turn()`**:
- Wrap each turn in `turn_span()`.
- After receiving the `AgentResponse`, call `extract_usage_records(response.raw_messages)` to get per-LLM-call token data.
- For each usage record, create a child `llm_call_span()` with token counts and cost (calculated from `ModelMetadataConfig.pricing_*`).
- Call `extract_code_executions(response.raw_messages)` to get structured code execution data. For each, create a child `tool_span()`.
- Pass the enriched data to `trace_logger.log_turn()`.

**In `_send_with_retries()`**:
- On each retry, create a child `llm_call_span()` marked with error status and the `error_code`.

### 2.6 Modified: `src/automation/manual_runner.py`

Same span wrapping as `runner.py`:
- `start()`: open root `experiment_span()`
- `_handle_message()`: when a turn completes, create `turn_span()` with child `llm_call_span()` and `tool_span()` spans.

### 2.7 Modified: `src/automation/config.py`

**Add `TracingConfig` dataclass**:

```python
@dataclass
class TracingConfig:
    enabled: bool = False
    phoenix_endpoint: str = "http://localhost:6006"
```

**Add to `ExperimentConfig`**:
```python
tracing: TracingConfig = field(default_factory=TracingConfig)
```

**Update `from_dict()`** to parse the `tracing:` YAML section:
```python
tracing_data = data.get("tracing", {})
tracing = TracingConfig(
    enabled=tracing_data.get("enabled", False),
    phoenix_endpoint=tracing_data.get("phoenix_endpoint", "http://localhost:6006"),
)
```

### 2.8 New File: `scripts/ensure_phoenix_server.py`

Python CLI script that ensures exactly one Phoenix server is running. Called by `exec_apptainer_harmonia.sh` before launching experiments.

**Behavior**:

```
ensure_phoenix_server.py [--mode submit|slurm] [--port 6006] [--timeout 120]
                         [--phoenix-dir .phoenix]

1. Acquire file lock on .phoenix/server.lock (flock, blocks up to 30s)
2. Check for running Phoenix:
   --mode=slurm:  squeue -u $USER --name=llm-tracing-phoenix-arize --states=RUNNING,PENDING -h
   --mode=submit: check if screen session "phoenix-tracing" exists and process is alive
3. If running:
   - For slurm: get node name from squeue output, construct endpoint http://<node>:6006
   - For submit: endpoint is http://localhost:6006
   - Print endpoint to stdout, release lock, exit 0
4. If not running:
   --mode=slurm:
     - Submit: srun --job-name=llm-tracing-phoenix-arize --account=compgen
               --time=08:00:00 --mem=2G --cpus-per-task=1 --nice=1000
               .venv/bin/phoenix serve --port 6006
       Run inside a screen session: screen -dmS phoenix-tracing srun ...
     - Wait for job to reach RUNNING state (poll squeue, max --timeout seconds)
     - Get node name, construct endpoint
   --mode=submit:
     - screen -dmS phoenix-tracing .venv/bin/phoenix serve --port 6006
     - Wait for http://localhost:6006/healthz to return 200
   - Print endpoint to stdout, release lock, exit 0
5. On failure: print error to stderr, release lock, exit 1
```

**Environment variable**: Sets `PHOENIX_WORKING_DIR` to the absolute path of `--phoenix-dir` before starting Phoenix.

**Output**: Prints `PHOENIX_ENDPOINT=http://<host>:<port>` to stdout. The calling script captures this.

**Default mode**: `submit` (submit node). Configurable via `--mode slurm` for compute-node deployment.

### 2.9 Modified: `exec_apptainer_harmonia.sh`

Add a block before the Apptainer exec call:

```bash
# --- Phoenix tracing server ---
TRACING_ENABLED=$(python3 -c "
import yaml, sys
with open('$CONFIG_FILE') as f:
    cfg = yaml.safe_load(f)
print(cfg.get('tracing', {}).get('enabled', False))
" 2>/dev/null)

if [ "$TRACING_ENABLED" = "True" ]; then
    PHOENIX_INFO=$(.venv/bin/python scripts/ensure_phoenix_server.py \
        --phoenix-dir .phoenix \
        --mode "${PHOENIX_MODE:-submit}" \
        --port "${PHOENIX_PORT:-6006}" \
        2>&1)
    if [ $? -eq 0 ]; then
        export PHOENIX_ENDPOINT=$(echo "$PHOENIX_INFO" | grep "PHOENIX_ENDPOINT=" | cut -d= -f2)
        echo "Phoenix tracing: $PHOENIX_ENDPOINT"
    else
        echo "Warning: Could not start Phoenix server. Tracing disabled for this run."
        echo "$PHOENIX_INFO"
    fi
fi
```

The `PHOENIX_ENDPOINT` environment variable is then available to the automation runner (which runs outside the container).

### 2.10 Modified: `.gitignore`

Add:
```
.phoenix/
```

### 2.11 Experiment YAML Config Addition

Add a `tracing:` block to experiment configs (can be added via `manage_configs.py` or manually):

```yaml
tracing:
  enabled: true
  phoenix_endpoint: "http://localhost:6006"  # overridden by ensure_phoenix_server.py
```

### 2.12 Config Snapshot in Results Directory

At the start of each experiment, copy the YAML config file to the results directory as `config_snapshot.yaml`. This closes the "Run-level experiment config" gap from the research report.

Implementation: In `ExperimentRunner.__init__()`, after creating the output directory:
```python
import shutil
config_path = Path(config_path_from_somewhere)
shutil.copy2(config_path, self.output_dir / "config_snapshot.yaml")
```

This requires passing the config file path through to the runner. Currently `ExperimentConfig` is passed as a parsed object. Options:
- Add `config_source_path: Optional[str] = None` to `ExperimentConfig`
- Or serialize `ExperimentConfig` back to YAML (less ideal, loses comments)

### 2.13 Rebuild Apptainer Image

After Archytas and Beaker changes are made:

```bash
srun --time=02:00:00 --mem=32G --gres=tmpspace:100G --account=compgen \
    bash build_harmonia_apptainer.sh
```

This is the final step of Phase 1. The build script already copies from the forked Archytas/Beaker source trees.

---

## 3. Phase 2: Visualization Integration + Log Enrichment (~3-4 days)

Deferred until Phase 1 is validated with at least one experiment batch.

### 3.1 Export `spans.parquet` Alongside `trace.json`

Add to `tracing.py`:
```python
def export_run_spans(run_id: str, phoenix_endpoint: str, output_dir: Path) -> Optional[Path]:
    """
    Export all spans for a run_id to a parquet file.
    Uses phoenix.Client().get_spans_dataframe().
    Returns path to spans.parquet or None if Phoenix is unreachable.
    """
```

Called at the end of `ExperimentRunner.run()` after saving trace.json.

### 3.2 Enrich Log Analysis CLI with `--phoenix` Flag

**File**: `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`

Add `--phoenix` flag. When set:
- Read `spans.parquet` from the results directory (if present)
- Enrich failure analysis with token counts, cost estimates, per-span error data
- Add summary line: "Turn 3 used 14,200 input tokens at $0.021"
- The existing 13-category failure taxonomy remains unchanged

### 3.3 Trace Links in `visualize_metrics_cli.py`

**File**: `src/evaluation/visualize_metrics_cli.py`

- When `--backend plotly` is used, add clickable links to Phoenix trace URLs in bar charts and tables
- Add `input_tokens`, `output_tokens`, `total_cost_usd` columns to summary tables
- Read token/cost data from `spans.parquet` or enriched `trace.json`

### 3.4 `phoenix_server.sh` Convenience Script

Wrapper script for manual Phoenix management:
```bash
#!/bin/bash
# Usage: ./scripts/phoenix_server.sh start|stop|status|ui
# start: ensure server is running
# stop: stop server
# status: show server status
# ui: print SSH port-forwarding command
```

---

## 4. Future: Critic Evaluation Tracing

When the LLM-as-critic workflow is implemented, the tracing architecture supports it without structural changes:

### Trace Linking

- Original annotation run: root span has `harmonia.trace_type = "annotation"`, `harmonia.run_id = "abc12345"`
- Critic evaluation run: root span has `harmonia.trace_type = "critic_evaluation"`, `harmonia.parent_run_id = "abc12345"`, `harmonia.run_id = "def67890"`
- Re-annotation run (if critic triggers retry): `harmonia.trace_type = "re_annotation"`, `harmonia.parent_run_id = "def67890"` (links to critic), additional attribute `harmonia.original_run_id = "abc12345"` (links to original)

### Querying

```python
import phoenix as px

client = px.Client(endpoint="http://localhost:6006")

# Find all critic evaluations of a specific annotation run
df = client.get_spans_dataframe(
    filter_condition="span_kind == 'AGENT' and attributes['harmonia.parent_run_id'] == 'abc12345'"
)

# Find annotation runs that were re-annotated
df = client.get_spans_dataframe(
    filter_condition="span_kind == 'AGENT' and attributes['harmonia.trace_type'] == 're_annotation'"
)
```

### Phoenix Annotations

Additionally, Phoenix's built-in annotation feature can attach critic scores directly to spans in the original trace:
```python
client.annotate_span(
    span_id=original_span_id,
    name="critic_score",
    score=0.85,
    label="mostly_correct",
    explanation="Critic found 2 minor mapping errors in columns X, Y"
)
```

This enables filtering traces by critic quality in the Phoenix UI.

---

## 5. Dependencies and Installation

### Project `.venv` (automation runner, outside container)

```bash
cd harmonia_metadata_agent/analysis/dstoker/harmonia
.venv/bin/pip install \
    arize-phoenix \
    arize-phoenix-otel \
    opentelemetry-api>=1.20 \
    opentelemetry-sdk>=1.20 \
    opentelemetry-exporter-otlp-proto-http \
    openinference-semantic-conventions>=0.1.5
```

### Inside the container

No Phoenix dependencies needed inside the container. The only container changes are the Archytas/Beaker modifications for token forwarding (no new pip packages).

---

## 6. File Change Summary

### New Files

| File | Purpose |
|------|---------|
| `src/automation/tracing.py` | OTel/Phoenix setup, span helpers, code execution extraction |
| `scripts/ensure_phoenix_server.py` | Phoenix server lifecycle management CLI |

### Modified Files

| File | Change |
|------|--------|
| `/hpc/.../archytas/archytas/agent.py` | Store `usage_metadata` in `_turn_usage_records` accumulator (~15 lines) |
| `/hpc/.../archytas/archytas/models/ollama.py` | Extract `usage_metadata` from Ollama response (~10 lines) |
| `/hpc/.../beaker-kernel/beaker_kernel/kernel.py` | Forward `usage_records` in WebSocket messages (~10 lines) |
| `src/automation/runner.py` | Wrap experiment/turn/retry in OTel spans, extract token data |
| `src/automation/manual_runner.py` | Same span wrapping for manual experiments |
| `src/automation/logger.py` | Add token/cost/code_execution fields to `TurnRecord` |
| `src/automation/config.py` | Add `TracingConfig` dataclass and parsing |
| `exec_apptainer_harmonia.sh` | Call `ensure_phoenix_server.py`, pass `PHOENIX_ENDPOINT` |
| `.gitignore` | Add `.phoenix/` |

### Rebuild Required

| Artifact | Trigger |
|----------|---------|
| `harmonia_beaker_LLM_agent_environment_apptainer.sif` | After Archytas + Beaker changes |

---

## 7. Testing Plan

### Phase 1 Validation

1. **Token forwarding**: Run a single experiment with OpenRouter model. Verify `usage_records` appears in `raw_messages` of `trace.json`. Check `input_tokens` and `output_tokens` are non-zero on `TurnRecord`.

2. **Phoenix spans**: Start Phoenix server manually (`phoenix serve`). Run an experiment with `tracing.enabled: true`. Open Phoenix UI and verify:
   - Root AGENT span with correct `harmonia.run_id`
   - CHAIN spans for each turn with correct `harmonia.turn_number`
   - LLM spans with token counts
   - TOOL spans for code executions

3. **Parallel experiments**: Launch 3 experiments simultaneously with tracing enabled. Verify all traces appear in Phoenix UI without data corruption.

4. **Server lifecycle**: Test `ensure_phoenix_server.py` in both `submit` and `slurm` modes. Verify it handles: no server running, server already running, parallel invocations (race condition via flock).

5. **Ollama token counts**: Run an experiment with an Ollama model. Verify token counts are captured (tests the `ollama.py` change).

6. **Backward compatibility**: Run an experiment with `tracing.enabled: false`. Verify `trace.json` and `conversation.md` are identical in structure to pre-change output (new fields present with default values).

---

## 8. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Phoenix server down during experiment | Tracing is best-effort. `init_tracing()` returns `tracing_active=False` if unreachable. `trace.json` is always written regardless. |
| SQLite contention from parallel experiments | `BatchSpanProcessor` buffers spans. SQLite single-writer lock releases in milliseconds. Monitor for errors; escalate to PostgreSQL if needed. |
| Token counts unavailable for some providers | Best-effort per provider. Ollama fixed in this plan. Other providers already work via litellm. Log a warning when tokens are zero. |
| Apptainer network isolation blocks OTLP | Apptainer shares host network namespace by default. `localhost:6006` resolves to host. If custom namespace used, use host IP instead. |
| Container rebuild fails | Build script has verification phases. Test key imports after build. |
