# SRAgent vs Harmonia Metadata Agent: Architectural Comparison

**Date:** 31-03-2026 | **Analyst:** Comparative Architecture Analysis

---

## 1. Comparison Table

| Axis | SRAgent | Harmonia Metadata Agent |
|------|---------|------------------------|
| **Overall architecture** | Multi-agent pipeline; custom-built LangGraph orchestration | Single-agent + external kernel; Beaker server mediates all LLM-to-tool interaction |
| **Agent orchestration** | 3-tier agent hierarchy (supervisor -> specialist -> tool) with LangGraph `create_react_agent` | Flat: one Archytas ReActAgent or one custom CodeActAgentLoop, no sub-agents |
| **Prompt management** | Static `"\n".join([...])` strings in Python source; no templating engine | Jinja2 templates (`src/bdikit_context/prompts/`); per-experiment overrides via env vars |
| **Context/memory** | Message history windowing (`state["messages"][-4:]`); XML/JSON truncation utilities | Kernel state budget enforcement (`context_management/`); CodeAct summarize/truncate strategies |
| **Tool integration** | LangChain `@tool` decorator; agents-as-tools composability | Archytas `@tool()` decorator running code via Beaker subkernel `context.evaluate()` |
| **Error handling** | Structured output retry on OpenAIRefusalError; flex-tier fallback; multi-source cascades | Retry policy per error code (`retry_policy` in YAML); OpenRouter hardening monkey-patch |
| **Configuration** | Dynaconf `settings.yml` with 3 environments; per-agent model/temp/reasoning settings | YAML per-experiment config -> `generate_env.py` -> `.env` -> Apptainer container env vars |
| **Code modularity** | 4-layer package: `cli/`, `agents/`, `tools/`, `workflows/`, `db/` | 6 distinct modules: `automation/`, `bdikit_context/`, `codeact_context/`, `code_context/`, `evaluation/`, `dashboard/` |
| **Testing** | pytest mirroring package structure; CLI smoke tests; no LLM mocking | 46 tests for config loading, metrics, ollama launcher; no LLM interaction tests |
| **Evaluation** | Database-backed evaluation with `scripts/`; no standardized metrics schema | Dedicated `evaluation/` package with Pydantic `MetricsResult` schema (v1.1); visualization CLI |
| **Documentation** | README.md + AGENTS.md; inline docstrings | Versioned codebase descriptions (`docs/codebase_descriptions/`); process docs; failure taxonomy |

---

## 2. Detailed Narrative Analysis

### 2.1 Overall Architecture Pattern

**SRAgent** is a **multi-agent pipeline** system. The user invokes a CLI command, which dispatches to a LangGraph state machine composed of multiple ReAct agents. These agents call each other hierarchically (up to 4 levels deep), with the top-level `sragent` supervisor deciding which specialist to invoke. The system is monolithic in deployment (single Python package) but internally decomposed into independent agents with clear specializations.

Reference: `SRAgent/agents/sragent.py` (supervisor), `SRAgent/workflows/metadata.py` (sequential pipeline), `SRAgent/workflows/srx_info.py` (fan-out/fan-in).

**Harmonia** is a **single-agent + external infrastructure** system. A Beaker kernel server runs inside an Apptainer container, hosting a Jupyter-protocol kernel with either Archytas ReAct or a custom CodeAct loop. The automation framework (`src/automation/`) sits *outside* the container, connecting via WebSocket to send scripted messages and capture responses. There is no agent hierarchy -- the single agent uses BDI-Kit tools directly.

Reference: `src/automation/client.py:BeakerClient` (WebSocket client), `src/bdikit_context/context.py:BDIKitContext` (Beaker context), `src/bdikit_context/agent.py:BDIKitAgent` (single agent with 5 tools).

**Key insight:** SRAgent's multi-agent design means the orchestration intelligence is distributed across multiple LLMs, each with focused prompts and tools. Harmonia concentrates all intelligence in a single LLM conversation, relying on detailed system prompts and human-like scripted messages to guide the workflow. This makes Harmonia simpler to deploy but harder to debug when the agent goes off-track mid-conversation.

### 2.2 Agent Orchestration Model

**SRAgent** uses LangGraph's `create_react_agent` with agents-as-tools:
- A supervisor agent receives the task and decides which specialist to delegate to
- Specialists execute deterministic tools and return results
- The supervisor analyzes results and decides next steps
- `Send()` enables parallel processing of multiple items (e.g., multiple SRX accessions)

The factory pattern (`create_<name>_agent(return_tool=True)`) is consistent across all 15 agents, enabling uniform composition.

