# Bug Fixing Analysis V2: Ollama/OpenRouter Experiments

## Overview

This document analyzes the issues found in the first batch of dou_harmonization experiments and documents the fixes applied. It also identifies remaining issues that need to be addressed before re-running experiments.

---

## Summary of First Run Results

| Experiment | Model | Node | Status | Turns Completed | Issues |
|------------|-------|------|--------|-----------------|--------|
| dou_harmonization_kimi-k2 | openrouter/kimi-k2:free | - | COMPLETED | 3/4 | Turn 4 timeout |
| dou_harmonization_glm-4.5-air | openrouter/glm-4.5-air:free | - | COMPLETED | 3/4 | Turn 4 timeout |
| dou_harmonization_mimo-v2-flash | openrouter/mimo-v2-flash:free | - | COMPLETED | 3/4 | Turn 4 timeout |
| dou_harmonization_devstral | ollama/devstral:123b | n0098 | COMPLETED | 3/4 | Used OpenRouter fallback |
| dou_harmonization_devstral-small | ollama/devstral-small:24b | n0098 | COMPLETED | 3/4 | Used OpenRouter fallback |
| dou_harmonization_nemotron-3-nano | ollama/nemotron-3-nano:30b | n0108 | COMPLETED | 3/4 | Used OpenRouter fallback |
| dou_harmonization_olmo3 | ollama/olmo3:32b | n0108 | COMPLETED | 3/4 | Used OpenRouter fallback |
| dou_harmonization_qwen3-coder | ollama/qwen3-coder:30b | n0108 | COMPLETED | 2/4 | Used OpenRouter fallback |

**Key Finding**: ALL Ollama experiments used the OpenRouter fallback model (xiaomi/mimo-v2-flash:free) instead of the configured Ollama models because the LLM config was not being passed to Beaker.

---

## Issues Found and Fixed

### 1. XSRF Token Missing on POST /notebook [FIXED]

**Location**: `src/automation/client.py:300-307`

**Issue**: The `save_notebook()` and `get_notebook()` methods made POST/GET requests without XSRF tokens.

**Error**:
```
403 POST /notebook (127.0.0.1): '_xsrf' argument missing from POST
```

**Fix Applied**: Added `?token={self.token}` to URLs in both methods to bypass XSRF protection.

```python
# Before:
url = f"{self.server_url}/notebook"

# After:
url = f"{self.server_url}/notebook?token={self.token}"
```

**Status**: FIXED

---

### 2. Context Not Set for bdi-kit [FIXED]

**Location**: `src/automation/client.py:77-132`

**Issue**: The `/api/sessions/create-with-context` endpoint returned 404. Sessions were created without the bdi-kit context.

**Error**:
```
404 POST /api/sessions/create-with-context
Context has no workflows: disabling tools.
```

**Fix Applied**:
- Removed broken endpoint attempt
- Added `_set_context()` method to set context after session creation
- Modified `_get_or_create_session()` to call `_set_context()` with bdi-kit context

```python
async def _set_context(self, context_slug: str) -> None:
    """Set the Beaker context for the kernel session."""
    url = f"{self.server_url}/contexts/{context_slug}/sessions/{self.session_id}?token={self.token}"
    async with self.session.post(url) as resp:
        if resp.status not in (200, 201, 204):
            print(f"  Warning: Could not set context '{context_slug}': {resp.status}")
```

**Status**: FIXED

---

### 3. LLM Config Not Applied to Beaker [FIXED - CRITICAL]

**Location**: `sbatch_template_gpu.sh`, `sbatch_template.sh`, `generate_jobs.py`

**Issue**: Experiment config specified `llm.provider` and `llm.model`, but Beaker used the .env default (OpenRouter/mimo-v2-flash) for ALL experiments.

**Evidence**:
```
Unrecognized OpenRouter model: 'xiaomi/mimo-v2-flash:free'
```
This appeared in ALL Ollama job logs, proving they used OpenRouter instead of Ollama.

**Impact**: All Ollama experiments were actually running with OpenRouter, not local models.

