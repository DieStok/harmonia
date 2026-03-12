# Research Report: LLM Agent Tracing and Observability for Harmonia

**Date**: 2026-03-03
**Author**: Claude Code (automated research)
**Purpose**: Primary input for framework evaluation subagents

---

## 1. Current Logging -- What Is Captured and What Is Missing

### 1.1 Source Files Inspected

| File | Path | Role |
|------|------|------|
| `logger.py` | `src/automation/logger.py` | `TraceLogger` (JSON trace), `ConversationLogger` (Markdown) |
| `prompt_logging.py` | `src/prompt_logging.py` | One-shot prompt composition capture (`full_prompt_composition.json`) |
| `read_and_analyze_logs_and_traces_cli.py` | `code_development_tools_agents/monitoring_and_evaluation/` | Post-hoc trace analysis with 13 failure mode categories |
| `types_of_log_and_trace_problems.yaml` | Same directory | YAML taxonomy of failure modes |
| `visualize_metrics_cli.py` | `src/evaluation/visualize_metrics_cli.py` | Metrics aggregation and plotting |

### 1.2 Example Artifacts Inspected

- **trace.json** from `results/dou_harmonization_code-context_gemini-3-flash-preview_20260302_170745_58fa9479/`
  - 8 turns, status=completed, total_duration=64.2s
  - Top-level keys: `experiment`, `llm`, `timing`, `status`, `error_message`, `turns`
  - Per-turn: `turn`, `user_message`, `agent_response`, `response_type`, `tool_calls`, `duration_seconds`, `raw_messages`, `timestamp`

- **full_prompt_composition.json** from a Claude Sonnet run
  - Keys: `metadata` (run_id, experiment_name, context_type, model_class, prompt_config), `layers` (system_message, auto_context_message, model_prompt_instructions), `messages_sent_to_llm`, `summary`

- **Results directory contents**: `trace.json`, `conversation.md`, `metrics.json`, `column_mapping.json`, `value_mapping.json`, `dou_harmonized.csv`, `dou_gdc.csv`

### 1.3 What IS Currently Captured

| Data Point | Where | Detail |
|------------|-------|--------|
| Experiment metadata | trace.json | Name, description, LLM provider, model |
| Timing | trace.json | Start/end timestamps, per-turn duration, total duration |
| User messages (scripted prompts) | trace.json, conversation.md | Full text of each automated prompt |
| Agent final response | trace.json, conversation.md | Text response from the LLM (often empty when agent executes code) |
| Response type | trace.json | `llm_response`, `timeout`, `code_cell` |
| Raw Beaker WebSocket messages | trace.json `raw_messages` | Full Jupyter message stream including `status`, `beaker__execute_input`, `beaker__execute_reply`, `execute_result`, `stream`, `error` |
| Initial prompt composition | full_prompt_composition.json | System message, auto-context, model-specific instructions, env vars, content hashes (one-shot, first LLM call only) |
| Experiment status | trace.json | `running`, `completed`, `failed`, `timeout` |
| Error messages | trace.json | Top-level error_message field |
| Kernel state budget metadata | trace.json (inside raw_messages) | `_budget_metadata` with dropped_count, unchanged_count, budget sizes |
| Quantitative evaluation | metrics.json | Column mapping accuracy, per-column value accuracy/F1/precision/recall, confusion matrices |
| Failure mode classification | CLI tool output | 13 categories (1A-6A) detected by compound logic over logs + traces |
| Human-readable conversation log | conversation.md | Markdown-formatted user/agent exchanges |

### 1.4 What IS NOT Captured (Gaps)