**Harmonia** has no orchestration layer between agents:
- The single Archytas `ReActAgent` (or `CodeActAgentLoop`) receives user messages sequentially
- Tool calls are mediated by Beaker's kernel protocol
- The `ExperimentRunner` (`src/automation/runner.py`) drives the conversation by sending pre-scripted messages, but it has no awareness of agent state or strategy
- Decision points are handled by pattern matching on agent output (`_is_decision_point()` at line 369)

**Key insight:** SRAgent's multi-agent orchestration allows each agent to have a focused context window and specialized prompt. Harmonia's single-agent model means the system prompt must cover the entire harmonization workflow, and the agent must maintain context across all steps in a single conversation.

### 2.3 Prompt Management Approach

**SRAgent** uses **hardcoded prompt strings** assembled via `"\n".join([...])` in each agent's factory function:
- 18 agent-level system prompts, 7 workflow-level prompts
- No templating engine; variables injected via Python `.format()` or `ChatPromptTemplate`
- Few-shot examples are procedural (describing which tools to call, not input/output pairs)
- All prompts are in Python source files, not separate files

Reference: `SRAgent/agents/entrez.py` lines 41-83, `SRAgent/workflows/metadata.py` lines 183-196.

**Harmonia** uses **Jinja2 templates** with environment-variable overrides:
- System prompt in `src/bdikit_context/prompts/system/main.j2` -- a single template for the entire workflow
- Tool descriptions can be overridden per-experiment via `HARMONIA_TOOL_PROMPTS_DIR`
- ReAct prelude customizable via `HARMONIA_REACT_PRELUDE`
- Versioned prompt variants stored in `experiments/.../configs/prompts/`
- `PromptLoader` class provides clean separation of prompt content from code

Reference: `src/bdikit_context/prompts/__init__.py:PromptLoader`, `src/bdikit_context/context.py` lines 36-78.

**Key insight:** Harmonia's Jinja2 approach is more maintainable and experiment-friendly, enabling A/B testing of prompt variants without code changes. SRAgent's inline prompts are harder to modify and version but have the advantage of proximity to the code that uses them.

### 2.4 Context/Memory Management

**SRAgent** manages context through:
- XML/JSON truncation: `tools/utils.py:truncate_values()` limits field lengths (500-1000 chars)
- Message history windowing: Router prompts use only the last 4 messages
- Batch size limits: Entrez queries use configurable `retmax` and `batch_size`
- Per-agent `max_tokens` settings
- Token counting is implicit (no explicit budget tracking)

**Harmonia** manages context through:
- Kernel state budget enforcement: `context_management/kernel_state_budget.py` patches Beaker's `FETCH_STATE_CODE` to limit Python variable serialization (configurable `max_variable_size`, `state_budget_pct`, type blacklist, variable whitelist)
- CodeAct context window management: `src/codeact_context/agent.py` implements three strategies:
  - `summarize`: LLM generates a summary of conversation history when approaching context limit
  - `truncate`: Keep first/last 20% of messages, drop middle
  - `none`: No management
- Token counting via `litellm.token_counter()` with fallback to character estimation
- Configurable `context_budget_fraction` (default 0.80)

Reference: `src/codeact_context/agent.py` lines 36-97 (truncation/summarization), `src/context_management/kernel_state_budget.py`.

**Key insight:** Harmonia has more sophisticated context management for the single-conversation paradigm. SRAgent's multi-agent design naturally segments context -- each specialist sees only its portion of the data. The kernel state budget is a unique Harmonia innovation addressing the specific challenge of Python kernel variables accumulating during a long interactive session.

### 2.5 Tool Integration Model

**SRAgent** tools are **LangChain `@tool`-decorated Python functions** that wrap external APIs:
- Each tool is a pure function: takes parameters, calls API, returns string
- Tools return error strings rather than raising exceptions (LLM interprets errors)
- Agents-as-tools pattern: sub-agents are wrapped as tools via `@tool` decorator
- 12+ deterministic tools covering Entrez, BigQuery, NCBI scraping, ontology lookup, paper download

**Harmonia** tools operate through a **Beaker kernel execution layer**:
- 5 BDI-Kit tools (`match_schema`, `rank_schema_matches`, `match_values`, `materialize_mapping`, `get_gdc_acceptable_values`)
- Each tool builds Python code via `agent.context.get_code()`, then executes it via `agent.context.evaluate()`
- In CodeAct mode, the LLM writes Python directly; the loop extracts and executes code blocks
- Tool results pass through the Beaker kernel, meaning the LLM sees output as Jupyter-style execution results

Reference: `src/bdikit_context/agent.py:BDIKitAgent` (5 tool definitions), `src/codeact_context/agent.py:CodeActAgentLoop.run()` lines 253-338.

