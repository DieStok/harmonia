# Harmonia Strengths Relative to SRAgent

**Date:** 31-03-2026 | **Analyst:** Comparative Architecture Analysis

---

## Preface: Honest Framing

SRAgent is a more mature multi-agent system with cleaner internal code organization and a broader tool ecosystem. In a head-to-head comparison of agent orchestration sophistication, SRAgent wins clearly. However, Harmonia has genuine architectural strengths that reflect its different purpose: it is an **experimentation platform for comparing LLM performance on a fixed task**, not an operational tool for processing arbitrary inputs. Several of its design decisions are superior *for that purpose*.

---

## Strength 1: Experiment-First Configuration System

### What Harmonia Does

Harmonia's YAML configuration system (`src/automation/config.py`) is purpose-built for systematic LLM experimentation. A single YAML file completely specifies:
- Which LLM to use, at what temperature, with what context length
- The exact conversation script (messages, wait times, decision modes)
- How to evaluate results (gold standard paths, acceptable alternatives, error tolerance)
- Retry behavior per error code
- Model metadata (pricing, parameter count, capabilities)
- Tracing configuration
- Data file mounts

The `manage_configs.py` tool provides `clone` functionality that auto-enriches with model metadata from the registry, enabling rapid generation of 50+ experiment configs across different LLMs.

### What SRAgent Does Not

SRAgent's Dynaconf system configures **how the system behaves** (which model for which agent, what temperature) but has no concept of:
- A complete experiment specification
- Gold standard comparison
- Conversation scripting
- Cost tracking and model metadata
- Automated metrics calculation

SRAgent cannot natively answer "how does GPT-5-mini compare to Claude Sonnet on this dataset?" without building significant external infrastructure.

### Why This Matters

For a research project evaluating LLM capabilities, the ability to define, clone, execute, and compare experiments across 100+ model configurations is the core workflow. Harmonia's config system is the foundation that makes this possible.

**Key files:** `src/automation/config.py` (12+ nested dataclasses, 326 lines), `manage_configs.py`, `generate_env.py`, `generate_jobs.py`.

---

## Strength 2: Comprehensive Evaluation Pipeline

### What Harmonia Does

The `src/evaluation/` package provides a rigorous metrics framework:

1. **Schema-level metrics** (`metrics.py:calculate_column_mapping_metrics()`): Precision, recall, accuracy for column mapping with support for acceptable alternative mappings
2. **Value-level metrics** (per-column): Accuracy, precision, recall, F1 (both including and excluding empty cells), hallucination rate, omission rate, confusion matrices
3. **Error categorization** (`schemas.py:ErrorCategorization`): Distinguishes whitespace-only, case-only, whitespace+case, and genuine errors -- critical for understanding whether LLM errors are trivial formatting issues or real semantic mistakes
4. **Structured output** (`schemas.py:MetricsResult`): Pydantic v2 schema (v1.1) with `model_dump_json()` for machine-readable metrics
5. **Visualization pipeline**: `make_standard_evaluation_plots.py` plus `visualize_metrics_cli.py` with 8 subcommands (summarize, bars, heatmap, confusion, errors, compare, boxplot, cross-compare) supporting both seaborn and plotly backends
6. **Cross-experiment comparison**: Aggregation across multiple metrics.json files for multi-model comparison

### What SRAgent Does Not

SRAgent stores results in PostgreSQL and has `scripts/` for evaluation, but:
- No standardized metrics schema
- No per-column value-level metrics
- No error categorization (whitespace vs case vs genuine)
- No hallucination/omission tracking
- No cross-experiment comparison framework
- No visualization pipeline

### Why This Matters

The error categorization alone is a significant contribution. Knowing that 60% of "errors" are just case mismatches (agent outputs "male" instead of "Male") versus 40% genuine semantic errors fundamentally changes how you interpret LLM performance and design prompts.

**Key files:** `src/evaluation/schemas.py` (Pydantic models), `src/evaluation/metrics.py` (core calculation), `src/evaluation/visualization/` (6 modules), `src/evaluation/make_standard_evaluation_plots.py`.

---

## Strength 3: Three-Paradigm Agent Architecture

### What Harmonia Does