**Fix Applied**:
1. Updated `sbatch_template_gpu.sh` and `sbatch_template.sh` to add:
   ```bash
   --env LLM_SERVICE_PROVIDER={{llm_provider}} \
   --env LLM_SERVICE_MODEL={{llm_model}} \
   ```

2. Updated `generate_jobs.py` to extract LLM config and pass to templates:
   ```python
   llm_provider = config.llm.provider
   llm_model = config.llm.model

   replacements = {
       "{{llm_provider}}": llm_provider,
       "{{llm_model}}": llm_model,
   }
   ```

**Note**: Apptainer `--env` flags override values from `--env-file`, so this should work correctly.

**Status**: FIXED

---

### 4. Ollama Race Condition on Multi-Job Nodes [FIXED]

**Location**: `/hpc/compgen/projects/ollama/ollama_run/analysis/dstoker/start_ollama.sh`

**Issue**: When multiple GPU jobs ran on the same node, they all tried to start Ollama on port 11434. Only one succeeded; others failed.

**Evidence**:
- n0098: devstral started Ollama, devstral-small detected "already running" (correct)
- n0108: olmo3 started Ollama, nemotron and qwen3-coder got "Failed to start" (race condition)

**Fix Applied**:
1. Added pre-start port check:
   ```bash
   # Check if port is already in use (another job on same node started Ollama)
   OLLAMA_PORT=$(echo "$OLLAMA_HOST" | cut -d':' -f2)
   if ss -tlnp 2>/dev/null | grep -q ":${OLLAMA_PORT} "; then
       echo "Ollama server already running on this node (port $OLLAMA_PORT in use)"
       exit 0  # Success - server is available
   fi
   ```

2. Added post-fail port check (race condition fallback):
   ```bash
   if ! kill -0 $OLLAMA_PID 2>/dev/null; then
       # Check if port is now occupied (race condition)
       if ss -tlnp 2>/dev/null | grep -q ":${OLLAMA_PORT} "; then
           echo "Ollama server running on this node (started by another job)"
           rm -f "$PID_FILE"
           exit 0  # Success - server is available
       fi
       ...
   fi
   ```

3. Changed exit code from 1 to 0 when server is already running.

**Status**: FIXED

---

### 5. Materialization Timeout [FIXED]

**Issue**: Turn 4 (materialization) consistently timed out at 60-120 seconds.

**Fix Applied**: Increased `wait_seconds` for materialization turn from 120-180 to 600 seconds in all config files.

**Configs Updated**:
- `dou_harmonization_mimo-v2-flash.yaml`
- `dou_harmonization_glm-4.5-air.yaml`
- `dou_harmonization_kimi-k2.yaml`
- `dou_harmonization_nemotron-3-nano.yaml`
- `dou_harmonization_devstral-small.yaml`
- `dou_harmonization_devstral.yaml`
- `dou_harmonization_qwen3-coder.yaml`
- `dou_harmonization_olmo3.yaml`

**Status**: FIXED

---

### 6. Missing Ollama Models [NEEDS ACTION]

**Issue**: Some models were not downloaded or have incorrect names.

**Downloaded Models** (confirmed in ollama_models/manifests):
- `gemma3` (latest)
- `gpt-oss` (20b)
- `nemotron-3-nano` (30b - note: no :30b tag in directory)
- `qwen3-coder` (30b - note: no :30b tag in directory)

**Missing Models**:
- `devstral:123b` - Not downloaded
- `devstral-small:24b` - Not downloaded (also check correct name)
- `olmo3:32b` - Not downloaded

**Action Required**:
1. Start interactive GPU session
2. Start Ollama server
3. Pull missing models:
   ```bash
   ollama pull devstral:latest      # Check if :123b exists
   ollama pull devstral-small:24b   # Or just devstral-small
   ollama pull olmo3:32b            # Or just olmo3
   ```
4. Verify model names match config files

**Status**: NEEDS ACTION

---

## Remaining Issues

### 1. Model Name Verification

