# Harmonia Experiment Log Error Analysis

**Date:** 25 February 2026
**Scope:** All experiment runs from logs/ and results/ (34 runs across 3 batches)
**Tool used:** `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`

---

## Executive Summary

Across 34 experiment runs (Feb 10–11 2026), **only 2 runs produced a harmonized CSV**, both from `qwen3-coder:30b`. The failures span 5 high-level categories and 15+ distinct problem types.

---

## Error Category Summary

### 1. Infrastructure Failures

- **1A — Beaker Server Failed to Start** (2 runs): `devstral` and `devstral-small` in the earliest batch hit a 120s startup timeout before Beaker could launch.
- **1C — ZMQ ReadTimeout on Context Cleanup** (7 runs): Cosmetic/benign — occurs during post-experiment teardown, does not affect results.

### 2. Model Availability / Configuration Failures

- **2A — Model Not Found (404)** (1 run): `olmo-3.1:32b` tag didn't exist in the Ollama registry.
- **2B — Tool Calling Not Supported** (3 runs): `kimi-k2:free` (2 runs) and `olmo-3:32b-think` (1 run) — these models cannot use Beaker's tool-calling API.
- **2C — Ollama Stream Error** (1 run): `devstral-small` crashed with "No data received from Ollama stream" ValueError.
- **2D — API Model Unavailable (free tier ended)** (3 runs): `mimo-v2-flash:free` — OpenRouter's free period expired.
- **2F — Model Pre-load Timeout** (3 runs, NEW): Ollama model pre-loading exceeded the 300s `MAX_WAIT` timeout in the sbatch script. Beaker never started. See details below.

### 3. LLM Behavioral Failures

- **3A — LLM-Side Timeout on Complex Tasks** (~14 runs): The most pervasive issue. `devstral` consistently times out on turns 3–6 (the hard harmonization steps). Several Batch B cloud models timed out on every turn.
- **3B — LLM Not Using Tools / Text-Only Guidance** (2 runs): `devstral` variants gave textual instructions instead of executing code in the Beaker kernel.
- **3D — WebSocket Message Size Exceeded** (1 run): `qwen3-coder` hit a 5.7 MB message vs 4 MB WebSocket limit.
- **3E — Context Window Exhaustion** (1 run): `pony-alpha` — detailed in the deep dive section below.
- **3F — Response Stream Truncated** (1 run): `glm-4.5-air` had a premature HTTP connection close (ChunkedEncodingError).
- **3G — Silent Empty Response** (~21 runs): The second most pervasive issue. Agent returns empty string. `nemotron-3-nano` and `olmo3` are 100% empty across all batches.
- **3H — Ollama Silent Context Truncation** (14 log files / 91 events, NEW): Ollama silently clips the prompt to `num_ctx=4096` because Beaker/Archytas doesn't pass `num_ctx` on `/api/chat` calls. See deep dive below.

### 4. Data Path Failures

- **4A — FileNotFoundError** (~8–10 runs): Persistent across all batches. The relative path `data/one_metadata_table_gdc_schema/data/dou.csv` doesn't resolve correctly inside the container.

### 5. Output Failures

- **5A — No Output Produced** (~30 of 34 runs): Downstream consequence of all the above.

---

## Run-by-Run Inventory

### Batch A: Pre-date-prefix (Feb 10, job IDs 46661849–46662438, no run IDs)

| # | Model | Provider | Turns OK/Total | Key Problems | Output? |
|---|-------|----------|----------------|-------------|---------|
| A1 | devstral:latest | ollama | 0/0 | 1A: Beaker startup timeout | No |
| A2 | devstral-small-2:latest | ollama | 0/0 | 1A: Beaker startup timeout | No |
| A3 | devstral:latest | ollama | 5/8 | 3A: Timeout, 3G: Empty | No |
| A4 | devstral-small-2:latest | ollama | 0/0 | 2C: Ollama stream crash | No |
| A5 | olmo-3.1:32b | ollama | 0/8 | 2A: Model not found | No |
| A6 | nemotron-3-nano:30b | ollama | 0/8 | 3G: All turns empty | No |
| A7 | qwen3-coder:30b | ollama | 5/8 | 4A: FileNotFound, 3A: Timeout | **Yes** (metrics: 0/11) |
| A8 | devstral:latest | anyllm:ollama | 5/8 | 3A: Timeout, 3G: Empty | No |
| A9 | mimo-v2-flash:free | anyllm:openrouter | 0/8 | 2D: Free tier ended | No |
| A10 | glm-4.5-air:free | openrouter | 3/8 | 4A, 3A, 3G | No |
| A11 | mimo-v2-flash:free | openrouter | 0/8 | 2D: Free tier ended | No |
| A12 | kimi-k2:free | openrouter | 0/8 | 2B: No tool support | No |
| A13 | devstral:latest | ollama | 4/8 | 3A: Timeout | No |
| A14 | devstral-small-2:latest | ollama | 8/8 | 4A, 3G | No |
| A15 | mimo-v2-flash:free | anyllm:openrouter | 0/8 | 2D: Free tier ended | No |

