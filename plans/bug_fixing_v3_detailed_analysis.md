# Bug Fixing Analysis V3: Complete Error Analysis and Fix Plan

## Executive Summary

After running experiments and analyzing logs from job batch 45323912-45323919, I identified 5 distinct error classes affecting the experiments. This document provides detailed root cause analysis, hypotheses, and step-by-step fixes for each error class.

---

## Error Classes Overview

| Error Class | Severity | Affected Jobs | Impact |
|-------------|----------|---------------|--------|
| E1: XSRF Token Still Failing | Medium | ALL | Notebook sync fails, experiments continue |
| E2: Context Setting 404 | Critical | ALL | bdi-kit tools unavailable |
| E3: Model Does Not Support Tools | Critical | kimi-k2 | Complete failure |
| E4: Context Has No Workflows | Critical | Ollama jobs | Tools disabled |
| E5: Server Disconnected | High | qwen3-coder | Connection errors |

---

## Error Class 1: XSRF Token Still Failing

### Evidence
```
[W] 403 POST /notebook?token=89f73481102c46c0bc13b2998f9a4fce (127.0.0.1): '_xsrf' argument missing from POST
```

### Impact
- Notebook saving fails (initial and final)
- Experiments still complete but no notebook sync for UI visibility

### Hypotheses

1. **Beaker's /notebook endpoint requires XSRF cookie, not just token in URL**
   - Jupyter's XSRF protection may require both token and _xsrf cookie
   - The token bypass only works for some endpoints

2. **Token format mismatch**
   - Beaker may expect token in a different format/header
   - POST requests need different authentication than GET

3. **Beaker notebook extension has custom XSRF handling**
   - The `/notebook` endpoint is provided by `beaker_kernel.service.notebook`
   - It may have different XSRF requirements than standard Jupyter

### Fix Location
- `src/automation/client.py:279-309` (save_notebook method)

### Proposed Fix
Add `_xsrf` as a form parameter or fetch the XSRF cookie first:

```python
async def save_notebook(self, cells: list[dict], name: str = "experiment") -> dict:
    # Get XSRF cookie by making a GET request first
    async with self.session.get(f"{self.server_url}/") as resp:
        xsrf_cookie = resp.cookies.get('_xsrf')

    # Include _xsrf in both URL and form data
    url = f"{self.server_url}/notebook?token={self.token}"
    data = {
        "content": notebook_content,
        "session": self.session_id,
        "name": name,
        "_xsrf": xsrf_cookie.value if xsrf_cookie else ""
    }
```

### Expected Behavior After Fix
- POST /notebook returns 200/201
- Notebook visible in Beaker UI during experiment

### Test
```bash
# Run a single experiment and check logs for:
# - No 403 errors on /notebook
# - "Notebook saved" message in stdout
```

---

## Error Class 2: Context Setting Returns 404

### Evidence
```
[W] 404 POST /contexts/bdikit_context/sessions/{session_id}?token=[secret]
Warning: Could not set context 'bdikit_context': 404
```

### Impact
- bdi-kit tools (match_schema, materialize_mapping, etc.) unavailable
- LLM cannot perform harmonization tasks
- Experiments produce generic responses, not harmonization results

### Hypotheses

1. **bdikit_context package not installed in Jupyter container**
   - The package exists in local project but isn't in the Apptainer image
   - Beaker can't find the context because it's not registered

2. **Context endpoint URL is incorrect**
   - Beaker may use a different URL format for setting context
   - The session ID may not be the correct identifier

3. **Context needs to be set via WebSocket message, not REST API**
   - Beaker may use a Jupyter protocol message like `set_context`
   - REST endpoint only lists contexts, doesn't set them

### Fix Location
- Container configuration (jupyter.sif or bind mounts)
- `src/automation/client.py:134-144` (_set_context method)

### Proposed Fix

**Option A: Install bdikit_context in container**
```bash
# In sbatch template, before starting Beaker:
pip install -e /jupyter/src/bdikit_context
```

**Option B: Use WebSocket set_context message (more likely correct)**
```python
async def _set_context(self, context_slug: str) -> None:
    """Set context via WebSocket message instead of REST API."""
    # Wait for WebSocket connection
    if self.ws is None:
        return

    msg = self._make_message("set_context", {
        "context": context_slug,
        "payload": {}
    })
    await self.ws.send_json(msg)

    # Wait for confirmation
    async for response in self._receive_until_complete(msg["header"]["msg_id"], 30):
        if response.get("msg_type") == "status":
            if response.get("content", {}).get("execution_state") == "idle":
                break
```

### Expected Behavior After Fix
- `Context has no workflows: disabling tools` message disappears
- bdi-kit tools available for harmonization

### Test
```bash
# Check stderr for:
# - No 404 on /contexts/bdikit_context/sessions
# - No "Context has no workflows" message
# - "Tools enabled" or similar message
```

---

## Error Class 3: Model Does Not Support Tools