**Key insight:** SRAgent's tools are tightly controlled -- the LLM can only call predefined functions with typed parameters. Harmonia's CodeAct mode gives the LLM far more freedom (arbitrary Python execution), which is powerful but harder to constrain. The BDI-Kit tool mode provides a middle ground with 5 structured tools.

### 2.6 Error Handling and Recovery

**SRAgent** has layered error handling:
- **API level**: Exponential backoff for NCBI rate limits (`tools/esearch.py` lines 173-183)
- **LLM level**: `FlexTierChatOpenAI` auto-fallback from flex to standard tier on timeout (`agents/utils.py` lines 37-84)
- **Structured output level**: Retry up to 3 times on `OpenAIRefusalError` with progressively softer prompts; fallback to defaults (`workflows/metadata.py` lines 286-321)
- **Data source level**: Multi-source paper download cascade with accumulated error messages (`tools/papers.py` lines 311-442)
- **Workflow level**: Convert graph has a 2-attempt hard limit before forced exit

**Harmonia** has error handling concentrated in the automation layer:
- **Provider level**: `retry_policy` in YAML config with per-error-code budgets (`openrouter_500: 3`, `timeout: 2`)
- **Classification**: `_classify_retryable_error()` in `runner.py` lines 427-440 pattern-matches on response content for OpenRouter errors, AIMessage validation errors
- **OpenRouter hardening**: `src/openrouter_hardening.py` monkey-patches the Archytas OpenRouter client
- **Agent level**: Archytas `max_react_steps` (default 30), `max_errors` (default 3), `max_consecutive_tool_errors` (default 3) -- configured via YAML -> env vars
- **No structured output retry**: Harmonia relies on the agent to self-correct within the conversation

Reference: `src/automation/runner.py` lines 413-469 (retry logic), `src/bdikit_context/context.py` lines 46-64 (Archytas limits).

**Key insight:** SRAgent's error handling is more granular because it controls every API call directly. Harmonia's error handling is more coarse-grained -- it can retry entire turns but cannot intervene mid-agent-loop. The retry_policy YAML configuration is more operator-friendly than SRAgent's hardcoded retry logic.

### 2.7 Configuration and Extensibility

**SRAgent** uses **Dynaconf** with a single `settings.yml`:
- 3 environments (test, prod, claude) switchable via `DYNACONF` env var
- 20 named agent slots with model, temperature, reasoning_effort, service_tier
- Adding a new agent requires: new Python file, new slot in settings.yml, wire into workflow

**Harmonia** uses **per-experiment YAML configs** with a rich generation/management pipeline:
- Each experiment has its own complete config with LLM, messages, evaluation, prompts, retry policy, tracing, model metadata
- `manage_configs.py` provides list/get/set/clone/validate operations
- `generate_env.py` converts YAML to `.env` for container injection
- `generate_jobs.py` creates SLURM batch scripts from configs
- Model registries (`LLM_associated_metadata/`) provide pricing and capability metadata
- Adding a new experiment requires: new YAML config (can be cloned from existing)

Reference: `manage_configs.py`, `generate_env.py`, `generate_jobs.py`, `src/automation/config.py:ExperimentConfig` (12+ nested dataclasses).

**Key insight:** Harmonia's configuration system is far more experiment-oriented, designed for running the same workflow across many LLMs and comparing results. SRAgent's configuration is more developer-oriented, designed for tuning individual agent behavior. Harmonia's approach is better suited to systematic evaluation; SRAgent's is better suited to operational deployment.

### 2.8 Code Modularity and Separation of Concerns

**SRAgent** has a **clean 4-layer architecture** with strict dependency direction:
- `cli/` -> `agents/` -> `tools/` -> `db/`
- Parallel naming: `agents/esearch.py` wraps `tools/esearch.py`
- Workflows compose agents without bypassing layers
- Minor violations: `workflows/metadata.py` imports `set_model` directly

**Harmonia** has a **mixed modular/monolithic structure**:
- `automation/` is cleanly separated (client, runner, config, logger, tracing)
- `bdikit_context/`, `code_context/`, `codeact_context/` are parallel implementations of the same interface (Beaker context)
- `evaluation/` is fully independent with its own Pydantic schemas
- `dashboard/` is a standalone Plotly Dash app
- The launch script (`exec_apptainer_harmonia.sh`) is a 300+ line bash script that bridges all components
- Cross-cutting concerns (prompt logging, openrouter hardening) sit at `src/` top level

