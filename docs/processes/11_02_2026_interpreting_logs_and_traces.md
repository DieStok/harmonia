# Interpreting Harmonia Experiment Logs and Traces: Failure Mode Taxonomy

**Date:** 11 February 2026
**Context:** Analysis of 10 automated experiments run on 10 Feb 2026 (SLURM jobs 46662631-46662640), each using the `dou_harmonization` scenario with different LLM backends.

---

## Overview

Each automated Harmonia experiment produces:
- **SLURM log** (`.out`): stdout from the job script — Beaker server startup, Ollama startup (for local LLMs), experiment runner output, and any Python/infra errors.
- **SLURM error log** (`.err`): stderr — typically empty unless the job itself crashes.
- **trace.json**: Per-run structured record in `results/<experiment_name>_<timestamp>/trace.json` — captures every turn's user message, agent response, response type (llm_response/timeout/error), tool calls, duration, and raw WebSocket messages.
- **metrics.json**: Per-run accuracy metrics in `results/<experiment_name>_<timestamp>/metrics.json` — column mapping accuracy, value mapping accuracy, extra/missing columns.
- **conversation.md**: Human-readable conversation log (monitor mode only).

Log file naming convention: `logs/{DD-MM-YYYY_HHMM}_{experiment_name}_{SLURM_JOB_ID}.out`

Results folder naming: `results/{experiment_name}_{YYYYMMDD_HHMMSS}/`

---

## Failure Mode Categories

### Category 1: Infrastructure / Beaker Server Failures

#### 1A. Beaker Server Hung (All Turns Timeout with Identical Pattern)

**Description:** The Beaker server becomes unresponsive after processing a previous batch of experiment runs. All 8 turns timeout with an identical, deterministic duration pattern `[180, 300, 180, 180, 360, 600, 300, 120]` totaling exactly 2220 seconds. Each turn's `raw_messages` contains only a single `status: busy` message — the Beaker kernel never starts processing.

**Distinguishing signature in trace.json:**
```json
{
  "turn": 1,
  "agent_response": "Request timed out after 180.0 seconds",
  "response_type": "timeout",
  "tool_calls": [],
  "duration_seconds": 180.001,
  "raw_messages": [
    {
      "msg_type": "status",
      "content": { "execution_state": "busy" }
    }
  ]
}
```
- Total duration is exactly ~2220s across all 8 turns
- Only 1 raw_message per turn (a `status` message, no `beaker__execute_input` or `stream` messages)
- ALL turns have `response_type: "timeout"` — not a single LLM response

**Affected experiments (10 Feb 2026):**
- `dou_harmonization_anyllm_devstral_20260210_183626`
- `dou_harmonization_anyllm_openrouter_20260210_183436`
- `dou_harmonization_glm-4.5-air_20260210_183436`
- `dou_harmonization_mimo-v2-flash_20260210_183436`

**Root cause:** The `run_experiment.py` script retries experiments multiple times. After the first run completes, it starts another run against the same Beaker server instance, which has become hung/unresponsive.

**Remediations:**
1. **Restart Beaker between runs:** Modify `run_experiment.py` to restart the Beaker server (or kernel) between experiment runs, rather than reusing a potentially stale server.
2. **Detect hung server:** Before sending turns, send a health-check request (e.g., `GET /api/sessions`). If the server doesn't respond within 10 seconds, abort the run and log it as `infrastructure_failure` rather than consuming 37 minutes of timeouts.
3. **Limit retries per job:** Configure `run_experiment.py` to only attempt one run per Beaker server instance, or implement exponential backoff with server restart between retries.

---

#### 1B. 405 Method Not Allowed on Notebook Save

**Description:** Beaker returns HTTP 405 when attempting to save a notebook. This appears in almost all SLURM `.out` logs as a warning but does not crash the experiment.

**Distinguishing signature in SLURM .out log:**
```
[W 2026-02-10 19:34:33.506 BeakerServerApp] 405 PUT /api/contents/notebook.ipynb ...
```

**Affected experiments:** All 10 experiments.

