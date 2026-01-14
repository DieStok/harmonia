# Bug Fixing Implementation Summary

## Date: 2026-01-14

---

## 1. Fixes Required (from Initial Plan)

### P0 - Critical
| Issue | Description | Priority |
|-------|-------------|----------|
| LLM Config Not Applied | Beaker used default OpenRouter model instead of config-specified model | P0 |
| Context Not Set | /contexts/bdikit_context/sessions returned 404, tools disabled | P0 |

### P1 - High
| Issue | Description | Priority |
|-------|-------------|----------|
| Ollama Race Condition | Multiple jobs on same node failed to share Ollama server | P1 |
| Server Disconnected | httpcore.RemoteProtocolError on Ollama connections | P1 |

### P2 - Medium
| Issue | Description | Priority |
|-------|-------------|----------|
| Materialization Timeout | Turn 4 consistently timed out | P2 |
| XSRF Token Error | 403/405 on POST /notebook | P2 |

### P3 - Low
| Issue | Description | Priority |
|-------|-------------|----------|
| Model Name Mismatch | devstral-small:24b, olmo3:32b not found | P3 |
| Model Tool Support | kimi-k2:free doesn't support tools | P3 |

---

## 2. What Was Implemented and Where

### File: `src/automation/client.py`
**Changes:**
- Added `_set_context_magic()` method to set Beaker context via execute_request with magic command `%set_context`
- Added `_set_context_rest()` method as alternative REST-based context setting
- Added `_find_context()` helper method to discover available contexts
- Added `_get_xsrf_cookie()` method to fetch XSRF token from server
- Modified `connect()` to call `_set_context_magic()` after WebSocket connection
- Modified `save_notebook()` to include X-XSRFToken header
- Refactored `_get_or_create_session()` to return context slug for later setting

**Key Code Addition:**
```python
async def _set_context_magic(self, context_slug: str) -> None:
    """Set the Beaker context via execute_request with magic command."""
    magic_code = f"%set_context {context_slug} python3 {{}}"
    msg = self._make_message("execute_request", {
        "code": magic_code,
        "silent": False,
        ...
    })
    await self.ws.send_json(msg)
```

### File: `sbatch_template_gpu.sh`
**Changes:**
- Added Ollama health check loop (60s timeout)
- Added model pre-loading before experiment starts
- Added pip install of bdikit_context package in container
- Added LLM_SERVICE_PROVIDER and LLM_SERVICE_MODEL env vars to apptainer exec

**Key Code Addition:**
```bash
# Wait for Ollama to respond
OLLAMA_READY=0
for i in {1..60}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        OLLAMA_READY=1
        break
    fi
    sleep 1
done

# Pre-warm the model
curl -s http://localhost:11434/api/generate -d '{"model": "{{llm_model}}", "prompt": "Hello"}' ...
```

### File: `sbatch_template.sh`
**Changes:**
- Added pip install of bdikit_context package in container
- Added LLM_SERVICE_PROVIDER and LLM_SERVICE_MODEL env vars to apptainer exec

### File: `generate_jobs.py`
**Changes:**
- Added extraction of LLM provider and model from config
- Added `{{llm_provider}}` and `{{llm_model}}` template variable replacements

### File: `start_ollama.sh` (in ollama directory)
**Changes:**
- Added pre-start port check for multi-job node sharing
- Added post-failure port check for race condition handling
- Changed exit code from 1 to 0 when server already running
- Added OLLAMA_PORT variable extraction

### File: `experiments/configs/dou_harmonization_kimi-k2.yaml`
**Changes:**
- Changed model from `moonshotai/kimi-k2:free` to `qwen/qwen-2.5-72b-instruct:free` (tool support)

### File: `experiments/configs/*.yaml` (8 files)
**Changes:**
- Increased materialization timeout from 120-180s to 600s

### File: `experiments/configs/dou_harmonization_devstral.yaml`
**Changes:**
- Changed model from `devstral:123b` to `devstral:latest`

### File: `experiments/configs/dou_harmonization_devstral-small.yaml`
**Changes:**
- Changed model from `devstral-small:24b` to `devstral-small-2:latest`

### Ollama Models Downloaded:
- `devstral:latest` (14 GB)
- `devstral-small-2:latest` (15 GB)
- `olmo-3:latest` (4.5 GB)

