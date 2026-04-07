# Harmonia Project Instructions

## Before Starting Any Task

1. **Read latest instructions**: `my_instructions/` (most recent by date)
2. **Ask user** if instructions are still current or if anything has changed
3. **Check datasets**: `../../raw/datasets_harmonia/` for experiment data

## After Code Changes

Always look at `docs/codebase_descriptions/`; find the latest .md file, see if what you have just implemented necessitates changes to this description. If so: generate the diffs needed to this file. Then, if the file has the correct date (check with `date +%d_%m_%Y`) edit that file. Otherwise, generate a new one with the same file name convention and correct date.

## After Experiment Runs (Log Auditing)

Use the log/trace analysis CLI tool to audit experiment results:

```bash
.venv/bin/python code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py
```

This detects 13 categories of failure modes (infrastructure hangs, model not found, API errors, LLM behavioral issues, missing output, etc.) by analyzing both SLURM logs and trace.json files. Use `--verbose` for per-turn analysis, `--json` for machine-readable output, or `--run-id <id>` / `--experiment <name>` to filter.

The error taxonomy is defined in `code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml`. The human-readable failure mode reference is in `docs/processes/11_02_2026_interpreting_logs_and_traces.md`.

## Project Overview

**Goal:** Run metadata harmonization agents using LLMs + Beaker to evaluate performance on biomedical data harmonization tasks.

**Full documentation:** `docs/codebase_descriptions/` (read the latest by date)

## Key Paths

| Resource | Path |
|----------|------|
| Source code | `src/` |
| Experiment configs | `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/` |
| Datasets | `../../raw/datasets_harmonia/` |
| Gold standard | `../../raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/` |
| Results | `results/` |
| Logs | `logs/` |
| Evaluation code | `src/evaluation/` |
| Log analysis tool | `code_development_tools_agents/monitoring_and_evaluation/` |
| Failure mode docs | `docs/processes/` |
| Apptainer image | `harmonia_beaker_LLM_agent_environment_apptainer.sif` |
| Python venv | `.venv/` |
| Model registries | `LLM_associated_metadata/` |

## Current State

- **Working:** Automated experiments with multiple LLM backends, manual interactive experiments
- **Working:** Metrics evaluation pipeline (`src/evaluation/`) comparing harmonized output to gold standard
- **Working:** Log/trace analysis CLI tool for diagnosing experiment failures
- **Working:** Per-job Ollama isolation (dynamic ports, per-job PID/runtime dirs)
- **Working:** Uniform experiment tracking via 8-char hex run IDs linking logs to results

## Experiment Types

1. **Automated:** Scripted interactions in `configs/automated/*.yaml` - same script runs for each LLM
2. **Manual:** Interactive Beaker notebook via port forwarding (configure LLM in `.env`)

## Running Experiments

### Manual interactive experiments (ALWAYS use --monitor)

When the user asks to start a manual/interactive experiment, **always use `--monitor`** so that
`conversation.md` and `trace.json` are produced. Without `--monitor`, Beaker runs but nothing
is logged.

```bash
# Cloud LLM providers
srun --time=04:00:00 --mem=10G \
    ./exec_apptainer_harmonia.sh --config <manual_config.yaml> --monitor

# Local LLM providers (ALWAYS use GPU partition!)
srun --partition=gpu --gpus-per-node=1 --time=04:00:00 --mem=64G --cpus-per-task=8 \
    ./exec_apptainer_harmonia.sh --config <manual_config.yaml> --monitor
```

The `--monitor` flag starts Beaker in the background and launches a WebSocket monitor
(`run_manual_experiment.py`) that passively captures all user/agent interactions into
`results/<experiment_name>_<timestamp>_<run_id>/trace.json` and `conversation.md`.

### Automated experiments

```bash
# Start Beaker server first (cloud)
./exec_apptainer_harmonia.sh --config <config.yaml>

# Start Beaker server first (local LLM — ALWAYS use GPU partition!)
srun --partition=gpu --gpus-per-node=1 --time=04:00:00 --mem=64G --cpus-per-task=8 \
    ./exec_apptainer_harmonia.sh --config <config.yaml>

# Then run the automated experiment script
python run_experiment.py <config.yaml>
```

## IMPORTANT: Local LLM Jobs

**Always use GPU partition for local LLM providers** (ollama, anyllm:ollama, local, anyllm:local).
Loading models on CPU takes 10-15+ minutes vs seconds on GPU. Without GPU:
- Model loading is extremely slow
- Inference is impractically slow
- Jobs may timeout before completing

When starting interactive sessions with local LLMs, ALWAYS include:
- `--partition=gpu`
- `--gpus-per-node=1`

**Startup timing:** After starting Ollama, wait at least 2.5 minutes before checking if Beaker is ready - model pre-loading takes time.

## Python Environment

**Always use the project `.venv`**, not conda or system Python:

```bash
.venv/bin/python <script.py>
```

This venv has Python 3.11, pydantic 2.12.5, PyYAML, and other project dependencies. Do NOT probe for conda environments or try `module load` — just use `.venv`.

## Model Registry Management

Before generating configs for OpenRouter models, check if the registry is current:
```bash
# Check age of registry file
find LLM_associated_metadata/openrouter_models.json -mmin +1440 2>/dev/null && echo "STALE" || echo "FRESH"
# If stale or missing (fetches both models and parameter meanings):
.venv/bin/python LLM_associated_metadata/fetch_openrouter.py
```

For Ollama models:
```bash
find LLM_associated_metadata/ollama_models.json -mmin +1440 2>/dev/null && echo "STALE" || echo "FRESH"
# If stale or missing:
.venv/bin/python LLM_associated_metadata/fetch_ollama_models.py
```

When creating configs for specific models, use `lookup_model.py` to get accurate metadata:
```bash
.venv/bin/python LLM_associated_metadata/lookup_model.py config-snippet openrouter:<model-id>
```

The `manage_configs.py clone` command auto-enriches configs with `model_metadata` from the registry (pricing, context length, capabilities). If the registry is stale or missing, it prints a warning.

## Practical Lessons

- **`.gitignore` uses repo-relative paths.** Absolute paths (e.g., `/hpc/compgen/.../logs/*`) silently fail. Use `logs/` not `/hpc/.../logs/*`.
- **`logs/` and `results/` are gitignored.** They contain experiment output (trace.json, conversation.md, SLURM logs) that should not be version-controlled.
- **Run IDs link logs to results.** Every experiment gets an 8-char hex ID. In automated mode, the SBATCH template generates it; in manual mode, `exec_apptainer_harmonia.sh` generates it. The ID appears in log filenames, results directory names, and the `.experiment_id` JSON file.
- **Gold standard files live outside the git repo** in `../../raw/datasets_harmonia/.../gold_standard/`. They are referenced by absolute path in experiment config YAMLs.
