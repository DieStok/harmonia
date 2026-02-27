# Implementation Plan: Finalize Context Management (Fix 1b + Fix 2)

**Date:** 26 February 2026, 13:22
**Scope:** Two remaining items from `25_02_2026_2238_fix_context_issues.md` that were not implemented in the main context management plan
**Depends on:** `26_02_2026_1243_new_context_management_implementation_plan.md` (already implemented)

---

## What's Already Done (from the main plan)

- Fix 1a: `OLLAMA_NUM_CTX` + `OLLAMA_CONTEXT_LENGTH` exported in `exec_apptainer_harmonia.sh`
- Config pipeline: `ContextManagementConfig` in `config.py`, `generate_env.py` emitting `HARMONIA_STATE_*` env vars
- Archytas: `context_window_override`, `summarization_threshold_pct` env var overrides in `base.py`, `ollama.py`, `summarizers.py`
- Beaker: `ARCHYTAS_MAX_REACT_STEPS`, `ARCHYTAS_MAX_ERRORS` passthrough in `agent.py`; `context_window_override`, `summarization_threshold_pct` in `config.py`
- All 18 experiment YAML configs updated with `context_management:` sections
- `.env.template` documents all new env vars

## What's Missing

| Item | Status | Description |
|------|--------|-------------|
| Fix 1b | Missing | `estimate_vram_usage()` bash function — no VRAM visibility before model loading |
| Fix 2 - Apptainer patch | Missing | FETCH_STATE_CODE budget enforcement in container |
| Fix 2 - Module + tests | Missing | `src/context_management/` reference implementation |
| Fix 2 - Problem 6A | Missing | Error taxonomy entry for budget enforcement events |

---

## Step 1: Fix 1b — `estimate_vram_usage()` in `exec_apptainer_harmonia.sh`

**Goal:** Add VRAM estimation logging after model pre-load, using `ollama ps` output (which shows model size and GPU offload) and `nvidia-smi` for GPU memory info.

**Location:** Inside `start_ollama_server()`, after the model pre-load and `ollama ps` verification block (after line ~561), but before the ollama serve log tail.

**Design decision:** The original plan proposed calling `estimate_vram_usage()` *before* model pre-load using model file size on disk. However, `ollama ps` (which already runs post-load) reports the model size and GPU offload percentage. We'll use a simpler approach: query `nvidia-smi` for total GPU memory, then estimate KV cache from `OLLAMA_CONTEXT_LENGTH`, and combine with the model size from `ollama ps`.

```bash
estimate_vram_usage() {
    # Back-of-the-envelope VRAM estimation after model loading.
    # Uses nvidia-smi for GPU VRAM and OLLAMA_CONTEXT_LENGTH for KV cache estimate.
    # Args: $1 = OLLAMA_CONTEXT_LENGTH (tokens)
    local NUM_CTX="$1"

    # Get GPU VRAM in MiB from nvidia-smi
    local GPU_VRAM_MIB
    GPU_VRAM_MIB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
    if [ -z "$GPU_VRAM_MIB" ]; then
        echo "   (VRAM estimation skipped: nvidia-smi not available)"
        return
    fi

    # Get current GPU memory used in MiB
    local GPU_USED_MIB
    GPU_USED_MIB=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)

    # Estimate KV cache for the full context window (conservative: ~0.25 GB per 1K tokens)
    local KV_CACHE_GB
    KV_CACHE_GB=$(echo "scale=1; ($NUM_CTX / 1024) * 0.25" | bc 2>/dev/null || echo "0")

    local GPU_VRAM_GB
    GPU_VRAM_GB=$(echo "scale=1; $GPU_VRAM_MIB / 1024" | bc 2>/dev/null || echo "0")
    local GPU_USED_GB
    GPU_USED_GB=$(echo "scale=1; $GPU_USED_MIB / 1024" | bc 2>/dev/null || echo "0")
    local GPU_FREE_GB
    GPU_FREE_GB=$(echo "scale=1; ($GPU_VRAM_MIB - $GPU_USED_MIB) / 1024" | bc 2>/dev/null || echo "0")
    local USAGE_PCT
    USAGE_PCT=$(echo "scale=0; ($GPU_USED_MIB * 100) / $GPU_VRAM_MIB" | bc 2>/dev/null || echo "0")

    # Estimate total VRAM after KV cache allocation at full context
    local ESTIMATED_TOTAL_GB
    ESTIMATED_TOTAL_GB=$(echo "scale=1; $GPU_USED_GB + $KV_CACHE_GB" | bc 2>/dev/null || echo "0")
    local ESTIMATED_PCT
    ESTIMATED_PCT=$(echo "scale=0; ($ESTIMATED_TOTAL_GB * 1024 * 100) / $GPU_VRAM_MIB" | bc 2>/dev/null || echo "0")

    echo ""
    echo "   === VRAM Estimation ==="
    echo "   GPU VRAM total:          ~${GPU_VRAM_GB} GB"
    echo "   GPU VRAM used (current): ~${GPU_USED_GB} GB (${USAGE_PCT}%)"
    echo "   GPU VRAM free:           ~${GPU_FREE_GB} GB"
    echo "   KV cache (ctx=${NUM_CTX}):    ~${KV_CACHE_GB} GB (est. at full context)"
    echo "   Est. peak usage:         ~${ESTIMATED_TOTAL_GB} GB (~${ESTIMATED_PCT}%)"

    if [ "$ESTIMATED_PCT" -ge 100 ] 2>/dev/null; then
        echo ""
        echo "   WARNING: Estimated peak VRAM (~${ESTIMATED_TOTAL_GB} GB) EXCEEDS GPU VRAM (~${GPU_VRAM_GB} GB)!"
        echo "   Model will likely be partially offloaded to CPU RAM, causing very slow inference."
        echo "   Consider: smaller quantization, larger GPU, or lower context_length in config YAML."
    elif [ "$ESTIMATED_PCT" -ge 80 ] 2>/dev/null; then
        echo ""
        echo "   WARNING: Estimated peak VRAM (~${ESTIMATED_TOTAL_GB} GB) is ~${ESTIMATED_PCT}% of GPU VRAM."
        echo "   This may cause instability or partial CPU offloading under load."
    else
        echo "   OK: VRAM headroom looks adequate."
    fi
    echo "   ========================"
    echo ""

    # Also log to Ollama log file
    if [ -n "$OLLAMA_LOG_FILE" ]; then
        {
            echo "[$(date)] VRAM Estimation:"
            echo "  GPU total: ${GPU_VRAM_GB} GB, used: ${GPU_USED_GB} GB (${USAGE_PCT}%)"
            echo "  KV cache est (ctx=${NUM_CTX}): ${KV_CACHE_GB} GB"
            echo "  Peak est: ${ESTIMATED_TOTAL_GB} GB (${ESTIMATED_PCT}%)"
        } >> "${OLLAMA_LOG_FILE}"
    fi
}
```