### Batch B: Feb 10 dated (job IDs 46662631–46662640)

| # | Model | Provider | Turns OK/Total | Key Problems | Output? |
|---|-------|----------|----------------|-------------|---------|
| B1 | devstral:latest | anyllm:ollama | 0/8 | 3A: All timeout | No |
| B2 | mimo-v2-flash:free | anyllm:openrouter | 0/8 | 3A: All timeout | No |
| B3 | devstral-small-2:latest | ollama | 8/8 | 4A, 3G | No |
| B4 | devstral:latest | ollama | 4/8 | 3A: Timeout | No |
| B5 | glm-4.5-air:free | openrouter | 0/8 | 3A: All timeout | No |
| B6 | kimi-k2:free | openrouter | 0/8 | 2B: No tool support | No |
| B7 | mimo-v2-flash:free | openrouter | 0/8 | 3A: All timeout | No |
| B8 | nemotron-3-nano:30b | ollama | 0/8 | 3G: All empty | No |
| B9 | olmo-3.1:32b | ollama | 0/8 | 3G: All empty (no tool support) | No |
| B10 | qwen3-coder:30b | ollama | 5/5 | 3D: WebSocket size exceeded | No |

### Batch C: Feb 11 dated (all with 8-char run IDs)

| # | Run ID | Model | Provider | Turns OK/Total | Key Problems | Output? |
|---|--------|-------|----------|----------------|-------------|---------|
| C1 | 7e879280 | glm-4.5-air:free | openrouter | 1/8 | 3F, 4A, 3A, 3G | No |
| C2 | 756ed865 | pony-alpha | openrouter | 1/8 | **3E: Context exhaustion**, 4A, 3A | No |
| C3 | c678cd44 | devstral:latest | ollama | 4/8 | 3A, 3B, 3G | No |
| C4 | 72add9c7 | devstral-small-2:latest | ollama | 3/8 | **2F: Pre-load timeout** (GPU contention), 4A, 3G | No |
| C5 | edf30893 | glm-4.7-flash:q8_0 | ollama | 0/0 | **2F: Pre-load timeout** (31GB model too slow to load) | No |
| C6 | c8ab47e3 | nemotron-3-nano:30b | ollama | 0/8 | **2F: Pre-load timeout** (24GB model on 24GB GPU), 3G | No |
| C7 | 7bedfa25 | olmo-3:32b-think | ollama | 0/8 | 2B: No tool support, 3G | No |
| C8 | 46d182ea | qwen3-coder:30b | ollama | 6/8 | 4A, 3A, 3G | **Yes** (with metrics) |
| C9 | d0b5043b | devstral:latest | anyllm:ollama | 8/8 | 3B: Not using tools | No |

---

## Deep Dive: Context Size Exceeded Errors

Two distinct mechanisms were found:

### Issue 1: OpenRouter Hard Rejection — pony-alpha (run 756ed865)

**Model:** `openrouter/pony-alpha` (200K context limit)

| Turn | Duration | Result | Tokens Requested |
|------|----------|--------|-----------------|
| 1 | 75s | Success | Normal |
| 2 | 300s | Timeout | Normal (but loaded huge GDC schema into kernel) |
| 3 | 80s | **Empty — context exceeded** | ~1,011,679 |
| 4 | 0.6s | Empty — context exceeded | ~1,014,454 |
| 5 | 0.7s | Empty — context exceeded | ~1,014,602 |
| 6 | 0.8s | Empty — context exceeded | ~1,014,730 |
| 7 | 0.7s | Empty — context exceeded | ~1,015,032 |
| 8 | 1.1s | Empty — context exceeded | ~1,015,152 |

**The exact error from OpenRouter:**
```
This endpoint's maximum context length is 200000 tokens. However,
you requested about 1011679 tokens (1008236 of text input, 3443 of
tool input). Please reduce the length of either one.
```

**Root cause:** In turn 2, the model ran `bdi.match_schema(df_subset, target="gdc", method="similarity_flooding")`, which loaded the entire GDC schema vocabulary into the Python kernel's memory. After each turn, Beaker's `FETCH_STATE_CODE` serializes the **entire kernel state** (all variables) and sends it as context to the LLM. That serialized state ballooned to ~1M tokens — **5x the 200K context window**. Every subsequent API call was instantly rejected (sub-second response times on turns 4–8).