| Gap | Severity | Detail |
|-----|----------|--------|
| **Token counts** | High | No `input_tokens`, `output_tokens`, `total_tokens` per turn or per LLM API call |
| **Cost per turn/run** | High | No cost tracking despite OpenRouter providing pricing in the model registry |
| **Individual LLM API calls within a turn** | High | A single "turn" in the ReAct loop may involve multiple LLM invocations (thought/action/observation cycles), but only the final agent_response is captured at the turn level |
| **Tool call structured data** | High | The `tool_calls` field exists on TurnRecord but is always empty in all inspected traces. Actual tool use (Beaker code execution) is only visible in `raw_messages` as `beaker__execute_input` messages |
| **Code execution results** | Medium | Code outputs are buried in raw_messages (`execute_result`, `stream`, `error` msg_types) but not surfaced as structured, queryable data |
| **Prompt evolution across turns** | Medium | Only the initial prompt composition is captured (one-shot via `register_prompt_json_logger`). The growing conversation history sent to the LLM at each subsequent turn is not logged |
| **Model parameters** | Medium | Temperature, top_p, max_tokens, etc. are not logged |
| **Nested span hierarchy** | Medium | Everything is flat turns; no parent-child span tree (Turn -> LLM call -> Tool use -> Code execution) |
| **Retry/error recovery** | Medium | If the LLM call is retried due to transient errors, retry attempts are not tracked |
| **Kernel state per turn** | Low | The budget-enforced state serialization is sent to the LLM but not separately logged per turn |
| **Run-level experiment config** | Low | The full YAML config that produced the run is not saved in the results directory |
| **Intermediate reasoning** | Low | The ReAct thought/action/observation chain within each turn is not explicitly decomposed |

### 1.5 Structural Observations