**Remediations:**
1. **Ignore:** This is a non-fatal warning. Beaker's dev mode tries to auto-save notebooks, but the API doesn't support PUT for this path. Does not affect experiment results.
2. **Suppress in logging:** Configure Beaker's logging level to suppress 405 warnings if they clutter log analysis.
3. **Fix Beaker config:** If notebook saving is desired, configure the correct save endpoint in Beaker's server settings.

---

#### 1C. ZMQ ReadTimeout on Context Cleanup

**Description:** After the experiment completes, the Beaker kernel's cleanup process encounters a ZMQ ReadTimeout when trying to tear down the context. This appears in the SLURM `.out` log at the very end.

**Distinguishing signature in SLURM .out log:**
```
Uncaught exception in ZMQStream callback
Traceback (most recent call last):
  File ".../zmq/eventloop/zmqstream.py", line 565, in _log_error
    f.result()
  File ".../beaker_kernel/lib/jupyter_kernel_proxy.py", line 253, in handler
  ...
  File ".../beaker_kernel/kernel.py", line 550, in llm_request
    result = await task
```

**Affected experiments:** All experiments that complete at least one run.

**Remediations:**
1. **Ignore:** This occurs during cleanup after the experiment finishes and does not affect results.
2. **Graceful shutdown:** Implement a proper shutdown sequence in `run_experiment.py` that sends a kernel shutdown request before disconnecting.
3. **Catch and suppress:** Wrap the Beaker kernel's cleanup handler in a try/except to prevent the uncaught exception log noise.

---

### Category 2: Model Configuration / Availability Errors

#### 2A. Ollama Model Not Found (404)

**Description:** The Ollama API returns HTTP 404 because the requested model name does not match any installed model. The model is either misspelled or not pulled.

**Distinguishing signature in SLURM .out log:**
```
ollama._types.ResponseError: model 'olmo-3.1:32b' not found (status code: 404)
```
File: `logs/10-02-2026_2314_dou_harmonization_olmo3_46662639.out`

**Distinguishing signature in trace.json:**
- Agent responses are empty or contain error text from Beaker
- Often followed by ZMQ exceptions as the kernel tries to process requests with no valid model

**Affected experiments:** `olmo3` (requested `olmo-3.1:32b`, available models were `olmo-3:32b-think` and `olmo-3:7b-instruct`)