### Evidence
```
ValueError: OpenRouter model 'moonshotai/kimi-k2:free' does not support tools.
Archytas requires models to support tools.
```

### Impact
- Complete experiment failure for kimi-k2
- No LLM responses generated

### Hypotheses

1. **Model selection is incorrect for free tier**
   - kimi-k2:free may not have tool calling capability
   - Need to check OpenRouter model capabilities

2. **Archytas/toki model list is outdated**
   - Model capabilities may have changed since toki was built
   - Need to update model attributes

3. **Should fall back to non-tool mode**
   - Some experiments don't need tools
   - Could use prompt-based approach instead

### Fix Location
- `experiments/configs/dou_harmonization_kimi-k2.yaml`
- Or skip kimi-k2 experiments entirely

### Proposed Fix
Either:
1. Remove kimi-k2 from experiment configs (use tool-capable models only)
2. Use a different OpenRouter model that supports tools

```yaml
# Option: Use different model
llm:
  provider: openrouter
  model: qwen/qwen-2.5-72b-instruct:free  # Supports tools
```

### Expected Behavior After Fix
- No tool support errors
- Experiment completes with tool calls

### Test
```bash
# Check stderr for:
# - No "does not support tools" error
# - Tool calls visible in logs
```

---

## Error Class 4: Context Has No Workflows (Tools Disabled)

### Evidence
```
Context has no workflows: disabling tools.
```

### Impact
- This is the consequence of E2 (context not set)
- LLM operates without bdi-kit tools
- Generic responses instead of harmonization

### Root Cause
- Related to E2 - context wasn't set properly
- When context is `None` or default, no tools are registered

### Fix
- Same as E2: Fix context setting

---

## Error Class 5: Server Disconnected

### Evidence
```
httpcore.RemoteProtocolError: Server disconnected without sending a response.
```

### Impact
- Ollama connection failed mid-request
- Experiment fails or produces partial results

### Hypotheses

1. **Ollama server overloaded or crashed**
   - Multiple jobs sharing same Ollama instance
   - Model too large for available GPU memory

2. **Network timeout between container and Ollama**
   - Ollama on host, Beaker in container
   - Port forwarding or network issue

3. **Model loading timeout**
   - First request to Ollama triggers model load
   - Takes longer than HTTP timeout

### Fix Location
- `sbatch_template_gpu.sh` - Ollama wait time
- Ollama configuration

### Proposed Fix
1. Increase Ollama startup wait time:
```bash
# Wait longer for Ollama to be ready
sleep 60  # Instead of 30
```

2. Add health check before starting experiment:
```bash
# Wait for Ollama to respond
for i in {1..30}; do
    curl -s http://localhost:11434/api/tags && break
    sleep 2
done
```

3. Pre-load model before experiment:
```bash
# Warm up the model
curl http://localhost:11434/api/generate -d '{"model": "devstral:latest", "prompt": "test", "stream": false}'
```

### Expected Behavior After Fix
- No "Server disconnected" errors
- Stable Ollama connections throughout experiment

### Test
```bash
# Check stderr for:
# - No RemoteProtocolError
# - Successful LLM responses
```

---

## Step-by-Step Fix Implementation Plan

### Phase 1: Fix Context Setting (E2, E4) - CRITICAL

**Step 1.1**: Modify client.py to set context via WebSocket
```python
# In _get_or_create_session, after WebSocket is connected
# Move context setting to after WS connection
```

**Step 1.2**: Verify context is available in container
```bash
# Add to sbatch template:
pip install -e /jupyter 2>/dev/null || true
```

### Phase 2: Fix XSRF Token (E1) - MEDIUM

**Step 2.1**: Fetch XSRF cookie before POST requests
**Step 2.2**: Include _xsrf in form data

### Phase 3: Fix Model Compatibility (E3) - LOW

**Step 3.1**: Remove or update kimi-k2 config to use tool-capable model
**Step 3.2**: Add model capability check before experiment

### Phase 4: Fix Ollama Stability (E5) - HIGH

**Step 4.1**: Increase Ollama wait time in sbatch template
**Step 4.2**: Add health check and model warm-up
**Step 4.3**: Consider sequential GPU job submission to avoid resource contention

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/automation/client.py` | Fix XSRF handling, fix context setting |
| `sbatch_template_gpu.sh` | Add pip install, increase wait time, add health check |
| `experiments/configs/dou_harmonization_kimi-k2.yaml` | Change model or remove |

---

## Verification Checklist

After implementing fixes, verify:

- [ ] No 403 errors on /notebook endpoints
- [ ] No 404 errors on /contexts endpoints
- [ ] No "Context has no workflows" message
- [ ] No "does not support tools" errors
- [ ] No "Server disconnected" errors
- [ ] Conversation logs show bdi-kit tool calls
- [ ] Harmonized dataframe produced in results

---

## Next Steps

1. Implement Phase 1 fixes (Context Setting)
2. Regenerate job scripts
3. Run single test job to verify
4. If successful, run full batch
5. Analyze results
