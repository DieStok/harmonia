# Harmonia Codebase Reference

**Date:** 12-03-2026 | **Python:** 3.11 via `.venv/` (never conda/system)

---

## What This Project Does

Runs **metadata harmonization agents** using LLMs + Beaker to harmonize biomedical metadata tables to GDC (Genomic Data Commons) standard. Measures and compares agent performance across different LLMs.

**Before starting work:** Read latest instructions from `my_instructions/` (most recent by date) and ask if anything changed.

---

## Directory Structure

```
harmonia/
├── src/
│   ├── automation/              # Experiment automation framework
│   │   ├── client.py            # BeakerClient — WebSocket client for Beaker kernel
│   │   ├── runner.py            # ExperimentRunner — automated experiment orchestration
│   │   ├── manual_runner.py     # ManualExperimentRunner — passive monitor for interactive sessions
│   │   ├── config.py            # ExperimentConfig and all config dataclasses
│   │   ├── logger.py            # TraceLogger (→trace.json), ConversationLogger (→conversation.md)
│   │   ├── tracing.py           # Phoenix/OTel tracing — span creation, token extraction, cost calc
│   │   └── ollama_launcher.py   # VRAM estimation + dynamic port calculation
│   │
│   ├── evaluation/              # Metrics pipeline
│   │   ├── schemas.py           # Pydantic models for metrics.json (v1.1)
│   │   ├── metrics.py           # Core: calculate_all_metrics()
│   │   ├── make_standard_evaluation_plots.py  # Generate all standard plots
│   │   └── visualization/       # io.py, enrich.py, normalize.py, aggregate.py, plots.py, report.py
│   │
│   ├── dashboard/               # Plotly Dash web dashboard
│   │   ├── app.py               # Main entry point + all callbacks
│   │   ├── activity_logger.py   # DashboardActivityLogger — JSON-lines interaction logging
│   │   ├── data_loader.py       # DashboardDataLoader — dual-source (files + Phoenix)
│   │   ├── tabs/                # overview, metrics, failure_analysis, error_analysis,
│   │   │                        #   trace_explorer, token_cost, comparison, activity_log
│   │   └── components/          # run_table, span_waterfall, turn_accordion, diff_card, multi_filter
│   │
│   ├── bdikit_context/          # BDI-Kit Beaker context (ReAct + domain tools)
│   │   ├── context.py           # BDIKitContext — reads HARMONIA_* env vars for prompt overrides
│   │   ├── agent.py             # BDIKitAgent — 5 tools: match_schema, rank_schema_matches,
│   │   │                        #   match_values, materialize_mapping, get_gdc_acceptable_values
│   │   ├── config/              # ContainerLLMConfig, HarmoniaConfig
│   │   ├── llm/                 # litellm_model.py (ChatLiteLLM, LiteLLMModel),
│   │   │                        #   provider_prefixes.py (15-entry prefix mapping)
│   │   └── prompts/             # Jinja2 templates for system prompt + tool descriptions
│   │
│   ├── code_context/            # Minimal context (ReAct + run_code tool only)
│   │
│   ├── codeact_context/         # True CodeAct (bypasses Archytas — LLM writes Python in markdown)
│   │   ├── context.py           # CodeActContext — builds litellm model, manages loop
│   │   └── agent.py             # CodeActAgent + CodeActAgentLoop (extract code → execute → loop)
│   │
│   ├── context_management/      # Kernel state budget enforcement (FETCH_STATE_CODE patch)
│   └── prompt_logging.py        # Prompt composition capture (stdout + JSON)
│
├── experiments/.../configs/
│   ├── automated/               # YAML configs for scripted experiments
│   ├── manual/                  # YAML configs for interactive experiments
│   └── prompts/                 # Versioned prompt variants (system, ReAct, CodeAct, tool)
│
├── scripts/
│   ├── dashboard.sh             # Dashboard start/stop/status (screen or SLURM)
│   └── ensure_phoenix_server.py # Singleton Phoenix server lifecycle management
│
├── code_development_tools_agents/monitoring_and_evaluation/
│   ├── read_and_analyze_logs_and_traces_cli.py  # Log/trace failure analysis (16-class taxonomy)
│   └── types_of_log_and_trace_problems.yaml     # Machine-readable error taxonomy
│
├── LLM_associated_metadata/     # Model registries (OpenRouter + Ollama) + lookup tools
├── tests/                       # 46 tests: config loading, metrics, ollama launcher
│
├── run_experiment.py            # CLI: automated experiments
├── run_manual_experiment.py     # CLI: manual experiment logging
├── calculate_metrics.py         # CLI: standalone metrics calculation
├── generate_jobs.py             # Generate SLURM job scripts
├── generate_env.py              # Generate .env from YAML configs
├── manage_configs.py            # List/get/set/clone/validate configs
│
├── exec_apptainer_harmonia.sh   # Launch Beaker in Apptainer (auto-detects image, per-job Ollama)
├── harmonia_beaker_LLM_agent_environment_apptainer.sif  # Current Apptainer image
├── results/                     # Experiment output (gitignored)
├── logs/                        # SLURM logs (gitignored)
└── .pre-commit-config.yaml      # ruff, shellcheck, yamllint
```