Harmonia supports three distinct agent paradigms, registered as Beaker entry points (`pyproject.toml`):

| Paradigm | Context | Agent Loop | LLM Action Format |
|----------|---------|------------|-------------------|
| ReAct + domain tools | `bdikit_context` | Archytas `ReActAgent` | Structured JSON tool calls |
| ReAct + run_code only | `code_context` | Archytas `ReActAgent` | Structured JSON tool calls |
| True CodeAct | `codeact_context` | Custom `CodeActAgentLoop` | Python in markdown fences |

Switching between paradigms requires only changing `context: bdikit_context` to `context: codeact_context` in the YAML config. This enables controlled experiments comparing structured tool use vs free-form code generation.

### What SRAgent Does Not

SRAgent has exactly one paradigm: LangGraph ReAct agents with `@tool`-decorated functions. There is no way to test whether an LLM performs better when given structured tools vs the ability to write arbitrary code, because the tool interface is hardcoded.

### Why This Matters

The CodeAct paradigm (`src/codeact_context/agent.py:CodeActAgentLoop`) is architecturally interesting: it bypasses Archytas entirely, calling `litellm.acompletion()` directly, extracting code blocks via regex, and executing them through the Beaker kernel. This gives the LLM maximum flexibility but requires more sophisticated context management (the summarize/truncate strategies at lines 36-97). Being able to compare ReAct-with-tools vs CodeAct on the same benchmark is a genuine research capability.

**Key files:** `src/bdikit_context/` (ReAct + domain tools), `src/code_context/` (ReAct + code), `src/codeact_context/` (CodeAct).

---

## Strength 4: Prompt Version Control and Override System

### What Harmonia Does

Prompt management in Harmonia is designed for systematic experimentation:

1. **Jinja2 templates** (`src/bdikit_context/prompts/`): System prompts and tool descriptions are templates, not hardcoded strings
2. **Per-experiment prompt overrides** via environment variables:
   - `HARMONIA_PROMPTS_DIR`: Custom system prompt directory
   - `HARMONIA_REACT_PRELUDE`: Custom ReAct agent prelude file
   - `HARMONIA_TOOL_PROMPTS_DIR`: Custom tool description templates
3. **Versioned prompt variants** stored in `experiments/.../configs/prompts/` (separate directories for system prompts, ReAct preludes, CodeAct prompts, tool prompts)
4. **Prompt composition logging**: `src/prompt_logging.py` captures the full assembled prompt (system + ReAct prelude + tool descriptions) as JSON for reproducibility
5. **Tool description override**: `BDIKitContext._override_tool_descriptions()` (context.py lines 81-110) replaces Archytas tool descriptions with rendered Jinja2 templates at runtime

### What SRAgent Does Not

SRAgent's prompts are hardcoded Python strings in agent files (`agents/entrez.py` lines 41-83, etc.). To test a different prompt:
- You must modify Python source code
- There is no mechanism to version or A/B test prompts
- Prompt composition is not logged or captured for reproducibility
- Tool descriptions come from `@tool` docstrings and cannot be overridden without code changes

### Why This Matters

Prompt engineering is the primary tuning mechanism for LLM agent performance. Being able to swap prompt variants without code changes, and having the full prompt composition captured in `full_prompt_composition.json` alongside each experiment's trace, enables reproducible prompt experimentation at scale.

**Key files:** `src/bdikit_context/prompts/__init__.py:PromptLoader`, `src/bdikit_context/context.py` lines 36-78 (override logic), `src/prompt_logging.py`.

---

## Strength 5: Observability Stack (Tracing + Dashboard + Failure Taxonomy)

### What Harmonia Does

Harmonia has a multi-layered observability stack:

