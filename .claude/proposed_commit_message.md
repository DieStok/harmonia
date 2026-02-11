# Proposed Commit Message

```
Add experiment tracking, metrics evaluation, per-job Ollama isolation,
log analysis tooling, and automated experiment infrastructure overhaul

This commit represents the work from 05-Feb through 11-Feb 2026 across
multiple sessions. It touches nearly every layer of the Harmonia
experiment automation stack: infrastructure scripts, automation
framework, experiment configs, evaluation pipeline, and developer
tooling.

---

## 1. Metrics Evaluation Pipeline (NEW)

Added `src/evaluation/` with Pydantic v2 schema (v1.1) and metrics
calculation for comparing LLM-harmonized output to gold standard data.

- `src/evaluation/schemas.py` — Pydantic models: ExperimentMetadata,
  ColumnMappingMetrics (dual precision incl/excl null), ColumnValueMetrics
  (per-column accuracy, macro-averaged P/R/F1), ErrorCategorization
  (whitespace_only, case_only, genuine), confusion matrices, OverallSummary
- `src/evaluation/metrics.py` — Core calculation: column mapping quality,
  value harmonization quality, numeric tolerance for float columns,
  index-based row alignment (inner join), error categorization
- `calculate_metrics.py` — Standalone CLI entry point for metrics
  calculation against gold standard CSVs

Metrics are also auto-calculated at the end of `run_experiment.py` when
an `evaluation:` block is present in the experiment config YAML.

See: plans/10_02_2026_implementing_metadata_harmonization_metrics_calculation.md

## 2. Evaluation Config Support in Experiment YAMLs

- `src/automation/config.py` — Added EvaluationConfig dataclass with
  fields for gold_standard, gold_column_mapping, gold_value_mapping,
  acceptable_columns_file, column/value mapping file names,
  index_column, and numeric_tolerance. Wired into ExperimentConfig
  and from_dict() parser.
- Created gold standard reference files for Experiment 1 (dou.csv)
  in raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/:
  - harmonized_dou_correct.csv — manually verified harmonized output
  - gold_standard_column_mapping.json — correct source→GDC column map
  - gold_standard_value_mapping.json — correct value transformations
  - harmonization_acceptable_columns.json — acceptable column alternatives
  (These files live outside this repo in the shared raw/ directory.)
- All automated experiment configs updated with `evaluation:` blocks
  pointing to those gold standard files
- `run_experiment.py` — Added post-experiment metrics calculation:
  loads gold standard, runs calculate_all_metrics(), writes metrics.json

## 3. Uniform Experiment Tracking with Run ID (NEW)

Every experiment run is now assigned a unique 8-char hex run ID
(secrets.token_hex(4)) that links SLURM logs to results folders.

- `sbatch_template.sh`, `sbatch_template_gpu.sh` — Generate RUN_ID
  before log redirect; include in log filenames
  (logs/<timestamp>_<name>_<jobid>_<run_id>.out); pass --run-id to
  exec script
- `exec_apptainer_harmonia.sh` — Added --run-id/-R flag; auto-generates
  RUN_ID if not provided; includes run_id in results directory name;
  creates .experiment_id JSON metadata file in results directory
- `src/automation/runner.py` — Reads RUN_ID from os.environ; includes
  in output directory name

The .experiment_id file contains: run_id, experiment_name,
experiment_mode (automated/manual), config_file, llm_provider,
llm_model, timestamp, slurm_job_id, and log_files paths.

See: plans/11_02_2026_1250_implementation_spec_uniform_experiment_tracking_with_unique_ID.md

## 4. Per-Job Ollama Isolation

- `exec_apptainer_harmonia.sh` — Major rewrite (~630 lines added):
  dynamic Ollama port per SLURM job (11434 + 1 + SLURM_JOB_ID % 200),
  per-job PID file (.ollama_${SLURM_JOB_ID}.pid), per-job runtime
  directory ($TMPDIR/ollama_${SLURM_JOB_ID}), per-job serve log,
  automatic Ollama start/stop for local LLM providers, model
  pre-loading/warming, proper cleanup on exit
- `sbatch_template_gpu.sh` — Displays Ollama port in job output
- Interactive/manual mode (no SLURM) keeps default port 11434

See: plans/10_02_2026_1830_make_separate_ollama_instances.md

## 5. Log and Trace Analysis Tooling (NEW)

- `code_development_tools_agents/monitoring_and_evaluation/
  types_of_log_and_trace_problems.yaml` — Machine-readable error
  taxonomy with 13 problem classes across 5 categories:
  Infrastructure (1A), LLM Connectivity (2A-2D), LLM Behavior (3A-3C),
  Data/Config (4A-4B), Experiment Lifecycle (5A-5C). Each class has
  detection keywords, regex patterns, severity, examples, remediation.
- `code_development_tools_agents/monitoring_and_evaluation/
  read_and_analyze_logs_and_traces_cli.py` — CLI tool (~700 lines)
  with Pydantic output schema. Discovers logs and results directories,
  links them by run_id (new) or experiment_name+timestamp (legacy),
  detects problems via keyword matching AND compound Python logic
  (e.g., distinguishing "all turns timed out" infrastructure hang
  from "some turns timed out" LLM-side timeout). Supports --verbose,
  --json, --run-id, --experiment filtering.
- `documentation/processes/11_02_2026_interpreting_logs_and_traces.md`
  — Comprehensive human-readable failure mode reference document

See: plans/11_02_2026_1140_analyze_failure_modes_automated_experiments.md

## 6. Manual Experiment Monitoring

- `run_manual_experiment.py` — Major expansion: WebSocket passive
  monitoring of interactive Beaker sessions, producing trace.json
  and conversation.md just like automated experiments. Supports
  --monitor flag via exec_apptainer_harmonia.sh for single-command
  launch.
- `src/automation/manual_runner.py` — ManualExperimentRunner class
  for passive WebSocket monitoring with auto-save after each turn.

## 7. SBATCH Templates & Log Naming

- Both templates now use date-stamped log filenames:
  logs/<DD-MM-YYYY_HHMM>_<experiment_name>_<SLURM_JOB_ID>_<run_id>.out
  (previously: logs/<experiment_name>_<jobid>.out)
- GPU template adds --gpus-per-node=1 and --partition=gpu
- Both pass --run-id and --job-name to exec_apptainer_harmonia.sh

## 8. Experiment Config Changes

- DELETED: dou_harmonization_mimo-v2-flash.yaml (and _associated.env)
  — OpenRouter free period ended, model no longer available
- DELETED: dou_harmonization_anyllm_openrouter.yaml (and _associated.env)
  — Same reason (used mimo-v2-flash via anyllm:openrouter)
- MODIFIED: dou_harmonization_olmo3.yaml — Changed model from
  olmo-3.1:32b to olmo-3:32b-think (correct Ollama registry name)
- All configs: Added evaluation: block with gold standard paths,
  added data path prefix fix (data/ -> data/one_metadata_table...)

## 9. Container & Build

- `harmonia_beaker_LLM_agent_environment_apptainer.def` (NEW) —
  Apptainer definition with any-llm-sdk, ollama package
- `build_harmonia_apptainer.sh` (NEW) — Build script for new image

## 10. .gitignore & Housekeeping

- Fixed .gitignore: replaced non-functional absolute path with
  relative `logs/` and `results/` entries
- Removed 58 log files and 59 results files from git tracking
  (files remain on disk, just untracked going forward)
- Added `src/evaluation/`, `code_development_tools_agents/`,
  documentation, plans, instructions as new tracked directories

## 11. Documentation

- `documentation/codebase_descriptions/how_this_codebase_works_11_02_2026.md`
  — Updated codebase description with all changes above
- `documentation/codebase_descriptions/how_this_codebase_works_10_02_2026.md`
  — Previous day's description
- `documentation/codebase_descriptions/how_this_codebase_works_05_02_2026.md`
  — Earlier description (any-llm integration)

---

For detailed context on each feature area, see:
- plans/11_02_2026_1250_implementation_spec_uniform_experiment_tracking_with_unique_ID.md
- plans/11_02_2026_1140_analyze_failure_modes_automated_experiments.md
- plans/10_02_2026_1830_make_separate_ollama_instances.md
- plans/10_02_2026_implementing_metadata_harmonization_metrics_calculation.md
- documentation/processes/11_02_2026_interpreting_logs_and_traces.md

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```