---

## Three Context Paradigms

| Paradigm | Context | Agent loop | LLM action format |
|----------|---------|------------|-------------------|
| ReAct + domain tools | `bdikit_context` | Archytas `ReActAgent` | Structured JSON tool calls |
| ReAct + run_code only | `code_context` | Archytas `ReActAgent` | Structured JSON tool calls |
| True CodeAct | `codeact_context` | Custom `CodeActAgentLoop` | Python in markdown fences |

Set via `context:` in experiment YAML. All three are registered as Beaker entry points in `pyproject.toml`.

---

## Running Experiments

### Automated

```bash
# Single command
srun -J harmonia --account=compgen --time=02:00:00 --mem=20G bash -c '
  cd .../datasets_harmonia/one_metadata_table_gdc_schema/data
  .../exec_apptainer_harmonia.sh --config .../configs/automated/some_config.yaml &
  BEAKER_PID=$!; sleep 10
  .venv/bin/python run_experiment.py --config .../configs/automated/some_config.yaml
  kill $BEAKER_PID
'
```

### Manual (interactive) — ALWAYS use --monitor

```bash
srun --time=04:00:00 --mem=20G \
    ./exec_apptainer_harmonia.sh --config configs/manual/some_config.yaml --monitor
# Then: ssh -L 8100:localhost:8100 <node>; open http://localhost:8100
```

### Local LLMs → ALWAYS use GPU partition

```bash
srun --partition=gpu --gpus-per-node=1 --time=04:00:00 --mem=64G --cpus-per-task=8 \
    ./exec_apptainer_harmonia.sh --config some_config.yaml --monitor
```

---

## Run ID System

Every run gets an 8-char hex ID (`secrets.token_hex(4)`). It appears in:

- Results dir: `results/{name}_{timestamp}_{run_id}/` or `results/{name}_{slurm_job_id}_{run_id}/`
- Log files: `logs/{date}_{name}_{jobid}_{run_id}.out/.err`
- `trace.json` top-level `run_id` field
- Phoenix spans: `harmonia.run_id` attribute
- `.experiment_id` JSON metadata file in results dir

When a run_id maps to multiple directories (both formats coexist), prefer the SLURM-job-ID format as canonical.

---

## Key Data Formats

### trace.json

Top-level: `run_id`, `experiment` (name, description), `llm` (provider, model), `timing` (start_time, end_time, total_duration_seconds), `status`, `error_message`, `config_snapshot`, `turns[]`.

Each turn: `turn`, `user_message`, `agent_response`, `response_type`, `tool_calls`, `duration_seconds`, `raw_messages`, `timestamp`, `input_tokens`, `output_tokens`, `cost_usd`, `code_executions`, `usage_records`.

### metrics.json (schema v1.1)
Top-level: `schema_version`, `metadata` (ExperimentMetadata), `column_mapping` (ColumnMappingMetrics), `column_values` (dict → ColumnValueMetrics), `extra_columns_count`, `extra_columns`, `overall_summary` (OverallSummary), `gold_standard_file`, `llm_output_file`.