The config files use specific tags (e.g., `devstral:123b`, `olmo3:32b`) but Ollama may use different naming. Need to verify:
- Check available model tags on ollama.com
- Update configs if model names are incorrect
- Or pull models with exact names from configs

### 2. Default Timeout in Runner

The log shows `timeout (60.0s)` even when config specifies 180s. Check if `run_experiment.py` or `client.py` has a default timeout that overrides config values.

**Location to check**: `src/automation/runner.py` - verify `wait_seconds` from config is actually used.

### 3. Test LLM Config Override

Need to verify the `--env` flags actually override `--env-file` values. Check `exec_apptainer.sh` to confirm precedence.

---

## Re-Run Checklist

Before re-running experiments:

- [x] XSRF token fix applied
- [x] Context setting fix applied
- [x] LLM config passing fix applied
- [x] Ollama race condition fix applied
- [x] Timeout increase applied
- [ ] Download missing Ollama models
- [ ] Verify model names in configs match actual Ollama model names
- [ ] Regenerate job scripts with new templates
- [ ] Re-submit jobs

---

## Commands for Re-Run

### 1. Download Missing Models (on GPU node)

```bash
srun -J ollama_models_claude-code --partition=gpu --gpus-per-node=1 --mem=40G --time=01:00:00 bash

# Start Ollama
cd /hpc/compgen/projects/ollama/ollama_run/analysis/dstoker
./start_ollama.sh

# Pull models (verify exact names first)
ollama pull devstral
ollama pull olmo3

# List to verify
ollama list
```

### 2. Regenerate Job Scripts

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia

# CPU jobs (OpenRouter)
python generate_jobs.py -c experiments/configs/dou_harmonization_mimo-v2-flash.yaml --time 02:00:00 --memory 20G
python generate_jobs.py -c experiments/configs/dou_harmonization_glm-4.5-air.yaml --time 02:00:00 --memory 20G
python generate_jobs.py -c experiments/configs/dou_harmonization_kimi-k2.yaml --time 02:00:00 --memory 20G

# GPU jobs (Ollama)
python generate_jobs.py -c experiments/configs/dou_harmonization_nemotron-3-nano.yaml --time 02:00:00 --memory 80G --gpu
python generate_jobs.py -c experiments/configs/dou_harmonization_devstral-small.yaml --time 02:00:00 --memory 60G --gpu
python generate_jobs.py -c experiments/configs/dou_harmonization_devstral.yaml --time 02:00:00 --memory 300G --gpu
python generate_jobs.py -c experiments/configs/dou_harmonization_qwen3-coder.yaml --time 02:00:00 --memory 80G --gpu
python generate_jobs.py -c experiments/configs/dou_harmonization_olmo3.yaml --time 02:00:00 --memory 80G --gpu
```

### 3. Submit Jobs

```bash
for job in jobs/dou_harmonization_*.sh; do
    sbatch "$job"
done
```

---

## Files Modified in This Fix Cycle

| File | Change |
|------|--------|
| `src/automation/client.py` | XSRF token fix, context setting fix |
| `sbatch_template_gpu.sh` | LLM config env vars |
| `sbatch_template.sh` | LLM config env vars |
| `generate_jobs.py` | Extract and pass LLM config |
| `start_ollama.sh` | Race condition fix with port checking |
| `experiments/configs/*.yaml` (8 files) | Increased materialization timeout to 600s |

---

## Expected Improvements in V2 Run

1. **Ollama jobs will use correct models**: LLM_SERVICE_PROVIDER and LLM_SERVICE_MODEL env vars now passed to Beaker
2. **No Ollama start failures**: Race condition fix allows multiple jobs to share Ollama server
3. **Materialization will complete**: 600s timeout should be sufficient
4. **Notebook sync will work**: XSRF token fix enables notebook saves
5. **bdi-kit tools available**: Context setting enables harmonization workflows

---

## Monitoring Commands

```bash
# Check job status
squeue -u $USER

# Watch jobs
watch -n 30 'squeue -u $USER'

# Check recent job history
sacct -u $USER --starttime=today

# View job output in real-time
tail -f logs/dou_harmonization_*.out
```
