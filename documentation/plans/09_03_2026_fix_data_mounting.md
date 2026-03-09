# Fix Data Mounting: LLM Should Only See Specified Files

**Date:** 2026-03-09
**Status:** Ready for implementation

## Context for Fresh Claude Instance

**Project root:** `/hpc/compgen/projects/llm_GEO_project/`
**Git repo root:** `harmonia_metadata_agent/analysis/dstoker/harmonia/` (all relative paths below are from here)
**Python venv:** `.venv/` (Python 3.11, has PyYAML, pydantic — always use `.venv/bin/python`)
**Apptainer image:** `harmonia_beaker_LLM_agent_environment_apptainer.sif` (does NOT need rebuild for this change)
**Container def:** `harmonia_beaker_LLM_agent_environment_apptainer.def` (NOT modified in this plan)
**Pre-commit hooks:** ruff, shellcheck (excludes `jobs/` and `sbatch_template*`), yamllint (excludes `experiments/`)

The Harmonia project runs LLM agents inside Apptainer containers to evaluate their performance on biomedical data harmonization tasks. The container provides a Beaker notebook environment where the LLM executes Python code. The exec script (`exec_apptainer_harmonia.sh`) orchestrates everything: reading config YAMLs, generating .env files, starting Ollama (for local LLMs), creating bind mounts, and launching the container.

## Problem

When the Apptainer container runs, the LLM agent inside it sees files it should NOT see:

**Data problem — the LLM sees everything:**
```
/workspace/data/                                    ← entire datasets_harmonia/ mounted
  one_metadata_table_gdc_schema/
    data/dou.csv                                    ← the actual input file
    data/dou-ucec-discovery.csv                     ← unrelated file
    data/dou_with_index.csv                         ← unrelated file
    gold_standard/harmonized_dou_correct.csv        ← ANSWERS! LLM can cheat
    gold_standard/gold_standard_column_mapping.json ← ANSWERS!
    gold_standard/gold_standard_value_mapping.json  ← ANSWERS!
    papers/dou2020.pdf                              ← irrelevant
    other/                                          ← irrelevant
    experiment_metadata.yaml                        ← irrelevant
  ten_metadata_tables_harmonize/                    ← entirely different experiment
  two_metadata_tables_harmonize/                    ← entirely different experiment
```

**Results problem — runtime plumbing visible:**
```
/workspace/results/
  .beaker_runtime/     ← Beaker kernel state
  .jupyter_runtime/    ← Jupyter cookie secret, etc.
  .ipython/            ← IPython history
  .experiment_id       ← JSON metadata (run_id, config, etc.)
  .cache/huggingface/  ← HF model downloads (created on first use)
```

## Root Cause

Two bind mounts in `exec_apptainer_harmonia.sh` (lines 982-983):

```bash
--bind ${DATA_BASE_DIR}:/workspace/data:ro          # Mounts ALL of datasets_harmonia/
--bind ${RESULTS_DIR}:/workspace/results             # Shares runtime + LLM output
```

Where:
- `DATA_BASE_DIR` defaults to `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia` (set on line 28)
- `RESULTS_DIR` is computed as `results/<experiment_name>_<timestamp>_<run_id>/` (around line 175)

## Solution: Two Changes

### Change A: Per-experiment data mounting (config-driven, mandatory)

Add a `data` section to experiment config YAMLs specifying exactly which files to expose. The exec script reads this and creates individual bind mounts. **If the `data` section is missing, the script MUST fail with a descriptive error** — no fallback to legacy behavior.

### Change B: Separate runtime dirs from LLM-visible results

Mount runtime artifacts to `/runtime` inside the container (outside `/workspace`), backed by `${RESULTS_DIR}/.runtime/` on the host. The LLM only sees `/workspace/results/` which starts empty and only contains its own output.

---

## Detailed Implementation

### Step 1: Add `data` section to experiment config YAML schema

In each config YAML, add a new top-level `data` key:

```yaml
data:
  base_dir: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia
  files:
    - source: one_metadata_table_gdc_schema/data/dou.csv
      mount_as: dou.csv
```