- `metadata`: experiment_name, timestamp, llm_provider, llm_model, timing_seconds, pricing_*, parameter_count_b, model_family_group, supports_tools.
- `overall_summary`: avg_accuracy/precision/recall/f1 (incl/excl empty), total_hallucinations/omissions, error categorization.
- `column_mapping`: total_expected, correct, wrong, missing, explicitly_null, precision (incl/excl null), recall, accuracy, details[].
- Per-column `column_values`: accuracy/precision/recall/f1 (incl/excl empty), hallucination/omission counts+rates, error_categorization, confusion_matrix, misclassifications, row_comparisons.

### Results directory contents
```
trace.json, conversation.md, config_snapshot.yaml, .experiment_id,
harmonized_table.csv (if successful), metrics.json (if evaluation configured),
row_values.csv (per-row comparison data), full_prompt_composition.json
```

---

## Phoenix/OTel Tracing

Opt-in via `tracing:` section in experiment YAML. Gracefully degrades if Phoenix unreachable.

**Span hierarchy (OpenInference conventions):**

- Root `AGENT` span `experiment:{name}`: `harmonia.run_id`, `harmonia.trace_type`, `llm.model_name`, `harmonia.config_snapshot`
- `CHAIN` span `turn:{N}`: `harmonia.turn_number`, `input.value`
- `LLM` span `llm_call:{N}`: `llm.token_count.prompt/completion/total`, `harmonia.cost_usd`
- `TOOL` span `beaker_execute`: `tool.name`, `input.value`

**Important:** Always use `SpanAttributes.*` constants from `openinference.semconv.trace`, not hardcoded strings.

Phoenix server managed by `scripts/ensure_phoenix_server.py` (called automatically by `exec_apptainer_harmonia.sh`).

---

## Dashboard (`src/dashboard/`)

Plotly Dash web app combining Phoenix traces, metrics.json, and trace.json.

**Launch:**
```bash
./scripts/dashboard.sh start          # submit node (screen session)
./scripts/dashboard.sh start --slurm  # SLURM job
# Access: ssh -L 8050:localhost:8050 <node>; open http://localhost:8050
```

**Direct:**
```bash
.venv/bin/python src/dashboard/app.py --phoenix-endpoint http://localhost:6006 --results-dir results/ --port 8050
```

**8 tabs:** Overview (AG Grid runs table + summary cards + status pie), Metrics Comparison (accuracy bars, cost-vs-accuracy scatter, heatmap, radar, boxplots), Failure Analysis (success/failure heatmap, failure distribution, sunburst), Error Analysis (error breakdown, per-column errors), Trace Explorer (span waterfall, paginated turn accordion with full content + tool calls, token/cost charts, confusion matrices), Token & Cost Analysis, Side-by-Side Comparison, Activity Log (chronological interaction history with filters).

**Data loader:** `DashboardDataLoader` scans `results/` directories AND queries Phoenix. Outer-joins on `run_id`. Thread-safe. Degrades gracefully without Phoenix (shows local data only).

**Activity logging:** All user interactions (tab switches, run selections, chart clicks, refreshes, etc.) are logged as JSON-lines to `logs/dashboard/dashboard.log` with daily rotation. The Activity Log tab reads these files and displays a filterable table. Logger: `DashboardActivityLogger` in `activity_logger.py`.

---

## Experiment Configuration

YAML configs in `experiments/.../configs/automated/` and `.../manual/`.

Key sections: `experiment` (name, description, context), `llm` (provider, model, temperature, context_length), `messages[]` (content, wait_seconds, decision_mode), `output`, `prompts` (system_prompt_dir, react_prelude, codeact_prompt, tool_prompts_dir), `context_management` (python_kernel + archytas settings), `model_metadata` (pricing, capabilities), `tracing` (enabled, phoenix_endpoint), `data` (base_dir, files — controls per-file mount isolation).

**Config flow:** YAML → `generate_env.py` → `.env` → `exec_apptainer_harmonia.sh` binds dirs + exports env vars → context reads env vars inside container.

**Config management:** `manage_configs.py` (list, get, set, clone, validate). `clone` auto-enriches with `model_metadata` from registry.

---

## LLM Providers

