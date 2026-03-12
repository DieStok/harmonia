---
title: "fix: Unify result directory naming to one directory per run"
type: fix
status: completed
date: 2026-03-12
origin: docs/brainstorms/2026-03-12-unified-result-directory-naming-brainstorm.md
---

# fix: Unify result directory naming to one directory per run

## Overview

Every automated experiment currently creates **two** result directories per run — one by the SBATCH shell layer (with SLURM job ID) and one by the Python runner (with datetime timestamp). This fix unifies them into a single directory using the format `<YYYYMMDD_HHMMSS>_<experiment_name>_<SLURM_JOB_ID>_<run_id>`, and updates all downstream parsers to handle both old and new formats.

(See brainstorm: `docs/brainstorms/2026-03-12-unified-result-directory-naming-brainstorm.md` for full root cause analysis and design decisions.)

## Problem Statement

Three independent layers construct result directory paths:
1. **SBATCH template** creates `<experiment_name>_<SLURM_JOB_ID>_<run_id>` (contains `.runtime/`, `full_prompt_composition.json`)
2. **exec_apptainer_harmonia.sh** creates `<experiment_name>_<YYYYMMDD_HHMMSS>_<run_id>` (manual mode only)
3. **Python runner** creates `<experiment_name>_<YYYYMMDD_HHMMSS>_<run_id>` (contains actual results: `trace.json`, `conversation.md`, etc.)

The Python runner ignores the `RESULTS_DIR` environment variable that the shell layer sets, and constructs its own path from `config.output.base_dir`. Evidence: every March 11 run has two dirs sharing the same run_id but different names.

## Proposed Solution

### New canonical format

```
<YYYYMMDD_HHMMSS>_<experiment_name>_<SLURM_JOB_ID>_<run_id>
```

Example: `20260311_125939_dou_harmonization_bdikit-tools_qwen3.5-9b_48213672_abd91539`

### Core principle

The **outermost layer** (SBATCH template or exec script) constructs the directory name once. All inner layers (exec script, Python runner) receive and reuse it — they never construct their own.

## Technical Approach

### Implementation Phases

#### Phase 1: Fix Directory Constructors (the root cause)

These changes eliminate the duplicate directory creation.

##### 1a. `sbatch_template.sh` (line 35)

**Current:**
```bash
RUN_RESULTS_DIR="{{project_dir}}/results/{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}"
```

**New:**
```bash
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
RUN_RESULTS_DIR="{{project_dir}}/results/${TIMESTAMP}_{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}"
```

##### 1b. `sbatch_template_gpu.sh` (line 38)

**Current:**
```bash
RUN_RESULTS_DIR="results/{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}"
```

**New:**
```bash
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
RUN_RESULTS_DIR="results/${TIMESTAMP}_{{experiment_name}}_${SLURM_JOB_ID}_${RUN_ID}"
```

##### 1c. `exec_apptainer_harmonia.sh` (lines 175-177)

This block fires when `--results-dir` was NOT provided (manual/interactive mode). Update to use the new format.

**Current:**
```bash
if [ -n "$CONFIG_FILE" ] && [ "$RESULTS_DIR" = "$DEFAULT_RESULTS_DIR" ]; then
    TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
    RESULTS_DIR="${DEFAULT_RESULTS_DIR}/${EXPERIMENT_NAME}_${TIMESTAMP}_${RUN_ID}"
```

**New:**
```bash
if [ -n "$CONFIG_FILE" ] && [ "$RESULTS_DIR" = "$DEFAULT_RESULTS_DIR" ]; then
    TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
    SLURM_ID="${SLURM_JOB_ID:-${SLURM_JOBID:-manual}}"
    RESULTS_DIR="${DEFAULT_RESULTS_DIR}/${TIMESTAMP}_${EXPERIMENT_NAME}_${SLURM_ID}_${RUN_ID}"
```

##### 1d. `src/automation/runner.py` (lines 55-63)

The critical fix: respect `RESULTS_DIR` env var when set.

**Current:**
```python
# Set up output directory (includes RUN_ID if available from environment)
timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
self.run_id = os.environ.get("RUN_ID", "")
base_dir = Path(output_dir or config.output.base_dir)
if self.run_id:
    self.output_dir = base_dir / f"{config.name}_{timestamp}_{self.run_id}"
else:
    self.output_dir = base_dir / f"{config.name}_{timestamp}"
self.output_dir.mkdir(parents=True, exist_ok=True)
```

**New:**
```python
# Use RESULTS_DIR env var if set (authoritative — set by exec_apptainer_harmonia.sh).
# Only construct our own path as fallback (e.g. running outside container).
self.run_id = os.environ.get("RUN_ID", "")
env_results_dir = os.environ.get("RESULTS_DIR")

if env_results_dir and Path(env_results_dir).is_dir():
    self.output_dir = Path(env_results_dir)
elif output_dir:
    self.output_dir = Path(output_dir)
else:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    slurm_id = os.environ.get("SLURM_JOB_ID", os.environ.get("SLURM_JOBID", "manual"))
    base_dir = Path(config.output.base_dir)
    if self.run_id:
        self.output_dir = base_dir / f"{timestamp}_{config.name}_{slurm_id}_{self.run_id}"
    else:
        self.output_dir = base_dir / f"{timestamp}_{config.name}_{slurm_id}"
self.output_dir.mkdir(parents=True, exist_ok=True)
```