- `base_dir` — absolute path to the dataset root on the host
- `files` — list of files to expose. Each entry has:
  - `source` — path relative to `base_dir`
  - `mount_as` — filename as seen by the LLM at `/workspace/data/<mount_as>`

The LLM will see ONLY `/workspace/data/dou.csv` — nothing else.

### Step 2: Modify `exec_apptainer_harmonia.sh` — data mounting

**Location:** Replace lines 980-984 (the current data bind mount block).

The current code:
```bash
# Bind workspace structure into container
# We bind to /workspace which becomes the working directory
APPTAINER_CMD="$APPTAINER_CMD --bind ${DATA_BASE_DIR}:/workspace/data:ro"
APPTAINER_CMD="$APPTAINER_CMD --bind ${RESULTS_DIR}:/workspace/results"
APPTAINER_CMD="$APPTAINER_CMD --pwd /workspace"
```

Replace with:

```bash
# =============================================================================
# Data mounting: per-file isolation from config YAML
# =============================================================================
if [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ]; then
    # Read data.files from config — MANDATORY
    DATA_MOUNT_JSON=$("${SCRIPT_DIR}/.venv/bin/python" -c "
import yaml, json, sys
with open('${CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
data = cfg.get('data')
if not data:
    print('ERROR: Config YAML is missing required \"data\" section.', file=sys.stderr)
    print('Add a data section specifying which files the LLM should see:', file=sys.stderr)
    print('  data:', file=sys.stderr)
    print('    base_dir: /hpc/.../datasets_harmonia', file=sys.stderr)
    print('    files:', file=sys.stderr)
    print('      - source: one_metadata_table_gdc_schema/data/dou.csv', file=sys.stderr)
    print('        mount_as: dou.csv', file=sys.stderr)
    sys.exit(1)
files = data.get('files', [])
base = data.get('base_dir', '')
if not files or not base:
    print('ERROR: data section must have base_dir and at least one file entry.', file=sys.stderr)
    sys.exit(1)
print(json.dumps({'base_dir': base, 'files': files}))
" 2>&1)

    if [ $? -ne 0 ]; then
        echo "$DATA_MOUNT_JSON"
        exit 1
    fi

    # Generate and validate bind specs
    BIND_SPECS=$("${SCRIPT_DIR}/.venv/bin/python" -c "
import json, sys, os
info = json.loads(sys.argv[1])
base = info['base_dir']
for f in info['files']:
    src = os.path.join(base, f['source'])
    if not os.path.exists(src):
        print(f'ERROR: Data file not found: {src}', file=sys.stderr)
        sys.exit(1)
    dst = '/workspace/data/' + f['mount_as']
    print(f'{src}:{dst}:ro')
" "$DATA_MOUNT_JSON" 2>&1)

    if [ $? -ne 0 ]; then
        echo "$BIND_SPECS"
        exit 1
    fi

    echo "📂 Data mounting (per-file isolation):"
    while IFS= read -r bind_spec; do
        APPTAINER_CMD="$APPTAINER_CMD --bind ${bind_spec}"
        echo "   ${bind_spec}"
    done <<< "$BIND_SPECS"
else
    # No config file at all — this path is for bare exec without --config
    # Still mount full dir for backward compat in configless mode
    echo "📂 Data mounting (no config file: entire directory)"
    APPTAINER_CMD="$APPTAINER_CMD --bind ${DATA_BASE_DIR}:/workspace/data:ro"
fi

# Results and working directory
APPTAINER_CMD="$APPTAINER_CMD --bind ${RESULTS_DIR}:/workspace/results"
APPTAINER_CMD="$APPTAINER_CMD --pwd /workspace"
```

**Shell caveat already handled:** The `while IFS= read` with `<<< "$BIND_SPECS"` runs in the current shell (not a subshell), so `APPTAINER_CMD` modifications propagate correctly.

**Also update the example paths echo block** (lines ~986-999). Change:
```bash
echo "   - Input:  data/one_metadata_table_gdc_schema/data/dou.csv"
```
To:
```bash
echo "   - Input:  data/ (see mounted files above)"
```

### Step 3: Modify `exec_apptainer_harmonia.sh` — separate runtime dirs

**Location A: Host-side mkdir** — Replace lines 185-192.