1. **`tool_calls` is a dead field**: In every trace inspected, `tool_calls` is `[]`. The actual tool invocations (code execution via Beaker's `run_code`) are only discoverable by parsing `raw_messages` for `beaker__execute_input` msg_type entries. This makes automated analysis of tool usage difficult.

2. **`agent_response` is frequently empty**: Many turns show `agent_response: ""` even though the turn succeeded -- because the LLM's output was code that Beaker executed (the result appears in raw_messages), not text returned to the user. The conversation.md correspondingly shows empty agent responses.

3. **raw_messages is extremely verbose**: A single turn can have 8-42 raw WebSocket messages, including large kernel state introspection code blocks (hundreds of lines of Python that fetch kernel state). This inflates trace.json files to 200-300KB per run.

4. **No semantic span kinds**: There is no classification of what each operation within a turn is (LLM call vs. tool invocation vs. code execution vs. state inspection). Everything is a flat list of raw Jupyter messages.

---

## 2. Desiderata -- What an Ideal Tracing and Visualization System Would Provide

### 2.1 Core Tracing Requirements

| Requirement | Priority | Rationale |
|-------------|----------|-----------|
| **Token accounting** per LLM call | P0 | Essential for cost analysis across 10+ models; already have pricing data in model registry |
| **Cost tracking** per turn and per run | P0 | OpenRouter provides per-model pricing; this enables ROI analysis |
| **Nested span hierarchy** | P0 | Turn -> LLM call(s) -> Tool use -> Code execution -> State inspection. Enables understanding of what happens within a turn |
| **Structured tool/code execution spans** | P0 | Each Beaker code execution should be a first-class span with input code, stdout/stderr, execution result, and errors |
| **Model parameters logging** | P1 | Temperature, max_tokens, top_p, etc. at each LLM call |
| **Full prompt at each turn** | P1 | The actual messages array sent to the LLM at every turn, not just the first call |
| **Run config preservation** | P1 | Copy of the experiment YAML saved in the results directory |
| **Retry tracking** | P2 | Number of retries, which errors triggered them, backoff timing |
| **Kernel state snapshots** | P2 | Per-turn snapshots of what the LLM "sees" as kernel context |

### 2.2 Visualization and Interaction Requirements

| Requirement | Priority | Rationale |
|-------------|----------|-----------|
| **Turn-by-turn trace viewer** | P0 | Step through conversation turns with expandable details (user prompt, agent response, code executed, output, errors, timing) |
| **Side-by-side trace comparison** | P0 | Select 2+ runs (e.g., same task, different models) and view their traces in parallel with aligned turns |
| **Click-through from metrics to traces** | P0 | From a bar chart of model accuracy, click a specific bar to jump to that run's trace |
| **Search and filter** | P1 | Find traces by model, status, error type, time range, experiment name, tags |
| **Latency waterfall** | P1 | Timeline view showing duration of each span within a turn |
| **Annotation support** | P2 | Mark specific turns as correct/incorrect, add notes for qualitative analysis |
| **Cost/token dashboard** | P2 | Aggregate views of token usage and cost across models and experiment configurations |

### 2.3 Deployment Constraints

| Constraint | Detail |
|------------|--------|
| **HPC environment** | Runs on SLURM-managed cluster nodes; no root/sudo; no Docker daemon (Apptainer/Singularity only) |
| **Network access** | Compute nodes have limited outbound network; no guaranteed persistent services between jobs |
| **Port forwarding** | Interactive tools must work via SSH port forwarding from local machine |
| **Python 3.11** | Project venv uses Python 3.11 |
| **File-based persistence preferred** | SQLite or file-based storage strongly preferred over PostgreSQL/ClickHouse/Redis which require persistent services |
| **Minimal infrastructure** | Fewer services = better; the tracing system should not require more infrastructure than the experiments themselves |

---

## 3. Framework Landscape -- Structured Comparison

### 3.1 Candidate Frameworks

Based on the landscape analysis (see `docs/my_instructions/initial_info_LLM_tracing.md`), four candidates are carried forward for detailed evaluation:

#### 3.1.1 Langfuse (MIT License)

**Architecture**: Sessions > Traces > Observations (10 observation types including generation, agent, tool, chain). v3 uses PostgreSQL + ClickHouse + MinIO + Redis (4 backing services + 2 app containers).

**Manual instrumentation**: First-class support via `@observe` decorators, context managers, and low-level SDK. No auto-patching required. Full control over trace structure.

**GUI**: Web UI with tree/timeline trace views, custom dashboards, filterable trace tables, session replay. No dedicated side-by-side trace diff view (comparison via dashboards/experiments).

**Data persistence**: Self-hosted via Docker Compose. Minimum 4 vCPUs, 16 GB RAM. Data export via SDK (Python API), UI (JSON), and scheduled blob storage exports (JSON/JSONL/CSV).

**Strengths**: Most feature-complete platform; MIT license; 22.6k GitHub stars; rich data export; OTel-native.
**Weaknesses**: Heavy infrastructure (6 containers); no simple SQLite mode; complex for HPC deployment without Docker.

#### 3.1.2 Arize Phoenix (Elastic License v2)

**Architecture**: Built on OpenTelemetry + OpenInference semantic conventions. 10 span kinds (LLM, AGENT, TOOL, CHAIN, RETRIEVER, etc.). Accepts standard OTLP traces.

**Manual instrumentation**: Full support via `phoenix.otel.register()` + standard OTel TracerProvider. Decorators (`@tracer.chain`, `@tracer.llm`, `@tracer.tool`, `@tracer.agent`). Raw OTel context managers also work.

**GUI**: Web UI at port 6006 with traces table, spans table, trace detail/waterfall, timeline view, UMAP embedding visualization, agents tab. Annotations and evaluations. No explicit side-by-side trace comparison (comparison via datasets/experiments).

**Data persistence**: **SQLite by default** (`~/.phoenix/`), PostgreSQL optional. Lightweight single-process deployment (`pip install arize-phoenix && phoenix serve`). Export via `get_spans_dataframe()`, SpanQuery DSL, or trace dataset save.

**Strengths**: Lightest deployment footprint (single pip install, SQLite); OTel-native; Python >= 3.10; UMAP embedding viz unique feature; strong export-to-DataFrame pipeline.
**Weaknesses**: ELv2 (not pure open source); no dedicated side-by-side trace comparison; smaller ecosystem than Langfuse.

#### 3.1.3 Opik (Apache 2.0 License)

**Architecture**: Trace > Span hierarchy with 4 span types (general, tool, llm, guardrail). ClickHouse + MySQL + Redis + MinIO + Zookeeper (5 backing services + 3 app containers = 8 containers total).

**Manual instrumentation**: Full support via low-level client API (`client.trace()`, `trace.span()`), context managers, and `@track` decorator. Token usage and cost fields are first-class on span objects.

**GUI**: Web UI at port 5173 with trace table (OQL filtering), single-trace drill-down, span-level metrics, experiment comparison/leaderboard, pre-built dashboard templates, CSV export.

**Data persistence**: Self-hosted via Docker Compose or Kubernetes. Export via Python SDK (`search_traces`/`search_spans`), CLI (`opik export`), REST API, UI CSV. Data stored in `~/opik`.

**Strengths**: Apache 2.0 license; Agent Optimizer SDK for prompt tuning; evaluation framework built in; experiment leaderboard; 40M+ traces/day scale.
**Weaknesses**: Heaviest infrastructure (8 containers); not production-ready in Docker Compose mode; youngest ecosystem; no SQLite mode.

#### 3.1.4 Custom Dash Dashboard

**Architecture**: Custom Python web application using Plotly Dash. Reads existing trace.json and metrics.json files directly. No new tracing infrastructure -- purely a visualization layer.

**Manual instrumentation**: N/A -- uses existing logging output as-is. Could add structured enrichments to existing logger.py.

**GUI**: Fully custom. Plotly charts for metrics, Dash AG Grid for run tables, accordion/details components for trace viewing, callback-based click-through from charts to traces, column layout for side-by-side comparison.

**Data persistence**: File-based (reads existing JSON files directly). No database required.

**Strengths**: Zero infrastructure overhead; works with existing data format; full customization; SSH port-forwarding friendly; no vendor dependency; ~7 developer-days effort.
**Weaknesses**: No out-of-the-box tracing instrumentation; requires building everything from scratch; no trace capture improvements (only visualization); no evaluation/annotation framework; single developer maintenance burden.

### 3.2 Comparison Matrix

| Criterion | Langfuse | Phoenix | Opik | Custom Dash |
|-----------|----------|---------|------|-------------|
| **Manual instrumentation** | Excellent | Excellent | Excellent | N/A (viz only) |
| **Trace data model** | Rich (10 obs types) | Rich (10 span kinds, OTel) | Good (4 span types) | N/A |
| **Token/cost tracking** | Yes (generation obs) | Yes (span attributes) | Yes (first-class fields) | Manual add |
| **GUI: trace drill-down** | Yes (tree + timeline) | Yes (tree + timeline) | Yes (tree) | Must build |
| **GUI: side-by-side comparison** | No (via dashboards) | No (via experiments) | Experiment comparison | Must build |
| **GUI: click-through metrics->trace** | No built-in | No built-in | No built-in | Yes (native Dash) |
| **Infrastructure weight** | Heavy (6 containers) | **Light (1 process, SQLite)** | Very heavy (8 containers) | **None** |
| **HPC compatibility** | Poor (needs Docker) | **Good (pip install)** | Poor (needs Docker) | **Excellent** |
| **Data export** | SDK + API + UI + blob | DataFrame + SpanQuery | SDK + CLI + API + UI | Direct file access |
| **License** | MIT | ELv2 | Apache 2.0 | N/A |
| **GitHub stars** | 22.6k | 8.7k | Growing | N/A |
| **Evaluation framework** | Built-in | Built-in | Built-in + Optimizer | None |
| **Estimated integration effort** | 3-5 days | 2-3 days | 3-5 days | 5-7 days |

### 3.3 Key Trade-offs

1. **Infrastructure vs. Features**: Langfuse and Opik offer the most features but require the most infrastructure. Phoenix offers a middle ground. Custom Dash has zero infrastructure but no trace capture improvements.

2. **Trace capture vs. Visualization**: The first three frameworks improve both tracing AND visualization. Custom Dash only improves visualization, leaving the existing logging gaps (token counts, cost, nested spans) unaddressed.

3. **HPC deployment feasibility**: Phoenix is the only platform framework that can run with `pip install` and SQLite, making it viable on HPC without Docker/Apptainer for the tracing server. Langfuse and Opik require Docker Compose with multiple persistent services.

4. **Side-by-side trace comparison**: None of the platform frameworks offer a dedicated side-by-side trace comparison view out of the box. This is a key desideratum that may require custom development regardless of framework choice.

5. **Metrics-to-trace click-through**: None of the platform frameworks natively integrate with the existing `visualize_metrics_cli.py` evaluation plots. A custom visualization layer (Dash or Streamlit) would be needed to bridge the two regardless.