**Call site:** After the GPU offload percentage check (line ~561), call:
```bash
if [ -n "$OLLAMA_CONTEXT_LENGTH" ]; then
    estimate_vram_usage "$OLLAMA_CONTEXT_LENGTH"
fi
```

---

## Step 2: Fix 2a — `src/context_management/` Module

Create the canonical reference implementation as a proper Python module.

**Files to create:**
- `src/context_management/__init__.py`
- `src/context_management/kernel_state_budget.py`
- `src/context_management/test_kernel_state_budget.py`

The module provides:
- `BudgetConfig` dataclass with fields matching the env vars
- `apply_budget(state, config, prev_hashes)` function implementing:
  1. Type blacklisting (whitelist overrides)
  2. Delta tracking (unchanged vars → compact summary)
  3. Per-variable size cap (whitelist exempt)
  4. Total budget cap (whitelist exempt)
- Returns `(budgeted_state, new_hashes)` tuple

**Tests cover:**
- Type blacklist drops variables
- Whitelist overrides size cap
- Per-variable size cap
- Total budget cap
- Delta tracking (unchanged → compact)
- Empty/None state passthrough

---

## Step 3: Fix 2b — FETCH_STATE_CODE Patch in Apptainer `.def`

**File:** `harmonia_beaker_LLM_agent_environment_apptainer.def`

Add a `%post` section after beaker_kernel is installed that patches `python.py` to append budget enforcement code to `FETCH_STATE_CODE`.

The patch:
1. Reads budget params from env vars (`HARMONIA_STATE_*`)
2. Applies type blacklist, delta tracking, per-variable cap, total budget
3. Replaces `_result` with the budgeted version
4. Adds `_budget_metadata` to the result for observability

The patch script runs at container build time and modifies the installed `python.py` in-place.

---

## Step 4: Fix 2c — Problem 6A in Error Taxonomy

**File:** `code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml`

Add category 6 ("Diagnostic") with problem 6A ("Kernel State Budget Enforced") — severity "info", detects `_budget_metadata` and `dropped_count` in traces.

---

## Step 5: Verification

1. Run unit tests: `.venv/bin/python -m pytest src/context_management/ -v`
2. Verify `estimate_vram_usage` function parses correctly (bash syntax check)
3. Verify Apptainer `.def` patch script logic against actual `python.py`
4. Verify error taxonomy YAML is valid

---

## Step 6: Documentation Update

Update the latest codebase description with:
- New `src/context_management/` module
- VRAM estimation in `exec_apptainer_harmonia.sh`
- FETCH_STATE_CODE budget patch in Apptainer definition
- Problem 6A in error taxonomy

---

## File Summary

| Action | File | Description |
|--------|------|-------------|
| **Modify** | `exec_apptainer_harmonia.sh` | Add `estimate_vram_usage()` function + call site |
| **Create** | `src/context_management/__init__.py` | Package init |
| **Create** | `src/context_management/kernel_state_budget.py` | Core budget logic |
| **Create** | `src/context_management/test_kernel_state_budget.py` | Unit tests |
| **Modify** | `harmonia_beaker_LLM_agent_environment_apptainer.def` | FETCH_STATE_CODE budget patch |
| **Modify** | `types_of_log_and_trace_problems.yaml` | Add problem 6A |
| **Modify** | `how_this_codebase_works_26_02_2026.md` | Update documentation |