**Why Archytas auto-summarization didn't help:** Archytas does have auto-summarization that triggers at 50% of the context window and also has a `ContextWindowExceededError` catch-and-retry mechanism. However, the problem is that the **single turn's serialized kernel state** (~1M tokens) already exceeds the context window. You cannot summarize a single message down to fit when that message alone is 5x the limit. The summarizer compresses *conversation history* (prior turns), but it cannot compress the current turn's raw kernel state that Beaker injects.

**Key insight:** This is an architectural gap — the kernel state serialization happens *outside* Archytas's context management. Beaker pushes the full serialized state as part of the current message, and Archytas has no mechanism to truncate or reject it before sending to the LLM.

### Issue 2: Ollama Silent Context Truncation — 91 Events Across 14 Log Files

Ollama defaults to `num_ctx=4096` for `/api/chat` calls because Beaker/Archytas doesn't pass the `num_ctx` parameter. The `OLLAMA_CONTEXT_LENGTH=64000` setting in `.env` is only used during the initial model pre-load (`/api/generate`). When the conversation history exceeds 4096 tokens, Ollama silently truncates:

```
level=WARN msg="truncating input prompt" limit=4096 prompt=4200 keep=5 new=4096
```

**Affected models and severity:**

| Model | Runs Affected | Max Overflow | Severity |
|-------|---------------|-------------|----------|
| qwen3-coder:30b | 3 runs | **688,358 tokens** (prompt=692,454) | Catastrophic — 99.4% of prompt discarded |
| devstral-small-2 | 3 runs | ~2,960 tokens | Moderate — loses early conversation history |
| devstral:latest | 5 runs | ~304 tokens | Minor — small clipping at conversation start |

**Why `OLLAMA_CONTEXT_LENGTH=64000` doesn't work:** The `.env` value is read by `exec_apptainer_harmonia.sh` and passed as `num_ctx` to the initial `/api/generate` (pre-loading) call only. However, Beaker/Archytas does **not** pass `num_ctx` on subsequent `/api/chat` calls, so Ollama falls back to its default of 4096.

---

## Deep Dive: Model Pre-load Timeout Failures (NEW: Problem 2F)

Three runs from the Feb 11 batch failed at startup because Ollama model pre-loading exceeded the 300s `MAX_WAIT` timeout.

| Run | Model | Size | Node | GPU | GPU VRAM | Root Cause |
|-----|-------|------|------|-----|----------|------------|
| c8ab47e3 | nemotron-3-nano:30b | 24 GB | n0096 | Quadro RTX 6000 | 24 GB | Model saturates GPU VRAM; partial CPU offload makes load too slow |
| edf30893 | glm-4.7-flash:q8_0 | 31 GB | n0132 | A100 80GB | 80 GB | 31 GB Q8_0 model; NFS read + GPU load + inference exceeds 300s |
| 72add9c7 | devstral-small-2 | 15 GB | n0108 | V100 16GB | 16 GB | GPU contention: co-located with devstral job on same node/GPU |

For `devstral-small` (72add9c7), the job landed on the **exact same node and GPU** (n0108, V100 16GB) as the successful `devstral` job (46734243). Both started simultaneously. The `devstral` model (14 GB) loaded first and consumed all VRAM, preventing `devstral-small-2` (15 GB) from loading.

---

## Models That Are Fundamentally Broken

| Model | Issue | Runs Attempted | Recommendation |
|-------|-------|---------------|----------------|
| olmo-3 / olmo-3.1 | Model not found (wrong tag) + no tool support | 4 | Remove from roster |
| kimi-k2:free | No tool support via OpenRouter | 2 | Remove or use community Ollama model with tool template |
| mimo-v2-flash:free | Free tier expired | 3 | Remove or switch to paid slug |
| nemotron-3-nano:30b | 100% silent empty responses across all batches | 3 | Investigate; likely tool-calling or prompt-handling issue |

---

## Architectural Recommendations

### For Context Issues (Issues 1 & 2)
1. **Pass `num_ctx` on every `/api/chat` call** (Archytas/Beaker change), or set `OLLAMA_NUM_CTX` as a server-level environment variable.
2. **Cap serialized kernel state size** — exclude large variables or truncate individual variable representations before sending to the LLM.
3. **Add a pre-flight token budget check** — estimate token count before sending to the API; if it exceeds the model's context window, either summarize older turns or warn and abort.
4. **Add early abort on context exhaustion** — once the API rejects a request for context overflow, terminate the run rather than burning through remaining turns with guaranteed-empty responses.

### For Model Pre-load Timeouts (Issue 2F)
1. Increase `MAX_WAIT` from 300s to 600s for larger models.
2. Investigate SLURM GPU allocation to prevent two GPU jobs sharing one GPU.
3. Match model sizes to available GPU VRAM.

### For Data Path Issues (Issue 4A)
1. Fix container data mount paths.
2. Use absolute paths (`/workspace/data/...`) in config YAMLs.