1. **Trace logging** (`src/automation/logger.py`): Every experiment produces `trace.json` with per-turn records including: user message, agent response, response type, tool calls, duration, raw WebSocket messages, input/output tokens, cost in USD, code executions (agent vs internal), and usage records
2. **Phoenix/OTel tracing** (`src/automation/tracing.py`): OpenTelemetry spans exported to Phoenix server with OpenInference conventions -- root AGENT span, per-turn CHAIN spans, per-LLM-call LLM spans, per-execution TOOL spans. Attributes include `harmonia.run_id`, `harmonia.cost_usd`, token counts
3. **Interactive dashboard** (`src/dashboard/`): 8-tab Plotly Dash application with AG Grid runs table, accuracy bars, cost-vs-accuracy scatter plots, failure heatmaps, span waterfall diagrams, confusion matrices, side-by-side comparison, activity logging
4. **Failure taxonomy** (`code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml`): 16-class machine-readable taxonomy across 5 categories (Infrastructure, Model Config, LLM Behavioral, Data/Config, Output)
5. **Log analysis CLI** (`read_and_analyze_logs_and_traces_cli.py`): Automated analysis of SLURM logs and trace.json files against the failure taxonomy
6. **Cost tracking**: Per-turn and per-experiment cost in USD, using model metadata from the registry

### What SRAgent Does Not

SRAgent has:
- Rich console output with step summaries (real-time, but not persisted)
- Database storage of results
- No per-turn tracing or cost tracking
- No dashboard
- No failure taxonomy
- No post-hoc log analysis

### Why This Matters

The run ID system (8-char hex linking logs, results, and traces) combined with the dashboard and failure taxonomy enables diagnosis at scale. When running 200+ experiments, finding which runs failed and why is the bottleneck -- Harmonia's observability stack directly addresses this.

**Key files:** `src/automation/logger.py`, `src/automation/tracing.py`, `src/dashboard/app.py` (+ 8 tab modules, 5 component modules), `code_development_tools_agents/monitoring_and_evaluation/`.

---

## Strength 6: Container-Based Reproducible Execution

### What Harmonia Does

Harmonia uses Apptainer (Singularity) containers with carefully designed bind mounts:
- `workspace_mount/` -> `/workspace` (writable, cleaned between runs)
- Per-file data mounts from config `data.files` -> `/workspace/data/` (read-only overlay)
- Results -> `/workspace/results` (writable, experiment-specific)
- Runtime -> `/runtime` (Jupyter, Beaker, IPython, HF cache, `.experiment_id`)
- Per-job Ollama isolation (dynamic port, PID file, runtime directory based on SLURM job ID)

The `exec_apptainer_harmonia.sh` script (300+ lines) handles:
- Image auto-detection (finds most recent `.sif`)
- Environment generation from YAML config
- Ollama startup for local LLMs
- Phoenix server management
- Run ID generation and propagation
- Workspace cleanup between runs
- Post-run diagnostic (logs files written outside `results/`)

### What SRAgent Does Not

SRAgent is designed for direct execution (pip install + run). There is:
- No container definition
- No workspace isolation (tools write to arbitrary filesystem locations)
- No per-experiment data isolation
- No Ollama management for local LLMs

### Why This Matters

Container-based execution ensures that experiments are reproducible: the same image, same data mounts, same environment variables produce the same results (modulo LLM nondeterminism). The workspace isolation prevents experiments from contaminating each other, which is essential when running hundreds of experiments on shared HPC infrastructure.

**Key files:** `exec_apptainer_harmonia.sh`, `harmonia_beaker_LLM_agent_environment_apptainer.def`, `build_harmonia_apptainer.sh`.

---

## Strength 7: Kernel State Budget Management

### What Harmonia Does

The `src/context_management/kernel_state_budget.py` module patches Beaker's `FETCH_STATE_CODE` to control how much Python kernel state is serialized into the LLM context. Configuration includes:
- `max_variable_size`: Maximum characters per variable (default 20,000)
- `state_budget_pct`: Percentage of context window allocated to kernel state (default 25%)
- `type_blacklist`: Python types never serialized (e.g., `SchemaGraph`, `SimilarityFloodingMatcher` -- BDI-Kit internals that would consume the entire context window)
- `var_whitelist`: Variables always included (e.g., `df`, `df_harmonized`, `mapping`)

### What SRAgent Does Not

SRAgent's agents have no concept of kernel state -- they receive structured inputs and produce structured outputs. There is no stateful Python environment accumulating variables across turns.

### Why This Matters