**Remediations:**
1. **Fix model name in config YAML:** Change `model: "olmo-3.1:32b"` to `model: "olmo-3:32b-think"` in the experiment config. Verify available models with `ollama list`.
2. **Add model validation to `exec_apptainer_harmonia.sh`:** After Ollama starts and the model list is printed, verify the requested model name exists in the list. Abort early with a clear error if not.
3. **Import custom model:** For models not in the Ollama registry (like OLMo 3.1 32B), create a Modelfile from the HuggingFace GGUF and register it: `ollama create olmo-3.1:32b -f Modelfile` (see https://huggingface.co/allenai/Olmo-3.1-32B-Instruct).

---

#### 2B. Tool Calling Not Supported (ValueError)

**Description:** The LLM framework (Archytas/LangChain) raises a ValueError because the model's Ollama template does not declare tool support. Ollama determines tool support by checking if the model's Go template references `{{ .Tools }}`.

**Distinguishing signature in SLURM .out log:**
```
ValueError: ... does not support tool calling
```
File: `logs/10-02-2026_1934_dou_harmonization_kimi-k2_46662636.out`

**Distinguishing signature in trace.json:**
- All turns have empty `agent_response` or error text
- `tool_calls` array is always empty
- Very short `duration_seconds` (the error is raised immediately)

**Affected experiments:** `kimi-k2`

**Root cause analysis:** Kimi-K2 **does** support tool calling natively (confirmed via HuggingFace docs at `moonshotai/Kimi-K2-Instruct/docs/tool_call_guidance.md`). The issue is that the standard `kimi-k2` Ollama model's template does not include the `{{ .Tools }}` block, so Ollama rejects tool calls.

**Remediations:**
1. **Use community model with tool template:** `ollama pull huihui_ai/kimi-k2` — this variant includes proper `{{ .Tools }}` template blocks.
2. **Create custom Modelfile:** Create a Modelfile that adds the tool calling template:
   ```
   FROM kimi-k2:latest
   TEMPLATE """{{ if .Tools }}<|im_system|>tool_declare<|im_middle|>{{ .Tools }}<|im_end|>{{ end }}..."""
   ```
3. **Check for client-side rejection:** Verify whether the `ValueError` comes from Ollama itself (HTTP 400) or from Archytas/LangChain pre-checking model capabilities. If the latter, add kimi-k2 to an allowlist.

---

#### 2C. Ollama Runner Process Crash (Exit Status 2)

**Description:** The Ollama runner subprocess crashes with exit status 2 during model inference. This is an Ollama-internal error, typically related to model loading or GGUF format issues.

**Distinguishing signature in SLURM .out log:**
```
llama runner process has terminated: exit status 2
```
File: `logs/10-02-2026_2158_dou_harmonization_nemotron-3-nano_46662638.out`

**Affected experiments:** `nemotron-3-nano`

**Remediations:**
1. **Check model integrity:** Re-pull the model (`ollama pull nemotron-3-nano`) to ensure the GGUF file is not corrupted.
2. **Check GPU memory:** The model may exceed available GPU VRAM. Check `seff <jobid>` for memory usage. Try a smaller quantization or request more GPU memory.
3. **Check Ollama version compatibility:** Some models require newer Ollama versions. Check Ollama release notes for `nemotron-3-nano` support.

---

#### 2D. OpenRouter Model No Longer Available (HTTP 404)

**Description:** The OpenRouter API returns HTTP 404 indicating that a free-tier model's free period has ended and the model must be accessed via a paid slug.

**Distinguishing signature in trace.json `raw_messages`:**
```json
{
  "name": "stderr",
  "text": "LLM Error:\n    Error from OpenRouter: {'error': {'message': 'The free MiMo-V2-Flash period has ended. To continue using this model, please migrate to the paid slug: xiaomi/mimo-v2-flash', 'code': 404}}"
}
```

**Distinguishing characteristics:**
- All turns complete in <1 second (the API error is immediate)
- `total_duration_seconds` for the entire experiment is typically <10s
- All `agent_response` fields are empty strings

**Affected experiments:** `mimo-v2-flash`, `anyllm_openrouter` (both using `xiaomi/mimo-v2-flash:free`)

**Remediations:**
1. **Remove from roster:** Delete the config YAML for models that are no longer free. Update experiment configs to use alternative models.
2. **Switch to paid slug:** If the model is worth using, update the config to use the paid model slug and ensure sufficient OpenRouter credits.
3. **Add availability check:** Before starting the experiment, make a lightweight API call (e.g., list models) to verify the model is accessible. Abort early if not.

---

#### 2E. OpenRouter Rate Limit (HTTP 429)

**Description:** The OpenRouter API returns HTTP 429 when the free-tier rate limit is exceeded. Free models are typically limited to 20 requests/minute.

**Distinguishing signature in trace.json `raw_messages`:**
```json
{
  "name": "stderr",
  "text": "LLM Error:\n    Error from OpenRouter: {'error': {'message': 'Rate limit exceeded: free-models-per-min. ', 'code': 429, 'metadata': {'headers': {'X-RateLimit-Limit': '20', 'X-RateLimit-Remaining': '0'}}}}"
}
```

**Distinguishing characteristics:**
- First 1-2 turns may succeed normally
- Subsequent turns return empty responses very quickly (<1s)
- Rate limit headers visible in raw_messages

**Affected experiments:** `glm-4.5-air` (turn 1 succeeded, turns 2+ rate-limited)

**Remediations:**
1. **Add rate limiting to experiment runner:** Implement a configurable delay between turns (e.g., 5-10 seconds) to stay within rate limits. For free models with 20 req/min, space requests at least 3 seconds apart.
2. **Implement retry with backoff:** When a 429 is received, parse the `X-RateLimit-Reset` header and wait until the reset time before retrying.
3. **Use paid tier:** Paid OpenRouter plans have significantly higher rate limits (hundreds or thousands of requests/minute).

---

### Category 3: LLM Behavioral Failures

#### 3A. LLM-Side Timeout on Complex Tasks

**Description:** The LLM responds to simple prompts (data loading, basic questions) but stalls/times out on complex analytical tasks (schema matching, value mapping). The model is running but takes too long to generate a response.

**Distinguishing signature in trace.json:**
```json
{
  "turn": 1,
  "agent_response": "I'll load the file...",
  "response_type": "llm_response",
  "duration_seconds": 16.8
},
{
  "turn": 3,
  "agent_response": "Request timed out after 180.0 seconds",
  "response_type": "timeout",
  "duration_seconds": 180.0,
  "raw_messages": [
    {"msg_type": "status", "content": {"execution_state": "busy"}},
    {"msg_type": "beaker__execute_input", "...": "..."},
    {"msg_type": "stream", "...": "..."}
  ]
}
```
- Key differentiator from infrastructure timeout (1A): multiple `raw_messages` per turn (>1), including `beaker__execute_input` and sometimes `stream` messages — the kernel IS processing, but the LLM is slow.
- Consistent pattern across reruns: same turns succeed, same turns timeout.

**Affected experiments:** `devstral` (turns 3-5 always timeout), `anyllm_devstral` (same model, same pattern), `devstral-small` (most turns timeout)

**Remediations:**
1. **Increase per-turn timeout:** For complex tasks, increase the timeout from 180s to 600s+ in the experiment config. Some schema matching tasks legitimately take 5+ minutes.
2. **Simplify prompts:** Break complex multi-step tasks into smaller, more focused prompts. Instead of "match to GDC schema and fix results," use separate turns for "list possible matches" and "evaluate match quality."
3. **Use faster/larger models:** Smaller models (devstral-small at ~24B) struggle with complex reasoning. Consider using larger models (70B+) or cloud-hosted models with faster inference.

---

#### 3B. LLM Not Using Tools / Text-Only Guidance

**Description:** The LLM responds to prompts but does NOT use Beaker's code execution capabilities. Instead, it outputs text guidance like "here's the Python code you could run" or "I can't directly manipulate files." This defeats the purpose of the agent framework.

**Distinguishing signature in trace.json:**
```json
{
  "turn": 7,
  "agent_response": "I don't have the capability to directly save files to the filesystem. However, I can guide you through the process...",
  "response_type": "llm_response",
  "tool_calls": [],
  "duration_seconds": 17.0
}
```
- `tool_calls` is always empty
- `agent_response` contains phrases like "I can't", "I don't have the capability", "here's how you could do it"
- The model treats the task as a tutoring exercise rather than an agentic execution

**Affected experiments:** `devstral`, `anyllm_devstral`

**Remediations:**
1. **Improve system prompt:** Add explicit instructions that the agent MUST use `run_code` to execute Python code, not just suggest it. Example: "You have access to a Python environment. Always execute code directly using the run_code tool. Never suggest code for the user to run."
2. **Use models trained for tool use:** Some models (especially code-focused ones like devstral) may default to code explanation rather than execution. Test with models specifically trained for agentic tool use (e.g., GPT-4o, Claude, Qwen3).
3. **Modify Archytas agent prompt template:** The prompt template in `archytas/react.py` controls how tools are presented to the LLM. Ensure it emphasizes that tools MUST be used, not just described.

---

#### 3C. Hallucinated / Fabricated Output Data

**Description:** When the source data file is not found (FileNotFoundError), some LLMs fabricate output data entirely unrelated to the task rather than reporting the error and stopping.

**Distinguishing signature in trace.json + metrics.json:**
```json
// metrics.json showing 0% accuracy with fabricated columns
{
  "column_mapping_accuracy": 0.0,
  "correct_mappings": 0,
  "total_expected": 11,
  "extra_columns": ["dou_id", "dou_title", "dou_description"]
}
```
- `dou_harmonized.csv` exists but contains completely unrelated data
- metrics.json shows 0% accuracy with many extra unrelated columns
- The fabricated data often matches the model's training data patterns (e.g., project management schemas) rather than biomedical data

**Affected experiments:** `qwen3-coder` (run 1)

**Remediations:**
1. **Fix data path:** Ensure `FileNotFoundError` doesn't occur in the first place by correctly mounting data into the container (see Category 4A).
2. **Add data validation step:** After the LLM claims to have produced output, add a validation turn that checks whether the output columns match the expected GDC schema columns.
3. **Add guardrails:** In the experiment script, check if `dou_harmonized.csv` contains at least some expected column names before marking the run as successful.

---

#### 3D. WebSocket Message Size Exceeded

**Description:** The LLM generates a response that exceeds the Beaker WebSocket message size limit (4MB default), crashing the connection.

**Distinguishing signature in trace.json:**
```json
{
  "status": "error",
  "error_message": "WebSocketError: Message size 5784393 exceeds limit 4194304"
}
```

**Affected experiments:** `qwen3-coder` (run 2) — the model tried to process the entire GDC schema and generated a 5.78MB response.

**Remediations:**
1. **Increase WebSocket limit:** Configure Beaker/Jupyter to accept larger messages. In Jupyter config: `c.ServerApp.websocket_max_message_size = 20 * 1024 * 1024` (20MB).
2. **Chunk large data:** When sending large data (like the full GDC schema) to the LLM, break it into smaller chunks across multiple turns rather than one massive prompt.
3. **Limit LLM response length:** Set `max_tokens` in the LLM config to prevent excessively long responses (e.g., 4096 tokens should be sufficient for most turns).

---

#### 3E. Context Window Exhaustion (API Token Limit Exceeded)

**Description:** The accumulated conversation history (system prompt, all prior turns, raw_messages, Beaker state introspection code) exceeds the model's maximum context length. The LLM provider API rejects the request immediately with HTTP 400. Once this occurs, every subsequent turn also fails because the conversation history only grows. The error is silently swallowed by the archytas/toki layer — `agent_response` is empty and `response_type` is `"llm_response"` (not `"error"`), making the failure invisible without `raw_messages` inspection.

**Distinguishing signature in trace.json `raw_messages`:**
```json
{
  "name": "stderr",
  "text": "LLM Error:\n    Error from OpenRouter: {'error': {'message': \"This endpoint's maximum context length is 200000 tokens. However, you requested about 1015152 tokens (1011709 of text input, 3443 of tool input). Please reduce the length of either one, or use the \\\"middle-out\\\" transform to compress your prompt automatically.\", 'code': 400}}"
}
```

**Distinguishing characteristics:**

- Turns complete in <2 seconds (API rejects instantly)
- `agent_response` is empty `""`
- `response_type` is `"llm_response"` (looks like success but is not)
- Token count in error message is far above model limit (e.g., 1,015,000 vs 200,000)
- Token count grows slightly each turn (~100-200 tokens per additional prompt)
- Tool input remains constant (~3,443 tokens); the growth is all in text input

**Affected experiments (11 Feb 2026):** `pony-alpha` (turns 3-8, requested ~1,015,000 tokens against 200,000 limit)

**Root cause:** The Beaker/archytas pipeline accumulates the full conversation history including all raw_messages (Beaker state introspection, execution inputs/outputs, dill serialization code) into the context sent to the LLM. After a complex turn (e.g., schema matching), the raw_messages can contain hundreds of KB of kernel state, pushing the total context far beyond the model's limit.

**Remediations:**

1. **Implement context window monitoring:** Track approximate token count before each API call and warn at 80% capacity. Abort the experiment gracefully when the limit is approached.
2. **Implement conversation summarization:** When approaching the model's context limit, summarize earlier turns into a compact summary and drop the raw_messages for those turns.
3. **Use provider-specific context compression:** OpenRouter offers a `"middle-out" transform` that automatically compresses prompts. Enable this in the API request.
4. **Reduce Beaker state introspection verbosity:** The raw_messages include large serialized Python state objects (dill pickles, full DataFrame representations). These inflate context rapidly and should be truncated or excluded from the LLM's context.
5. **Surface the API error:** Modify the archytas/toki error handling to propagate HTTP 400 context length errors to `agent_response` and set `response_type` to `"error"`.

---

#### 3F. Response Stream Truncated (Premature Connection Close)

**Description:** The LLM provider begins streaming a response but the HTTP connection is severed mid-transfer, resulting in a `ChunkedEncodingError` or `ProtocolError` from urllib3/requests. The archytas/toki layer catches the exception but returns an empty string as the `agent_response` rather than raising an error. The turn is recorded as `response_type: "llm_response"` (apparent success) with an empty response.

**Distinguishing signature in trace.json `raw_messages`:**
```
LLM Error:
    Response ended prematurely

    Traceback (most recent call last):
      File "/usr/local/lib/python3.11/site-packages/requests/models.py", line 820, in generate
        yield from self.raw.stream(chunk_size, decode_content=True)
      ...
    urllib3.exceptions.ProtocolError: Response ended prematurely

    During handling of the above exception, another exception occurred:
      ...
    requests.exceptions.ChunkedEncodingError: Response ended prematurely
```

**Distinguishing characteristics:**

- Duration is significant (tens of seconds), indicating real LLM processing occurred before the stream broke
- `agent_response` is empty `""`
- `response_type` is `"llm_response"` (looks like success)
- Differs from 3E (context exhaustion): takes real time and has a network-level error rather than a token-count error
- Differs from 3A (timeout): completes within the timeout; the response type is `llm_response`, not `timeout`

**Affected experiments (11 Feb 2026):** `glm-4.5-air` (turn 7, 66.3s duration, stream cut mid-transfer)

**Root cause:** Transient network error between the compute node and the OpenRouter API. The HTTP response stream was interrupted — this can be caused by load balancer timeouts, network instability, or the upstream LLM provider terminating the connection.

**Remediations:**

1. **Implement retry logic:** `ChunkedEncodingError` is typically transient. Retry the same turn 1-2 times with exponential backoff before marking it as failed.
2. **Surface the error:** Modify archytas/toki to set `agent_response` to the error message and `response_type` to `"error"` when a stream is truncated.
3. **Add response validation:** In `run_experiment.py`, check if `agent_response` is empty after a non-timeout turn. If so, retry the turn or log it as a stream failure.
4. **Set HTTP client timeouts:** Configure explicit read timeouts and connection keep-alive parameters in the requests/urllib3 session to detect stream failures earlier.

---

#### 3G. Silent Empty Response (No Agent Output) — Cross-cutting Detection

**Description:** A turn completes with `response_type: "llm_response"` (apparent success) but `agent_response` is empty or whitespace-only. This is a cross-cutting detection that catches any case where the LLM framework silently swallowed an error. Specific causes include context window exhaustion (3E) and response stream truncation (3F), but this class also catches unknown error types that result in empty responses.

**Distinguishing signature in trace.json:**
```json
{
  "turn": 4,
  "agent_response": "",
  "response_type": "llm_response",
  "tool_calls": [],
  "duration_seconds": 0.646
}
```

**Distinguishing characteristics:**

- `response_type` is `"llm_response"` but `agent_response` is empty
- Without this detection, the CLI incorrectly counts these turns as "successful"
- When 3E or 3F is also detected for the same run, 3G provides the list of affected turn numbers
- When neither 3E nor 3F is detected, 3G flags an undiagnosed silent failure

**Affected experiments (11 Feb 2026):**

- `pony-alpha` (turns 3-8, caused by 3E context exhaustion)
- `glm-4.5-air` (turn 7, caused by 3F stream truncation)

**Remediations:**

1. **Investigate raw_messages:** For each affected turn, inspect `raw_messages` to identify the root cause (context overflow, network error, rate limit, etc.).
2. **Fix archytas/toki error handling:** The error handling layer should propagate errors to `agent_response` and set `response_type` to `"error"` instead of returning empty strings.
3. **Add response validation in run_experiment.py:** After each turn, check if `agent_response` is empty. If so, abort or retry instead of continuing with broken state.
4. **Log empty responses explicitly:** In the experiment output, log a clear warning when an empty response is received from a non-timeout turn.

---

### Category 4: Data / Configuration Path Errors

#### 4A. FileNotFoundError — Incorrect Data Path in Container

**Description:** The LLM (or the code it generates) tries to access a file path that does not exist inside the container. This happens when:
- The experiment config YAML contains an incorrect path (e.g., `/data/...` instead of `data/...`)
- The Beaker kernel's working directory is not `/workspace` but a subdirectory (e.g., the results folder)
- The LLM generates an absolute path that doesn't match the container's mount structure

**Distinguishing signature in trace.json `raw_messages`:**
```json
{
  "content": {
    "ename": "FileNotFoundError",
    "evalue": "[Errno 2] No such file or directory: 'data/one_metadata_table_gdc_schema/data/dou.csv'",
    "execution_type": "tool",
    "execution_item_name": "run_code"
  }
}
```

**Affected experiments:** `devstral-small`, `qwen3-coder` (all runs)

**Container workspace structure:**
```
/workspace/           <- pwd (working directory set via --pwd /workspace)
├── data/             -> bound from datasets_harmonia/ (read-only)
│   └── one_metadata_table_gdc_schema/
│       └── data/
│           └── dou.csv
└── results/          -> bound to experiment-specific results dir (read-write)
```

**Root cause:** Even after fixing the config YAML paths from `/data/...` to `data/...`, the FileNotFoundError persists because the Beaker kernel's working directory may be set to the results subdirectory (`results/<experiment>_<timestamp>/`) instead of `/workspace`. When the LLM runs `pd.read_csv('data/...')`, the relative path resolves against the kernel's cwd, which is wrong.

**Remediations:**
1. **Use absolute paths in configs:** Change all file references in experiment config YAMLs to use absolute container paths: `/workspace/data/one_metadata_table_gdc_schema/data/dou.csv`.
2. **Fix kernel working directory:** Ensure the Beaker kernel starts with cwd set to `/workspace`. Check if the `WORKSPACE_DIR` environment variable is respected by the kernel, or if the kernel cwd is overridden by Beaker's internal notebook directory management.
3. **Restructure workspace with symlinks:** Mount data as symlinks directly in the workspace root, so that both relative and absolute paths work regardless of kernel cwd. See proposed symlink strategy in section below.

**Proposed symlink strategy:**
```
/workspace/                          <- pwd
├── one_metadata_table_gdc_schema/   -> symlink to datasets_harmonia/one_metadata_table_gdc_schema/
│   └── data/
│       └── dou.csv
├── results/                         -> symlink to experiment-specific results folder
└── (no solution files visible — only data/ subdirs are linked)
```

---

### Category 5: Missing / Incorrect Output

#### 5A. No Output Produced

**Description:** The experiment completes (or times out) without producing `dou_harmonized.csv` or any mapping files in the results directory.

**Distinguishing signature:**
- Results directory exists but contains only `trace.json` and possibly `metrics.json`
- No `dou_harmonized.csv`, `column_mapping.json`, or `value_mapping.json`
- Often a consequence of upstream failures (Categories 1-4)

**Affected experiments:** All experiments except `devstral-small` (partial output) and `qwen3-coder` (fabricated output).

**Remediations:**
1. **Fix upstream issues first:** This is almost always a downstream effect of another failure. Fix the root cause (model config, file paths, timeouts, etc.).
2. **Add output verification to experiment runner:** After the final turn, check if expected output files exist. Log a clear `NO_OUTPUT_PRODUCED` status in the trace.
3. **Add a "save results" fallback:** If the LLM has produced intermediate results (e.g., column mappings in memory) but failed to save them, add a final automated save step that dumps any available results to disk.

---

## Quick Diagnostic Flowchart

```
Is total experiment duration ~2220s with all 8 turns timing out?
├─ YES → Category 1A (Beaker Server Hung)
└─ NO
    ├─ Is total duration <10s with all empty responses?
    │   └─ YES → Check raw_messages for HTTP 404 → Category 2D (Model Unavailable)
    ├─ Does the SLURM log contain "not found (status code: 404)"?
    │   └─ YES → Category 2A (Ollama Model Not Found)
    ├─ Does the SLURM log contain "does not support tool"?
    │   └─ YES → Category 2B (Tool Calling Not Supported)
    ├─ Does the SLURM log contain "exit status 2"?
    │   └─ YES → Category 2C (Ollama Runner Crash)
    ├─ Do raw_messages contain "Rate limit exceeded" / code 429?
    │   └─ YES → Category 2E (Rate Limit)
    ├─ Do raw_messages contain "FileNotFoundError"?
    │   └─ YES → Category 4A (Data Path Error)
    ├─ Does the trace contain "WebSocketError: Message size"?
    │   └─ YES → Category 3D (WebSocket Size Exceeded)
    ├─ Do raw_messages contain "maximum context length"?
    │   └─ YES → Category 3E (Context Window Exhaustion)
    ├─ Do raw_messages contain "Response ended prematurely" / "ChunkedEncodingError"?
    │   └─ YES → Category 3F (Response Stream Truncated)
    ├─ Are there turns with response_type "llm_response" but empty agent_response?
    │   └─ YES → Category 3G (Silent Empty Response) — check raw_messages for root cause
    ├─ Do some turns succeed (short duration) but complex turns timeout?
    │   └─ YES → Check tool_calls array
    │       ├─ Always empty → Category 3B (LLM Not Using Tools)
    │       └─ Sometimes populated → Category 3A (LLM-Side Timeout)
    └─ Does metrics.json show 0% accuracy with extra unrelated columns?
        └─ YES → Category 3C (Hallucinated Output)
```

---

## Reference: Log and Trace File Locations

| File Type | Location Pattern |
|-----------|-----------------|
| SLURM stdout | `logs/{DD-MM-YYYY_HHMM}_{experiment_name}_{jobid}.out` |
| SLURM stderr | `logs/{DD-MM-YYYY_HHMM}_{experiment_name}_{jobid}.err` |
| Experiment trace | `results/{experiment_name}_{YYYYMMDD_HHMMSS}/trace.json` |
| Experiment metrics | `results/{experiment_name}_{YYYYMMDD_HHMMSS}/metrics.json` |
| Beaker log | `logs/{experiment_name}_{jobid}_beaker.log` |
| Ollama log | `logs/{experiment_name}_{jobid}_ollama.log` |
| Conversation log | `results/{experiment_name}_{YYYYMMDD_HHMMSS}/conversation.md` |

---

## Appendix: Affected Experiments Summary (10 Feb 2026)

| Experiment | Job ID | Provider | Model | Primary Failure | Category |
|---|---|---|---|---|---|
| anyllm_devstral | 46662631 | anyllm:ollama | devstral:latest | LLM timeout + no tool use | 3A, 3B |
| anyllm_openrouter | 46662632 | anyllm:openrouter | xiaomi/mimo-v2-flash:free | Free tier expired | 2D |
| devstral-small | 46662633 | ollama | devstral-small-2:latest | FileNotFoundError | 4A |
| devstral | 46662634 | ollama | devstral:latest | LLM timeout + no tool use | 3A, 3B |
| glm-4.5-air | 46662635 | openrouter | z-ai/glm-4.5-air:free | Rate limit after turn 1 | 2E |
| kimi-k2 | 46662636 | ollama | kimi-k2 | Tool calling not supported | 2B |
| mimo-v2-flash | 46662637 | openrouter | xiaomi/mimo-v2-flash:free | Free tier expired | 2D |
| nemotron-3-nano | 46662638 | ollama | nemotron-3-nano | Ollama runner crash | 2C |
| olmo3 | 46662639 | ollama | olmo-3.1:32b | Model not found | 2A |
| qwen3-coder | 46662640 | ollama | qwen3-coder:30b | FileNotFoundError + hallucination + WS crash | 4A, 3C, 3D |

### Affected Experiments Summary (11 Feb 2026)

| Experiment | Job ID | Provider | Model | Primary Failure | Category |
|---|---|---|---|---|---|
| glm-4.5-air | 46734241 | openrouter | z-ai/glm-4.5-air:free | LLM timeout + stream truncation + silent empty response | 3A, 3F, 3G |
| pony-alpha | 46734242 | openrouter | openrouter/pony-alpha | Context window exhaustion + silent empty response | 3E, 3G |
