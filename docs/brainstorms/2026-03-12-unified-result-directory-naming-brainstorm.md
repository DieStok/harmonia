# Brainstorm: Unified Result Directory Naming

**Date:** 2026-03-12
**Status:** Ready for planning

## What We're Building

A single, consistent result directory naming scheme that eliminates the current bug where every automated experiment creates **two** result directories per run — one by the SBATCH/shell layer and one by the Python runner.

### The Problem

Three independent layers each construct result directory paths with different naming schemes:

| Layer | File | Pattern | What it creates |
|-------|------|---------|----------------|
| SBATCH template | `sbatch_template.sh:35`, `sbatch_template_gpu.sh:38` | `<experiment_name>_<SLURM_JOB_ID>_<run_id>` | Dir with `.runtime/`, `full_prompt_composition.json` |
| exec_apptainer_harmonia.sh | `exec_apptainer_harmonia.sh:175-177` | `<experiment_name>_<YYYYMMDD_HHMMSS>_<run_id>` | Only when `--results-dir` not provided (manual mode) |
| Python runner | `src/automation/runner.py:56-63` | `<experiment_name>_<YYYYMMDD_HHMMSS>_<run_id>` | `config_snapshot.yaml`, `conversation.md`, `trace.json` (the real results) |

In automated mode, the SBATCH template passes `--results-dir` to exec_apptainer, which bind-mounts it as `/workspace/results` in the container. But the Python runner ignores the `RESULTS_DIR` environment variable and constructs its own path from `config.output.base_dir`, creating a second directory.

### Evidence from March 11 runs

Every run produced two directories sharing the same run_id:
- `dou_harmonization_bdikit-tools_qwen3.5-9b_48213672_abd91539` (SBATCH — contains `.runtime/`, `full_prompt_composition.json`)
- `dou_harmonization_bdikit-tools_qwen3.5-9b_20260311_125939_abd91539` (Python — contains actual results)

## Why This Approach

### Chosen naming format

```
<YYYYMMDD_HHMMSS>_<experiment_name>_<SLURM_JOB_ID>_<run_id>
```

Example: `20260311_125939_dou_harmonization_bdikit-tools_qwen3.5-9b_48213672_abd91539`

**Rationale:**
- Datetime first: directories sort chronologically with plain `ls`
- Experiment name: human-readable identification of what ran
- SLURM job ID: correlate with `seff`/`squeue`/SLURM logs
- Run ID (8-char hex): canonical link between logs and results

**Fallback for non-SBATCH runs:** `$SLURM_JOB_ID` (usually available from `srun`) -> `"manual"` placeholder.

## Key Decisions

1. **Single source of truth for directory naming:** The SBATCH template constructs the canonical path and passes it through the entire chain. The Python runner must use the provided path, not construct its own.

2. **The `RESULTS_DIR` environment variable becomes authoritative inside the container.** The Python runner should check for it before falling back to constructing a path from config.

3. **All artifacts go in one directory:** `.runtime/`, `full_prompt_composition.json`, `config_snapshot.yaml`, `conversation.md`, `trace.json`, `column_mapping.json`, etc. — all in the same run directory.

4. **Datetime is generated once** in the SBATCH template (or exec script for manual mode) and propagated, not regenerated independently by each layer.

5. **Backward compatibility:** All parsers must handle both old (`<experiment_name>_<YYYYMMDD_HHMMSS>_<run_id>`) and new (`<YYYYMMDD_HHMMSS>_<experiment_name>_<SLURM_JOB_ID>_<run_id>`) formats, so old results can still be analyzed.

6. **Re-run `generate_jobs.py`** after template changes to regenerate all job scripts.

## Complete File Change Inventory

### A. Directory Constructors (the root cause fix)