Current code:
```bash
mkdir -p "$RESULTS_DIR"
# Keep Jupyter runtime artifacts inside the per-run results directory
RUNTIME_DIR_HOST="${RESULTS_DIR}/.jupyter_runtime"
mkdir -p "$RUNTIME_DIR_HOST"
# Keep Beaker runtime and IPython history/checkpoints in per-run storage
BEAKER_RUNTIME_DIR_HOST="${RESULTS_DIR}/.beaker_runtime"
IPYTHON_DIR_HOST="${RESULTS_DIR}/.ipython"
mkdir -p "$BEAKER_RUNTIME_DIR_HOST" "$IPYTHON_DIR_HOST"
```

Replace with:
```bash
mkdir -p "$RESULTS_DIR"
# Runtime artifacts go to .runtime/ — mounted at /runtime inside container
# This keeps /workspace/results clean (LLM only sees its own output)
RUNTIME_HOST_DIR="${RESULTS_DIR}/.runtime"
mkdir -p "${RUNTIME_HOST_DIR}/jupyter" "${RUNTIME_HOST_DIR}/beaker" \
         "${RUNTIME_HOST_DIR}/ipython" "${RUNTIME_HOST_DIR}/cache/huggingface"
```

**Location B: Container env vars** — Replace lines 1092-1095 and 1101-1102.

Current code:
```bash
APPTAINER_CMD="$APPTAINER_CMD --env JUPYTER_RUNTIME_DIR=/workspace/results/.jupyter_runtime"
APPTAINER_CMD="$APPTAINER_CMD --env XDG_RUNTIME_DIR=/workspace/results/.jupyter_runtime"
APPTAINER_CMD="$APPTAINER_CMD --env BEAKER_RUN_PATH=/workspace/results/.beaker_runtime"
APPTAINER_CMD="$APPTAINER_CMD --env IPYTHONDIR=/workspace/results/.ipython"
```
and (a few lines later):
```bash
APPTAINER_CMD="$APPTAINER_CMD --env HF_HOME=/workspace/results/.cache/huggingface"
APPTAINER_CMD="$APPTAINER_CMD --env TRANSFORMERS_CACHE=/workspace/results/.cache/huggingface"
```

Replace with (add the `/runtime` bind mount nearby):
```bash
# Mount runtime directory separately from results
APPTAINER_CMD="$APPTAINER_CMD --bind ${RUNTIME_HOST_DIR}:/runtime"

# Point runtime env vars to /runtime (NOT /workspace/results)
APPTAINER_CMD="$APPTAINER_CMD --env JUPYTER_RUNTIME_DIR=/runtime/jupyter"
APPTAINER_CMD="$APPTAINER_CMD --env XDG_RUNTIME_DIR=/runtime/jupyter"
APPTAINER_CMD="$APPTAINER_CMD --env BEAKER_RUN_PATH=/runtime/beaker"
APPTAINER_CMD="$APPTAINER_CMD --env IPYTHONDIR=/runtime/ipython"
```
and:
```bash
APPTAINER_CMD="$APPTAINER_CMD --env HF_HOME=/runtime/cache/huggingface"
APPTAINER_CMD="$APPTAINER_CMD --env TRANSFORMERS_CACHE=/runtime/cache/huggingface"
```

**Location C: Move `.experiment_id`** — Change line 336.

Current:
```bash
cat > "${RESULTS_DIR}/.experiment_id" <<EXPEOF
```

Change to:
```bash
cat > "${RUNTIME_HOST_DIR}/.experiment_id" <<EXPEOF
```

Also update the echo on line 354:
```bash
echo "Wrote .experiment_id to ${RUNTIME_HOST_DIR}/.experiment_id"
```

**IMPORTANT:** Note that `RUNTIME_HOST_DIR` must be defined BEFORE the `.experiment_id` write. Currently `.experiment_id` is written around line 336, and the mkdir for runtime dirs is around line 185-192. So the ordering is fine — just make sure `RUNTIME_HOST_DIR` is set by that point.

### Step 4: Update `.experiment_id` readers (3 files)

The `.experiment_id` file is read by host-side scripts. After moving it to `.runtime/.experiment_id`, update:

**File: `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`**
- Line 229: `self.has_experiment_id = (path / ".experiment_id").exists()` → `self.has_experiment_id = (path / ".runtime" / ".experiment_id").exists() or (path / ".experiment_id").exists()`
- Line 422: `eid_path = results.path / ".experiment_id"` → check `.runtime/.experiment_id` first, fall back to `.experiment_id` for old results dirs

**File: `src/evaluation/visualization/normalize.py`**
- Line 51: `direct = metrics_path.parent / ".experiment_id"` → `direct = metrics_path.parent / ".runtime" / ".experiment_id"`; add fallback to old location
- Line 55: `for candidate in sorted(results_root.glob(f"*_{run_id}/.experiment_id")):` → also glob `.runtime/.experiment_id`

**File: `calculate_metrics.py`**
- Line 102: `exp_id_file = results_dir / ".experiment_id"` → check `.runtime/.experiment_id` first, fall back

**Pattern for backward-compatible reading** (use everywhere):
```python
def find_experiment_id(results_dir: Path) -> Path | None:
    """Find .experiment_id in new (.runtime/) or old location."""
    new_path = results_dir / ".runtime" / ".experiment_id"
    if new_path.exists():
        return new_path
    old_path = results_dir / ".experiment_id"
    if old_path.exists():
        return old_path
    return None
```

### Step 5: Update all experiment config YAMLs

**Automated configs (38 files):** `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/*.yaml`

For each file:
1. Add the `data` section (as a top-level key)
2. Replace `/workspace/data/one_metadata_table_gdc_schema/data/dou.csv` with `/workspace/data/dou.csv` in `messages:` content strings

**Manual configs (13 files):** `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/*.yaml`