In a long interactive session, the Python kernel accumulates variables (dataframes, mapping specs, intermediate results). Without budget management, Beaker serializes *all* kernel state into the LLM context, quickly exhausting the context window. The type blacklist is particularly important: BDI-Kit's `SimilarityFloodingMatcher` object can serialize to 100K+ characters, which would consume the entire context of smaller models.

This is a unique challenge that arises specifically from the Beaker/Jupyter architecture, and Harmonia's solution is thoughtful and well-configured for the domain.

**Key files:** `src/context_management/kernel_state_budget.py`, `src/automation/config.py:PythonKernelContextConfig` (lines 82-94).

---

## Strength 8: Versioned Codebase Documentation

### What Harmonia Does

The `docs/codebase_descriptions/` directory contains 15 dated versions of a comprehensive codebase reference document (format: `how_this_codebase_works_DD_MM_YYYY.md`). Each document is a complete snapshot of the system architecture, updated after significant changes. The CLAUDE.md project instructions mandate checking the latest version before work and updating it after changes.

### What SRAgent Does Not

SRAgent has a static README.md and AGENTS.md. There is no versioned architectural documentation.

### Why This Matters

For a research project with a single primary developer working with AI assistants, this documentation strategy creates:
- An architectural decision record (comparing versions reveals what changed and when)
- Reliable context for AI assistants (the latest doc is always current)
- Onboarding material (new contributors read the latest doc)
- A form of "institutional memory" that survives between development sessions

---

## Patterns Worth Preserving in Any Architectural Evolution

If Harmonia adopts SRAgent-style patterns (multi-agent, LangGraph workflows), the following Harmonia-specific designs should be preserved:

1. **Per-experiment YAML configs with clone/enrich** -- Do not replace with SRAgent-style settings.yml
2. **Evaluation pipeline with error categorization** -- This is more sophisticated than anything in SRAgent
3. **Three agent paradigms** -- The ability to compare ReAct vs CodeAct is a research asset
4. **Jinja2 prompt templates with per-experiment overrides** -- Far superior to hardcoded strings
5. **Run ID system linking traces/logs/results** -- Essential for experiment tracking at scale
6. **Container-based execution with workspace isolation** -- Non-negotiable for HPC reproducibility
7. **Kernel state budget management** -- Necessary if keeping the Beaker/Jupyter architecture
8. **Failure taxonomy and log analysis CLI** -- Irreplaceable for diagnosing experiment failures at scale

---

## Honest Assessment of Relative Weakness

While the above strengths are real, it is important to acknowledge:

- **Harmonia's agent is simple by design**: A single flat agent with 5 tools. SRAgent's 15-agent hierarchy with 4-level nesting is architecturally more sophisticated. If Harmonia's harmonization task grows in complexity (multiple schemas, multi-step ontology resolution, cross-referencing external databases), the single-agent model will strain.
- **Harmonia has no workflow state machine**: The "workflow" is an implicit sequence of scripted messages in YAML. There is no conditional branching, no loops, no parallel processing within an experiment. SRAgent's LangGraph workflows are structurally more expressive.
- **Harmonia's error handling is coarser**: It can retry entire turns but cannot intervene mid-agent-loop. SRAgent's structured output retry with progressive prompt softening is more nuanced.
- **Harmonia's code duplication is modest but present**: The three context packages (`bdikit_context/`, `code_context/`, `codeact_context/`) share structural patterns but have no shared base class or factory, unlike SRAgent's consistent `create_<name>_agent()` pattern.
- **Harmonia has fewer unit tests proportional to its codebase**: 46 tests across 60+ source files, with no tests for the agent, client, runner, dashboard, or prompt loading.

---

## Completeness Assessment

This document identifies 8 genuine Harmonia strengths with specific file references and line numbers. Each strength is compared directly to SRAgent's equivalent (or lack thereof) with an explanation of why it matters for Harmonia's specific use case. The honest assessment section identifies 5 areas where SRAgent is objectively stronger. The "patterns worth preserving" section provides actionable guidance for future architectural decisions.

Strengths not analyzed in depth: the `LLM_associated_metadata/` registry system (OpenRouter + Ollama model fetching, pricing data, capability flags) which has no SRAgent equivalent, and the `scripts/ensure_phoenix_server.py` singleton server management pattern. Both are useful but less architecturally significant than the 8 strengths above.