**Key insight:** SRAgent has better internal code organization (consistent naming, clear layers). Harmonia has better modular boundaries at the system level (automation, evaluation, and dashboard are fully decoupled). Harmonia's architecture reflects an experimentation platform; SRAgent's reflects a production tool.

### 2.9 Testing and Evaluation Approach

**SRAgent**:
- pytest with test structure mirroring source (`tests/agents/`, `tests/tools/`, `tests/workflows/`)
- CLI smoke tests via `--help` subprocess calls
- Tool unit tests for deterministic helpers
- No LLM mocking or integration tests
- CI via GitHub Actions (Python 3.11/3.12)
- Evaluation via `scripts/` directory utilities and database queries

**Harmonia**:
- 46 tests focused on config loading, metrics calculation, ollama launcher
- No tests for agent behavior, WebSocket communication, or prompt rendering
- `pre-commit-config.yaml` with ruff, shellcheck, yamllint
- Comprehensive evaluation pipeline: `evaluation/metrics.py:calculate_all_metrics()` produces structured `MetricsResult` with column mapping metrics, per-column value metrics, error categorization, confusion matrices
- Visualization pipeline: 8+ plot types via seaborn and plotly backends
- Dashboard for cross-experiment comparison
- Log/trace analysis CLI with 16-class failure taxonomy

Reference: `src/evaluation/metrics.py`, `src/evaluation/schemas.py`, `code_development_tools_agents/monitoring_and_evaluation/`.

**Key insight:** SRAgent has broader unit test coverage across its tool layer. Harmonia has a dramatically more sophisticated evaluation and analysis pipeline -- the metrics schema, dashboard, and failure taxonomy represent significant investment in understanding experiment outcomes. For a research project comparing LLM performance, Harmonia's approach is far more valuable.

### 2.10 Documentation Quality and Developer Experience

**SRAgent**:
- README.md with usage examples
- AGENTS.md with project guidelines
- Module-level docstrings on most public functions
- `Annotated[type, description]` on all tool parameters
- `--write-graph` CLI flag for visual graph export
- No versioned codebase documentation
- No architecture decision records

**Harmonia**:
- 15+ versioned codebase descriptions in `docs/codebase_descriptions/` (updated with each significant change)
- Process documentation in `docs/processes/`
- Failure mode reference documentation
- CLAUDE.md project instructions (detailed operational playbook)
- Comprehensive inline comments explaining design decisions
- Dashboard provides visual experiment exploration
- `manage_configs.py` reduces operational friction

**Key insight:** Harmonia's documentation strategy is exceptional for a research project -- the versioned codebase descriptions create a living record of architectural evolution. SRAgent's documentation is more typical of an open-source tool (README + docstrings). For onboarding a new team member or understanding design rationale, Harmonia is significantly better documented.

---

## 3. Architecture Diagrams (Textual)

### SRAgent Execution Flow
```
CLI -> argparse -> asyncio.run()
  -> LangGraph StateGraph
    -> Supervisor ReAct Agent (LLM decides which specialist to call)
      -> Specialist Agent 1 (wraps Tool A, Tool B)
      -> Specialist Agent 2 (wraps Tool C)
      -> ...
    -> Structured Output Extraction (LLM + Pydantic model)
    -> [Optional] Database upsert
  -> Rich console output
```

### Harmonia Execution Flow
```
SLURM job -> exec_apptainer_harmonia.sh
  -> Apptainer container
    -> Beaker server (Jupyter protocol)
      -> Context (bdikit/code/codeact) + single ReAct agent
      -> Python subkernel (BDI-Kit, pandas, etc.)
  -> run_experiment.py (outside container)
    -> BeakerClient (WebSocket)
      -> Sends scripted messages
      -> Captures responses (trace.json, conversation.md)
      -> Handles decision points, retries
  -> calculate_metrics.py (post-experiment)
    -> MetricsResult (metrics.json)
  -> Dashboard (cross-experiment analysis)
```

---

## Completeness Assessment

This comparison covers all 10 requested axes with specific file and line references from both codebases. The analysis draws on:
- All 6 SRAgent Phase 1 analysis documents
- The latest Harmonia codebase description (13-03-2026)
- Direct reading of 20+ Harmonia source files (`automation/`, `bdikit_context/`, `codeact_context/`, `evaluation/`, `dashboard/`)
- Sample experiment configs and launch scripts

Areas not deeply compared: database layer (SRAgent has PostgreSQL; Harmonia stores results as files), deployment infrastructure (SRAgent uses Cloud Run; Harmonia uses SLURM + Apptainer), and CI/CD (SRAgent has GitHub Actions; Harmonia relies on pre-commit hooks). These differences are primarily infrastructure choices rather than architectural patterns.