For each file:
1. Add the `data` section only (manual configs don't have `messages:`)

**Batch update script** (run from repo root with `.venv/bin/python`):

```python
#!/usr/bin/env python3
"""Add data section to all experiment configs and update message paths."""
import yaml
import glob

DATA_SECTION = {
    'base_dir': '/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia',
    'files': [
        {'source': 'one_metadata_table_gdc_schema/data/dou.csv', 'mount_as': 'dou.csv'}
    ]
}

OLD_PATH = '/workspace/data/one_metadata_table_gdc_schema/data/dou.csv'
NEW_PATH = '/workspace/data/dou.csv'

patterns = [
    "experiments/**/configs/automated/*.yaml",
    "experiments/**/configs/manual/*.yaml",
]

for pattern in patterns:
    for path in sorted(glob.glob(pattern, recursive=True)):
        with open(path) as f:
            cfg = yaml.safe_load(f)

        if cfg is None:
            print(f"SKIP (empty): {path}")
            continue

        cfg['data'] = DATA_SECTION

        # Update message paths (automated configs have messages)
        for msg in cfg.get('messages', []):
            if isinstance(msg.get('content'), str):
                msg['content'] = msg['content'].replace(OLD_PATH, NEW_PATH)

        with open(path, 'w') as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        print(f"Updated: {path}")
```

**Note:** `yaml.dump` reformats the YAML. This is the same approach used by `manage_configs.py` (line 122). The configs are machine-generated so reformatting is acceptable.

### Step 6: Verify workspace tree display still works

The `find /workspace -maxdepth 4` command (lines 1159-1164 in exec script) still works — it will now show only mounted files. Expected output:

```
/workspace
/workspace/data
/workspace/data/dou.csv
/workspace/results
```

### Step 7: Verify monitor mode doesn't need changes

The monitor process (line ~1226) binds `${SCRIPT_DIR}:/harmonia:ro` and `${RESULTS_DIR}:/results`. This is for the experiment runner (not the LLM kernel), so it correctly sees the full results dir. No changes needed.

### Step 8: Commit

```bash
cd harmonia_metadata_agent/analysis/dstoker/harmonia
git add exec_apptainer_harmonia.sh
git add experiments/experiment_1_harmonia_dou2020_gdc/configs/
git add code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py
git add src/evaluation/visualization/normalize.py
git add calculate_metrics.py
git commit -m "Isolate LLM data visibility: per-file mounts and separate runtime dirs

Data: mount only config-specified files instead of entire datasets_harmonia/.
Configs without a 'data' section now fail with a descriptive error.
Runtime: move .jupyter_runtime, .beaker_runtime, .ipython, .cache, .experiment_id
to /runtime inside the container (backed by .runtime/ on host) so the LLM
cannot see them under /workspace/results/.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Step 9: Test with Qwen 3.5

Submit a test job with a small local model:

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia

# Use the qwen3.5:9b config
sbatch --wrap="cd $(pwd) && ./exec_apptainer_harmonia.sh \
    --config experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_qwen3.5-9b.yaml" \
    --partition=gpu --gpus-per-node=1 --time=01:00:00 --mem=32G --cpus-per-task=4 \
    --account=compgen --job-name=test_isolation \
    --output=logs/test_isolation_%j.out --error=logs/test_isolation_%j.err
```

**Verification checklist (check the SLURM .out log):**

1. Workspace tree should show ONLY:
   ```
   /workspace
   /workspace/data
   /workspace/data/dou.csv
   /workspace/results
   ```
   - NO `gold_standard/`, `papers/`, `other/`, `ten_metadata_tables_harmonize/`, etc.
   - NO `.beaker_runtime`, `.jupyter_runtime`, `.ipython`, `.experiment_id` under results

2. The experiment should still start (Beaker server ready, kernel started, context switch to bdikit_context).

3. On the host, `results/<experiment_dir>/` should contain:
   ```
   .runtime/
     jupyter/
     beaker/
     ipython/
     cache/huggingface/
     .experiment_id
   ```

4. The LLM should be able to read `/workspace/data/dou.csv` (check conversation output or trace.json).

### Step 10: Update codebase description

Per CLAUDE.md, after significant code changes, update `documentation/codebase_descriptions/`. Check if today's file (`how_this_codebase_works_09_03_2026.md`) exists; if so, add a section about the data isolation changes. If the date has changed, create a new file following the naming convention.

---

## Files to Modify

| File | What to change |
|------|----------------|
| `exec_apptainer_harmonia.sh` | Lines 185-192: runtime mkdir. Lines 336,354: .experiment_id path. Lines 980-984: data bind mount → per-file. Lines ~986-999: example paths echo. Lines 1092-1095: runtime env vars → /runtime. Lines 1101-1102: HF cache env vars → /runtime. |
| `experiments/.../configs/automated/*.yaml` (38 files) | Add `data` section; replace path in messages |
| `experiments/.../configs/manual/*.yaml` (13 files) | Add `data` section |
| `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` | Lines 229, 422: find `.experiment_id` in `.runtime/` with fallback |
| `src/evaluation/visualization/normalize.py` | Lines 51, 55: find `.experiment_id` in `.runtime/` with fallback |
| `calculate_metrics.py` | Line 102: find `.experiment_id` in `.runtime/` with fallback |

## Files to NOT Modify

| File | Reason |
|------|--------|
| `harmonia_beaker_LLM_agent_environment_apptainer.def` | Container image doesn't need changes — bind-mount change only |
| `build_harmonia_apptainer.sh` | Builds image, unrelated |
| `run_experiment.py` | Connects to Beaker via WebSocket, doesn't touch mounts |
| `generate_env.py` | Generates .env from config, doesn't handle `data` section |
| `src/automation/runner.py` | Sends messages to Beaker, doesn't control mounts |
| `sbatch_template.sh` / `sbatch_template_gpu.sh` | Call exec script, don't handle mounts directly |

## Decisions (No Open Questions)

1. **No backward compatibility for configs.** Configs without `data` section fail with a descriptive error. All existing runs used the insecure mount so results should be evaluated knowing the LLM could have seen gold standards.
2. **`.experiment_id` moves to `.runtime/`.** Three reader scripts updated with fallback to old location (for reading old results).
3. **Manual experiments** also get the `data` section — same isolation applies.
4. **Multiple input files** are supported — add more entries to `data.files`.
5. **Configless exec** (bare `./exec_apptainer_harmonia.sh` without `--config`) still mounts full dir — this is only used for quick manual debugging, not experiments.