| File | Lines | Current behavior | Required change |
|------|-------|-----------------|-----------------|
| `sbatch_template.sh` | 35 | `{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}` | `${TIMESTAMP}_{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}` (add TIMESTAMP generation) |
| `sbatch_template_gpu.sh` | 38 | `{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}` | Same as above |
| `exec_apptainer_harmonia.sh` | 175-177 | `${EXPERIMENT_NAME}_${TIMESTAMP}_${RUN_ID}` | `${TIMESTAMP}_${EXPERIMENT_NAME}_${SLURM_JOB_ID:-manual}_${RUN_ID}` |
| `src/automation/runner.py` | 56-63 | Always constructs own `<name>_<ts>_<runid>` from config | Check `RESULTS_DIR` env var first; only construct fallback path using new format |
| `src/automation/manual_runner.py` | 76-82 | Same as runner.py | Same fix as runner.py |
| `run_manual_experiment.py` | 121-123 | Constructs `<name>_<ts>` | Use new format with SLURM_JOB_ID fallback |

### B. Directory Name Parsers (backward-compatible updates)

| File | Lines | What it parses | Required change |
|------|-------|---------------|-----------------|
| `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` | 79-81 | `RESULTS_FOLDER_PATTERN`: `^(.+?)_(\d{8}_\d{6})(?:_([a-f0-9]{8}))?$` | Add alternative pattern for new format; try new first, fall back to old |
| `src/dashboard/data_loader.py` | 34-36, 84, 99-104 | `_SLURM_JOB_ID_RE`, `_TIMESTAMP_RE`, run_id extraction | Update to handle datetime-first format |
| `src/evaluation/visualization/io.py` | 8, 28-35 | `RUN_ID_PATTERN = r"_([0-9a-f]{8})$"` | **No change needed** — run_id stays at end |
| `src/evaluation/visualization/normalize.py` | 50-63 | Globs `*_<run_id>/.runtime/.experiment_id` | **No change needed** — glob still matches |
| `src/evaluation/visualization/enrich.py` | 9-12, 29 | `MODEL_TOKEN_PATTERN` searches experiment_name | **No change needed** — searches anywhere in string |
| `results/plots/generate_march11_experiment_overview.py` | 84-90 | `_DIR_PATTERN` hardcoded to `dou_harmonization_<ctx>_<model>_<date>_<time>_<runid>` | Add new-format pattern; keep old for existing March 11 data |

### C. Log Filename Patterns (also need updating)

The log filenames also embed experiment names and SLURM job IDs. These patterns in `read_and_analyze_logs_and_traces_cli.py` should be audited but may not need changes since log naming is independent of result dir naming:

| Pattern | Lines | Format | Needs change? |
|---------|-------|--------|--------------|
| `AUTO_LOG_PATTERN` | 58-60 | `<DD-MM-YYYY_HHMM>_<exp>_<jobid>[_<runid>].(out\|err)` | Only if log naming also changes |
| `AUTO_COMPONENT_LOG_PATTERN` | 63-65 | `<exp>_<jobid>[_<runid>]_(beaker\|ollama).log` | Only if log naming also changes |
| `MANUAL_BEAKER_LOG_PATTERN` | 68-70 | `[<exp>_]beaker_<YYYYMMDD_HHMMSS>[_<runid>].log` | Probably no |
| `MANUAL_OLLAMA_LOG_PATTERN` | 74-76 | `[<exp>_]ollama_<YYYYMMDD_HHMMSS>[_<runid>].log` | Probably no |

### D. No Changes Needed

| File | Reason |
|------|--------|
| `src/prompt_logging.py` | Uses `RESULTS_DIR` env var directly — already correct |
| `calculate_metrics.py` | Reads `.experiment_id` JSON, doesn't parse dir names |
| `src/evaluation/visualization/failure_io.py` | Processes already-parsed metadata |
| `generate_jobs.py` | Needs re-running, but its template variable substitution doesn't change |
| `manage_configs.py` | Config management only, no dir name parsing |

## Resolved Questions

1. **`full_prompt_composition.json` placement:** Written by `src/prompt_logging.py:250` using the `RESULTS_DIR` env var (which points to the SBATCH-created dir inside the container as `/workspace/results`). Once the Python runner also writes to this same dir, everything will be co-located. No change needed in `prompt_logging.py`.

2. **Regenerate job scripts:** Yes — re-run `generate_jobs.py` after template changes.

3. **Downstream parser backward compatibility:** All parsers will support both old and new formats. The `RUN_ID_PATTERN` (trailing `_[0-9a-f]{8}`) and glob-based lookups already work with both formats. Only `RESULTS_FOLDER_PATTERN` and `_DIR_PATTERN` need dual-format support.