100+ via litellm. Provider prefix mapping in `src/bdikit_context/llm/provider_prefixes.py`:
`ollama→ollama_chat/`, `openai→""`, `openrouter→openrouter/`, `anthropic→anthropic/`, etc.

Key env vars: `LLM_SERVICE_PROVIDER`, `LLM_SERVICE_MODEL`, `LLM_PROVIDER_IMPORT_PATH`, provider API keys.

**Ollama specifics:** Per-job isolation under SLURM (unique port, PID file, runtime dir). Context length via `context_length` in YAML → `OLLAMA_CONTEXT_LENGTH` env var. Default 4096 is too small — always set explicitly.

---

## Evaluation Pipeline

```bash
# Standalone
.venv/bin/python calculate_metrics.py --results-dir results/<dir> --gold-standard <path> --verbose

# Standard plots
.venv/bin/python src/evaluation/make_standard_evaluation_plots.py --metrics-glob "results/*/metrics.json" --out-dir analysis/plots
```

**Visualization CLI:** `visualize_metrics_cli.py` with subcommands: summarize, bars, heatmap, confusion, errors, compare, boxplot, cross-compare. Supports `--backend seaborn|plotly`.

---

## Log/Trace Analysis

```bash
.venv/bin/python code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py
# Flags: --run-id <id>, --experiment <name>, --verbose, --json, --diagnostics
```

16-class failure taxonomy across 5 categories: Infrastructure (hung server, 405, ZMQ), Model Config (not found, no tools, crash, unavailable, rate limit), LLM Behavioral (timeout, not using tools, hallucinated output, websocket size, context exhaustion, truncated, silent empty), Data/Config (file not found), Output (no output).

---

## Container Environment

**Current image:** `harmonia_beaker_LLM_agent_environment_apptainer.sif` (Python 3.11, litellm, bdi-kit 0.9.0). Built from local dev forks of beaker-kernel and archytas.

**Build:** `srun --time=02:30:00 --mem=50G --gres=tmpspace:100G bash` then `./build_harmonia_apptainer.sh`

**Bind mounts:** `workspace_mount/` → `/workspace` (writable cwd), per-file data mounts from config `data.files` → `/workspace/data/` (read-only overlay), results → `/workspace/results` (writable, experiment-specific), runtime → `/runtime` (Jupyter, Beaker, IPython, HF cache, .experiment_id). The workspace bind comes before data/results binds so Apptainer overlays the read-only data mount on top. Between runs, `workspace_mount/` is cleaned of stray files. A post-run diagnostic logs any files the LLM wrote outside `results/`.

**System prompts** (all three contexts: codeact, code, bdikit) include a "Workspace Layout" section instructing the LLM to save output to `results/` and warning that `data/` is read-only.

---

## Datasets

All in `harmonia_metadata_agent/raw/datasets_harmonia/`:

1. **one_metadata_table_gdc_schema/** — Dou 2020 endometrial carcinoma (17 cols, 190 rows). Primary benchmark.
2. **two_metadata_tables_harmonize/** — Dou 2020 + Dou 2023 (153 + 190 samples).
3. **ten_metadata_tables_harmonize/** — 10 CPTAC cancer studies with Li 2023 ground truth.

Gold standard: `raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/`

---

## Quality & Testing

- **Pre-commit:** ruff (lint+format), shellcheck, yamllint
- **Tests:** `tests/` — 46 tests (config loading, metrics, ollama launcher). Run: `.venv/bin/python -m pytest tests/ -v`
- **Ruff config:** `pyproject.toml` — Python 3.11, line-length 120, rules E/F/W/I

---

## Troubleshooting

| Error | Cause | Fix |
| ----- | ----- | --- |
| `No module named 'bdikit_context.llm.litellm_model'` | Legacy `jupyter.sif` image | Rebuild with `./build_harmonia_apptainer.sh` |
| "Agent says it doesn't have tools" | Context entry point not registered | Check `pyproject.toml` entry points, rebuild image |
| "Model does not support tools" | LLM lacks function calling | Use tool-capable model or switch to `codeact_context` |
| Connection errors | Beaker not running / wrong port / token | Check server output, verify port and token |
