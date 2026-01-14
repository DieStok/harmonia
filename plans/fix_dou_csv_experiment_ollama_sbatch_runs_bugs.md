# Fix Plan: Dou CSV Experiment Ollama/Sbatch Bugs

## Summary of Experiments Run

| Experiment | Model | Status | Result |
|------------|-------|--------|--------|
| dou_harmonization_kimi-k2 | openrouter/moonshotai/kimi-k2:free | COMPLETED | Success, Turn 4 timeout |
| dou_harmonization_devstral | ollama/devstral:123b | COMPLETED | Partial, empty responses |
| dou_harmonization_glm-4.5-air | openrouter/z-ai/glm-4.5-air:free | RUNNING | - |
| dou_harmonization_mimo-v2-flash | openrouter/xiaomi/mimo-v2-flash:free | RUNNING | - |
| dou_harmonization_devstral-small | ollama/devstral-small:24b | RUNNING | Model not found |
| dou_harmonization_nemotron-3-nano | ollama/nemotron-3-nano:30b | RUNNING | Ollama start failed |
| dou_harmonization_olmo3 | ollama/olmo3:32b | RUNNING | - |
| dou_harmonization_qwen3-coder | ollama/qwen3-coder:30b | RUNNING | Ollama start failed |

---

## Issues Found

### 1. XSRF Token Missing on POST /notebook

**Location**: `src/automation/client.py:300-307`

**Issue**: The `save_notebook()` method makes POST requests without XSRF tokens. Jupyter server requires XSRF protection by default.

**Error**:
```
403 POST /notebook (127.0.0.1): '_xsrf' argument missing from POST
```

**Impact**: Non-critical - notebook sync fails but experiments continue

**Fix Options**:
1. Disable XSRF in Beaker server config (`--ServerApp.disable_check_xsrf=True`)
2. Fetch XSRF cookie and include in requests
3. Use token-authenticated requests which bypass XSRF

**Recommended**: Option 3 - add `?token={self.token}` to POST requests

### 2. Ollama Race Condition on Multi-Job Nodes

**Location**: `start_ollama.sh` and `sbatch_template_gpu.sh`

**Issue**: When multiple GPU jobs run on the same node, they all try to start Ollama on port 11434 simultaneously. Only one succeeds.

**Evidence**:
- n0098: devstral started Ollama, devstral-small detected "already running" (correct)
- n0108: olmo3 started Ollama, nemotron and qwen3-coder got "Failed to start" (race condition)

**Fix Options**:
1. Use file locking in start_ollama.sh to serialize start attempts
2. Check if port 11434 is in use before attempting start
3. Wait and retry if server fails to start but port is occupied
4. Use per-job Ollama ports (complex)

**Recommended**: Option 3 - add retry logic with port checking

```bash
# After failed start, check if port is occupied
if ! kill -0 $OLLAMA_PID 2>/dev/null; then
    # Check if port 11434 is in use (another job started it)
    if ss -tlnp | grep -q ":11434"; then
        echo "Ollama server running on this node (started by another job)"
        exit 0  # Exit with success, server is available
    fi
    echo "ERROR: Failed to start server. Check ollama_serve.log"
    rm -f "$PID_FILE"
    exit 1
fi
```

### 3. LLM Config Not Applied to Beaker Session

**Location**: `src/automation/runner.py` and Beaker kernel initialization

**Issue**: The experiment config specifies `llm.provider` and `llm.model`, but these are only logged. The actual LLM used is whatever Beaker's .env or container config specifies.

**Evidence**:
```
Unrecognized OpenRouter model: 'xiaomi/mimo-v2-flash:free'
```
This appears even in Ollama jobs, showing the .env default is used.

**Impact**: Critical for Ollama jobs - they use OpenRouter instead of Ollama!

**Fix Options**:
1. Pass LLM config to Beaker via kernel message
2. Set environment variables before starting Beaker
3. Create per-experiment .env files
4. Modify sbatch template to set LLM_PROVIDER/LLM_MODEL env vars

**Recommended**: Option 4 - modify sbatch template to export LLM config

```bash
# In sbatch_template_gpu.sh, before starting Beaker:
export LLM_PROVIDER="{{llm_provider}}"
export LLM_MODEL="{{llm_model}}"
export LLM_BASE_URL="{{llm_base_url}}"
```

And add these template variables to generate_jobs.py.

Do check that this works: exec_apptainer.sh passes the env vars in the .env file into the container: does this overwrite the ones sbatch sets or not?

### 4. Timeout on Materialization Turn

**Issue**: Turn 4 ("Materialize the mapping...") consistently times out at 120 seconds.

**Evidence**:
```
**Agent** (timeout):
Request timed out after 120.0 seconds
```

**Impact**: Medium - experiments complete but miss final results

**Fix Options**:
1. Increase default timeout
2. Increase per-message timeout in config
3. Break materialization into smaller steps

**Recommended**: Increase wait_seconds in config for Turn 4:
```yaml
- content: |
    Materialize the mapping and show me the harmonized dataframe.
    Also show the mapping summary.
  wait_seconds: 300  # Increase from 180 to 300
```

### 5. Model Download Failures

**Issue**: Some Ollama models failed to download:
- devstral-small:24b - "file does not exist" error
- olmo3:32b - may not have downloaded (verifying took too long)

**Evidence**:
```
Error: pull model manifest: file does not exist
```

**Impact**: Critical for devstral-small job

**Fix**:
1. Verify correct model names at ollama.com
2. Re-run downloads with corrected names:
   - Try `devstral-small` without version tag
   - Try `olmo3` without version tag
3. Check for network/timeout issues during download

### 6. API Endpoint 404

**Issue**: `/api/sessions/create-with-context` returns 404

**Location**: `src/automation/client.py:119-123`

**Impact**: Non-critical - falls back to standard session creation

**Fix**: Check Beaker version compatibility or remove custom endpoint attempt

---

## Priority Order

1. **P0 - LLM Config Not Applied**: Ollama jobs use wrong model - BLOCKING
2. **P1 - Ollama Race Condition**: Jobs fail on shared nodes - HIGH IMPACT
3. **P1 - Model Downloads**: Missing models - HIGH IMPACT
4. **P2 - Materialization Timeout**: Final results missing - MEDIUM
5. **P3 - XSRF Token**: Non-critical, experiments run fine
6. **P3 - API 404**: Non-critical, has fallback

---

## Next Steps

1. Fix sbatch templates to pass LLM config via environment variables
2. Update start_ollama.sh with port-checking retry logic
3. Re-run model downloads for devstral-small and olmo3
4. Increase timeout for materialization turn in configs
5. Re-run experiments after fixes

---

## Files to Modify

| File | Change |
|------|--------|
| `sbatch_template_gpu.sh` | Add LLM_PROVIDER, LLM_MODEL env exports |
| `generate_jobs.py` | Parse LLM config and pass to template |
| `start_ollama.sh` | Add port-checking retry logic |
| `experiments/configs/*.yaml` | Increase Turn 4 timeout |
| Model downloads | Re-run with correct names |