---

## 3. Errors/Fixes Still Remaining

### CRITICAL: Context Tools Still Not Working

**Status:** Partially fixed, but subkernel doesn't have bdi-kit tools

**Evidence from logs:**
```
Switching from context default to bdikit_context...
Context switch complete.
Context 'bdikit_context' set successfully
...
Context has no workflows: disabling tools.
```

**Root Cause:**
- The context switch works at the Beaker kernel level
- However, a new Python subkernel is started for the context
- The subkernel doesn't have the BDIKitAgent and tools registered
- The bdikit_context package needs to be properly installed and registered BEFORE Beaker starts

**Hypothesis:**
- The `pip install -e /jupyter` runs but doesn't complete before Beaker starts
- OR the package installs but Beaker doesn't pick up the new context at runtime
- Beaker contexts are discovered at startup time, not dynamically

**Proposed Fix:**
1. Build a custom Apptainer image with bdikit_context pre-installed
2. OR run pip install BEFORE starting Beaker (sequentially, not in same bash command)

### MEDIUM: Notebook Save Returns 405

**Status:** Not fixed

**Evidence:**
```
405 POST /notebook?token=... (Method Not Allowed)
```

**Root Cause:**
- The `/notebook` endpoint doesn't accept POST requests
- This is a Beaker API design issue - the endpoint may only support GET

**Impact:**
- Notebooks not visible in UI during experiment
- Doesn't affect experiment execution

### LOW: LLM Responses Empty for Ollama Models

**Status:** Partially diagnosed

**Evidence:**
- All Ollama experiments complete but with empty agent responses
- Errors in stderr show Ollama connection issues (RemoteProtocolError)

**Root Cause:**
- olmo-3 model may not be responding properly
- Context tools not available, so agent can't use harmonization functions

---

## 4. Test Results Summary

| Test | Result | Notes |
|------|--------|-------|
| Ollama health check | ✅ Working | Responds within 2s |
| Model pre-loading | ✅ Working | Model preloaded successfully |
| Context switching | ✅ Working | "Context switch complete" |
| Context tools | ❌ Not working | "disabling tools" still appears |
| LLM config override | ✅ Working | Correct model in logs |
| Notebook save | ❌ 405 error | Method not allowed |
| Experiment completion | ✅ Working | Jobs complete without crash |

---

## 5. Recommended Next Steps

### Immediate (Critical Path):

1. **Build custom Apptainer image with bdikit_context pre-installed:**
   ```bash
   # In Dockerfile or Apptainer def:
   RUN pip install -e /path/to/harmonia
   ```

2. **Alternative: Sequential pip install in sbatch:**
   ```bash
   # Run pip install first, wait, then start Beaker
   apptainer exec ... pip install -e /jupyter
   sleep 5  # Wait for install
   apptainer exec ... beaker dev watch ...
   ```

3. **Test with a model known to work well:**
   - Try `qwen3-coder:30b` instead of `olmo-3:latest`
   - Larger models may handle the context better

### Later:

4. **Fix notebook save endpoint:**
   - Investigate Beaker's notebook API
   - May need different endpoint or HTTP method

5. **Add better error handling:**
   - Catch empty LLM responses and retry
   - Log more details about Ollama connection state

---

## 6. Files Modified (Complete List)

| File | Type | Change Summary |
|------|------|----------------|
| `src/automation/client.py` | Python | Context setting via magic command |
| `sbatch_template_gpu.sh` | Bash | Health checks, model preload, pip install |
| `sbatch_template.sh` | Bash | Pip install, LLM config vars |
| `generate_jobs.py` | Python | LLM config extraction |
| `start_ollama.sh` | Bash | Race condition handling |
| `dou_harmonization_kimi-k2.yaml` | YAML | Model change (tool support) |
| `dou_harmonization_devstral.yaml` | YAML | Model name fix |
| `dou_harmonization_devstral-small.yaml` | YAML | Model name fix |
| `dou_harmonization_*.yaml` (8 files) | YAML | Timeout increase |
| `bug_fixing_v3_detailed_analysis.md` | Markdown | Error analysis |
| `bug_fixing_experiment_ollama_openrouter_v2.md` | Markdown | Fix plan v2 |