##### 1e. `src/automation/manual_runner.py` (lines 75-83)

Identical fix to runner.py — same pattern of checking `RESULTS_DIR` first.

##### 1f. `run_manual_experiment.py` (lines 119-125)

Update `create_experiment_output_dir()` to use new format and include run_id.

**Current:**
```python
def create_experiment_output_dir(config, output_dir_override: Path = None) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_dir = Path(output_dir_override or config.output.base_dir)
    output_dir = base_dir / f"{config.name}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
```

**New:**
```python
def create_experiment_output_dir(config, output_dir_override: Path = None) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = os.environ.get("RUN_ID", "")
    slurm_id = os.environ.get("SLURM_JOB_ID", os.environ.get("SLURM_JOBID", "manual"))
    base_dir = Path(output_dir_override or config.output.base_dir)
    name_parts = [timestamp, config.name, slurm_id]
    if run_id:
        name_parts.append(run_id)
    output_dir = base_dir / "_".join(name_parts)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
```

---

#### Phase 2: Update Parsers (backward-compatible)

All parsers must handle **both** old and new formats to support re-analyzing historical results.

##### 2a. `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`

**`RESULTS_FOLDER_PATTERN` (line 79-81):** Replace single pattern with two patterns tried in order.

```python
# New format: {YYYYMMDD_HHMMSS}_{experiment_name}_{SLURM_JOB_ID}_{run_id}
RESULTS_FOLDER_PATTERN_NEW = re.compile(
    r"^(\d{8}_\d{6})_(.+?)_(\d+|manual)_([a-f0-9]{8})$"
)
# Old format: {experiment_name}_{YYYYMMDD_HHMMSS}[_{run_id}]
RESULTS_FOLDER_PATTERN_OLD = re.compile(
    r"^(.+?)_(\d{8}_\d{6})(?:_([a-f0-9]{8}))?$"
)
```

**`discover_results()` (lines 297-311):** Try new pattern first, fall back to old.

```python
def discover_results(results_dir: Path) -> list[DiscoveredResults]:
    results = []
    for d in results_dir.iterdir():
        if not d.is_dir():
            continue
        m = RESULTS_FOLDER_PATTERN_NEW.match(d.name)
        if m:
            results.append(DiscoveredResults(
                path=d,
                experiment_name=m.group(2),
                timestamp_str=m.group(1),
                run_id=m.group(4),
                slurm_job_id=m.group(3),
            ))
            continue
        m = RESULTS_FOLDER_PATTERN_OLD.match(d.name)
        if m:
            results.append(DiscoveredResults(
                path=d,
                experiment_name=m.group(1),
                timestamp_str=m.group(2),
                run_id=m.group(3),
            ))
    return results
```

Also add optional `slurm_job_id` field to `DiscoveredResults` dataclass.

##### 2b. `src/dashboard/data_loader.py`

**Lines 70-104 (`_build_run_index`):** The deduplication logic (preferring SLURM-format dirs) becomes unnecessary after the fix — there will be one dir per run_id. Simplify but keep safe:

```python
def _build_run_index(self):
    if not self.results_dir.is_dir():
        return
    candidates: dict[str, list[Path]] = {}
    for d in sorted(self.results_dir.iterdir()):
        if not d.is_dir():
            continue
        m = RUN_ID_PATTERN.search(d.name)
        if m:
            rid = m.group(1)
            candidates.setdefault(rid, []).append(d)
    with self._cache_lock:
        for rid, dirs in candidates.items():
            if len(dirs) == 1:
                self._run_index[rid] = dirs[0]
            else:
                # Multiple dirs for same run_id (legacy duplication).
                # Prefer the one that contains trace.json (the real results).
                best = dirs[0]
                for d in dirs:
                    if (d / "trace.json").exists():
                        best = d
                        break
                self._run_index[rid] = best
```

This is more robust than the current SLURM-format preference (which picks the empty dir) and works for both old and new naming.

##### 2c. `results/plots/generate_march11_experiment_overview.py`

**Lines 84-90:** Add new format pattern alongside existing one. Since this script is specific to March 11 historical data, the old pattern can remain as-is. Add a second pattern for future use:

```python
# New format: {YYYYMMDD}_{HHMMSS}_{context}_{model}_{slurm_id}_{run_id}
_DIR_PATTERN_NEW = re.compile(
    r"(?P<date>\d{8})_(?P<time>\d{6})_"
    r"dou_harmonization_"
    r"(?P<context>bdikit-tools|code-context|codeact)_"
    r"(?P<model_token>[^_]+(?:-[^_]+)*)_"
    r"(?P<slurm_id>\d+|manual)_"
    r"(?P<run_id>[0-9a-f]{8})$"
)
# Old format (March 11 historical data)
_DIR_PATTERN = re.compile(
    r"dou_harmonization_"
    r"(?P<context>bdikit-tools|code-context|codeact)_"
    r"(?P<model_token>[^_]+(?:-[^_]+)*)_"
    r"(?P<date>\d{8})_(?P<time>\d{6})_"
    r"(?P<run_id>[0-9a-f]{8})$"
)
```

Update the discovery function to try both patterns.

---

#### Phase 3: Regenerate Job Scripts and Verify

##### 3a. Re-run `generate_jobs.py`

After template changes, regenerate all job scripts:

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
.venv/bin/python generate_jobs.py --config <each active config>
```

Verify that generated scripts contain the new `TIMESTAMP` variable and new `RUN_RESULTS_DIR` format.

##### 3b. Smoke test with one job

Submit a single experiment and verify:
- [ ] Only **one** result directory is created per run
- [ ] Directory name matches `<YYYYMMDD_HHMMSS>_<experiment_name>_<SLURM_JOB_ID>_<run_id>`
- [ ] All artifacts are co-located: `.runtime/`, `full_prompt_composition.json`, `config_snapshot.yaml`, `conversation.md`, `trace.json`
- [ ] Log analysis CLI correctly discovers the new-format directory
- [ ] Dashboard correctly loads the run

##### 3c. Verify backward compatibility

Run the log analysis CLI and dashboard against **existing** March 11 result directories to confirm old-format parsing still works.

---

## Files Changed Summary

### Must change (6 files)

| File | Change type |
|------|------------|
| `sbatch_template.sh` | Add TIMESTAMP, reorder dir name |
| `sbatch_template_gpu.sh` | Same |
| `exec_apptainer_harmonia.sh` | Reorder dir name, add SLURM_JOB_ID fallback |
| `src/automation/runner.py` | Respect RESULTS_DIR env var, new fallback format |
| `src/automation/manual_runner.py` | Same as runner.py |
| `run_manual_experiment.py` | New format in `create_experiment_output_dir()` |

### Must update parsers (3 files)

| File | Change type |
|------|------------|
| `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` | Dual-format RESULTS_FOLDER_PATTERN, add slurm_job_id to DiscoveredResults |
| `src/dashboard/data_loader.py` | Replace SLURM-preference dedup with trace.json-based dedup |
| `results/plots/generate_march11_experiment_overview.py` | Add new-format pattern |

### No change needed (5 files)

| File | Reason |
|------|--------|
| `src/prompt_logging.py` | Already uses `RESULTS_DIR` env var |
| `src/evaluation/visualization/io.py` | `RUN_ID_PATTERN` matches trailing `_[0-9a-f]{8}` — still works |
| `src/evaluation/visualization/normalize.py` | Glob `*_<run_id>/...` still works |
| `src/evaluation/visualization/enrich.py` | `MODEL_TOKEN_PATTERN` searches anywhere in string |
| `calculate_metrics.py` | Reads `.experiment_id` JSON, no dir name parsing |

## Acceptance Criteria

- [x] Automated experiments create exactly **one** result directory per run
- [x] Directory name format: `<YYYYMMDD_HHMMSS>_<experiment_name>_<SLURM_JOB_ID>_<run_id>`
- [x] Manual experiments use same format with `$SLURM_JOB_ID` or `"manual"` fallback
- [x] All artifacts (`trace.json`, `conversation.md`, `config_snapshot.yaml`, `full_prompt_composition.json`, `.runtime/`) land in the same directory
- [x] Log analysis CLI (`read_and_analyze_logs_and_traces_cli.py`) correctly parses both old and new format dirs
- [x] Dashboard (`data_loader.py`) loads both old and new format runs
- [x] `generate_march11_experiment_overview.py` still works on old March 11 data
- [x] Python runner uses `RESULTS_DIR` env var when available (inside container), constructs own path only as fallback (outside container)

## Dependencies & Risks

- **Low risk:** Changes are to experiment infrastructure only, not to LLM interaction or evaluation logic
- **Backward compat risk:** Mitigated by dual-format parsers. If a regex is wrong, old runs become invisible to tooling. Test against existing results before deploying.
- **Job script staleness:** After template changes, any un-regenerated job scripts will still use the old format. Mitigated by re-running `generate_jobs.py` as part of this change.

## Sources & References

- **Origin brainstorm:** [docs/brainstorms/2026-03-12-unified-result-directory-naming-brainstorm.md](docs/brainstorms/2026-03-12-unified-result-directory-naming-brainstorm.md) — key decisions: datetime-first format, RESULTS_DIR env var as authority, backward-compatible parsers
- Root cause files: `sbatch_template.sh:35`, `src/automation/runner.py:56-63`
- Evidence: March 11 duplicate directories in `results/`
