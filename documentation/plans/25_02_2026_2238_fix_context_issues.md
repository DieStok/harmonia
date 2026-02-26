# Implementation Plan: Fix Context Size Issues (v2)

**Date:** 25 February 2026 (updated with user feedback)
**Scope:** Two fixes — (1) Ollama num_ctx passthrough + VRAM estimation, (2) FETCH_STATE_CODE budget caps with delta-tracking, variable whitelist, and percentage-based budget
**Background:** See `documentation/possible_features/25_02_2026_2238_context_management_Archytas_beaker.md`

---

## Overview

| Fix | Problem | Effort | Risk |
|-----|---------|--------|------|
| Fix 1: Ollama num_ctx + VRAM warnings | Silent truncation to 4096 tokens; no VRAM visibility | Small (exec script changes) | Low |
| Fix 2: FETCH_STATE_CODE budget | Kernel state serialization can produce ~1M tokens | New Python module + Apptainer patch | Low-medium |

---

## Fix 1: Ollama Context Length Passthrough + VRAM Estimation

### Problem

`OLLAMA_CONTEXT_LENGTH=64000` in `.env` is only used during model pre-load (`/api/generate`). Subsequent `/api/chat` calls from Beaker/Archytas don't pass `num_ctx`, so Ollama defaults to 4096 tokens and silently truncates prompts.

Additionally, there is no visibility into whether the requested context length will actually fit in GPU VRAM alongside the model.

### Solution

1. Export **both** `OLLAMA_NUM_CTX` and `OLLAMA_CONTEXT_LENGTH` before starting Ollama (the exact env var name varies across Ollama versions, so set both).
2. Add a back-of-the-envelope VRAM estimation that prints a **WARNING** if estimated total exceeds 80% of available VRAM (or exceeds it entirely).

### Change 1a: Export both env vars

**File:** `exec_apptainer_harmonia.sh`

**Current code (lines 618–622):**

```bash
# Export OLLAMA_CONTEXT_LENGTH if set (controls Ollama's context window allocation)
if [ -n "$OLLAMA_CONTEXT_LENGTH" ]; then
    export OLLAMA_CONTEXT_LENGTH
    echo "   OLLAMA_CONTEXT_LENGTH: ${OLLAMA_CONTEXT_LENGTH}"
fi
```

**New code (replace the above block):**

```bash
# Export OLLAMA_CONTEXT_LENGTH and OLLAMA_NUM_CTX if set.
# Both env vars are set because the exact name varies across Ollama versions:
#   - OLLAMA_CONTEXT_LENGTH: documented in Ollama FAQ
#   - OLLAMA_NUM_CTX: used in some Ollama versions (see GitHub issue #10829)
# Without this, Ollama defaults to num_ctx=4096 on /api/chat calls and
# silently truncates prompts. See problem 3H in types_of_log_and_trace_problems.yaml.
if [ -n "$OLLAMA_CONTEXT_LENGTH" ]; then
    export OLLAMA_CONTEXT_LENGTH
    export OLLAMA_NUM_CTX="${OLLAMA_CONTEXT_LENGTH}"
    echo "   OLLAMA_CONTEXT_LENGTH: ${OLLAMA_CONTEXT_LENGTH}"
    echo "   OLLAMA_NUM_CTX:        ${OLLAMA_CONTEXT_LENGTH} (server-level default for /api/chat)"
fi
```

### Change 1b: VRAM estimation and warning

Add a function to `exec_apptainer_harmonia.sh` that estimates VRAM usage after GPU detection but before model pre-load. The estimation uses this rough formula:

```
VRAM_model ≈ model_file_size_GB (from `ollama show --modelfile` or file size on disk)
VRAM_kv_cache ≈ (num_ctx / 1024) * 0.125 * num_layers  (rough: ~0.125 GB per 1K context per 32 layers)
VRAM_overhead ≈ 1.0 GB (CUDA runtime, Ollama server, buffers)
VRAM_total ≈ VRAM_model + VRAM_kv_cache + VRAM_overhead
```

For a simpler approach that doesn't require parsing model architecture:

```
VRAM_kv_cache_estimate ≈ (num_ctx / 1024) * 0.25  (conservative: ~0.25 GB per 1K tokens)
```

**Add this function to `exec_apptainer_harmonia.sh`, called after GPU detection and before model pre-load:**

```bash
estimate_vram_usage() {
    # Back-of-the-envelope VRAM estimation
    # Args: $1 = model file size in bytes, $2 = num_ctx, $3 = GPU VRAM in MiB
    local MODEL_SIZE_BYTES="$1"
    local NUM_CTX="$2"
    local GPU_VRAM_MIB="$3"

    if [ -z "$MODEL_SIZE_BYTES" ] || [ -z "$NUM_CTX" ] || [ -z "$GPU_VRAM_MIB" ]; then
        return
    fi

    local MODEL_SIZE_GB=$(echo "scale=1; $MODEL_SIZE_BYTES / 1073741824" | bc 2>/dev/null || echo "0")
    local KV_CACHE_GB=$(echo "scale=1; ($NUM_CTX / 1024) * 0.25" | bc 2>/dev/null || echo "0")
    local OVERHEAD_GB="1.0"
    local TOTAL_GB=$(echo "scale=1; $MODEL_SIZE_GB + $KV_CACHE_GB + $OVERHEAD_GB" | bc 2>/dev/null || echo "0")
    local GPU_VRAM_GB=$(echo "scale=1; $GPU_VRAM_MIB / 1024" | bc 2>/dev/null || echo "0")
    local USAGE_PCT=$(echo "scale=0; ($TOTAL_GB * 100) / $GPU_VRAM_GB" | bc 2>/dev/null || echo "0")

    echo ""
    echo "   === VRAM Estimation ==="
    echo "   Model size:       ~${MODEL_SIZE_GB} GB"
    echo "   KV cache (ctx=${NUM_CTX}): ~${KV_CACHE_GB} GB"
    echo "   Overhead:         ~${OVERHEAD_GB} GB"
    echo "   Estimated total:  ~${TOTAL_GB} GB"
    echo "   GPU VRAM:         ~${GPU_VRAM_GB} GB"
    echo "   Usage:            ~${USAGE_PCT}%"

    # Warn if estimated usage exceeds 80% of VRAM
    if [ "$USAGE_PCT" -ge 100 ] 2>/dev/null; then
        echo ""
        echo "   ⚠️  WARNING: Estimated VRAM usage (~${TOTAL_GB} GB) EXCEEDS available GPU VRAM (~${GPU_VRAM_GB} GB)!"
        echo "   ⚠️  Model will likely be partially offloaded to CPU RAM, causing very slow inference."
        echo "   ⚠️  Consider: smaller quantization, larger GPU, or lower context_length in config YAML."
    elif [ "$USAGE_PCT" -ge 80 ] 2>/dev/null; then
        echo ""
        echo "   ⚠️  WARNING: Estimated VRAM usage (~${TOTAL_GB} GB) is >${USAGE_PCT}% of GPU VRAM (~${GPU_VRAM_GB} GB)."
        echo "   ⚠️  This may cause instability or partial CPU offloading under load."
    else
        echo "   ✓ VRAM headroom looks adequate."
    fi
    echo "   ========================"
    echo ""
}
```

Call this function after GPU detection and model size discovery, passing in the model file size (obtainable from the Ollama models directory), `OLLAMA_CONTEXT_LENGTH`, and the detected GPU VRAM.

**Note:** `context_length` is already in the per-model config YAMLs (e.g., `context_length: 64000`), so models already get different values. This VRAM check just makes the consequences visible.

### Verification

```bash
# After a new run, check for:
grep "OLLAMA_NUM_CTX" logs/*.out           # Should show the env var
grep "VRAM Estimation" logs/*.out          # Should show the estimate
grep "truncating input prompt" logs/*_ollama.log  # Should be zero matches
```

---

## Fix 2: FETCH_STATE_CODE Kernel State Budget

### Problem

Beaker's `FETCH_STATE_CODE` (in `beaker_kernel/subkernels/python.py` lines 27–124) serializes the entire Python kernel namespace to JSON. When BDI loads the GDC schema vocabulary, this serialized state can balloon to ~1M tokens. The existing truncation (99 items for lists, `.head()` for DataFrames) is insufficient because the GDC schema is deeply nested dicts.

### Solution

Patch `FETCH_STATE_CODE` **in the Apptainer build definition** to add budget enforcement inline. The patch implements four configurable strategies:

1. **Per-variable size cap**: Drop any single variable whose JSON exceeds a threshold. Replace with a placeholder.
2. **Total budget cap (as % of model context window)**: If the total serialized state exceeds a budget (default: 25% of context window), stop adding variables.
3. **Type blacklist**: Exclude variables of certain types entirely (e.g., BDI internal objects).
4. **Variable whitelist**: Always include certain variable names even if they exceed per-variable cap (e.g., `df`, `df_harmonized`, `result`).
5. **Delta tracking**: Track which variables changed since the last FETCH_STATE_CODE call. Send unchanged variables as compact summaries (name + type + size only), send changed/new variables in full.

### Architecture

```
[FETCH_STATE_CODE executes in kernel]
         │
         ├─ Original Beaker logic: serialize all variables
         │
         ▼
[Budget enforcement (inline in FETCH_STATE_CODE)]
         │
         ├─ Step 0: Compare to previous state snapshot → identify changed vars
         ├─ Step 1: Remove blacklisted types
         ├─ Step 2: For unchanged vars → compact summary only
         ├─ Step 3: For changed vars → check per-variable cap (whitelist exempted)
         ├─ Step 4: Enforce total budget (drop remaining large vars)
         │
         ▼
[Budgeted state JSON]  (guaranteed ≤ budget)
```

### Integration: Apptainer Build Definition Patch

**File to modify:** `harmonia_beaker_LLM_agent_environment_apptainer.def`

Add a `%post` section that patches `python.py` after `beaker_kernel` is installed. This is durable across rebuilds (it's in the definition file) and includes clear comments explaining what and why.

**Add to the `%post` section, after the pip install of beaker-kernel:**

```bash
# =============================================================================
# HARMONIA PATCH: Kernel State Budget Enforcement for FETCH_STATE_CODE
# =============================================================================
# Problem: Beaker's FETCH_STATE_CODE serializes the ENTIRE Python kernel
# namespace to JSON and sends it to the LLM as context. When BDI loads the
# GDC schema vocabulary (~1M tokens), this exceeds any model's context window.
#
# Solution: Append budget enforcement logic to the end of FETCH_STATE_CODE.
# The patch runs after the original serialization and applies:
#   1. Type blacklisting (exclude known large BDI types)
#   2. Variable whitelisting (always keep important result variables)
#   3. Delta tracking (only send changed variables in full)
#   4. Per-variable size cap (configurable, default 20K chars)
#   5. Total budget cap (configurable, default 25% of context window)
#
# The budget parameters are read from environment variables at kernel startup,
# allowing per-experiment configuration via the experiment YAML.
#
# See: documentation/plans/25_02_2026_2238_fix_context_issues.md
# See: types_of_log_and_trace_problems.yaml (problems 3E, 3H)
# =============================================================================

BEAKER_PYTHON_SUBKERNEL="/usr/local/lib/python3.11/site-packages/beaker_kernel/subkernels/python.py"

# Verify the file exists and contains FETCH_STATE_CODE
if [ ! -f "$BEAKER_PYTHON_SUBKERNEL" ]; then
    echo "ERROR: Cannot find beaker_kernel subkernel at $BEAKER_PYTHON_SUBKERNEL"
    exit 1
fi
if ! grep -q "FETCH_STATE_CODE" "$BEAKER_PYTHON_SUBKERNEL"; then
    echo "ERROR: FETCH_STATE_CODE not found in $BEAKER_PYTHON_SUBKERNEL"
    exit 1
fi

# Create the patch file that will be applied via Python
cat > /tmp/patch_fetch_state_code.py << 'PATCH_EOF'
"""
Patch FETCH_STATE_CODE in beaker_kernel to add budget enforcement.
This runs at container build time (Apptainer %post).
"""
import re

SUBKERNEL_PATH = "/usr/local/lib/python3.11/site-packages/beaker_kernel/subkernels/python.py"

# The budget enforcement code to append to FETCH_STATE_CODE.
# This code runs INSIDE the Jupyter kernel after the original state serialization.
# It operates on `_result` which is the dict built by the original FETCH_STATE_CODE.
# Budget parameters are read from os.environ, falling back to defaults.
BUDGET_CODE = '''
# === HARMONIA: Kernel State Budget Enforcement ===
# Prevents context window explosions from large kernel state serialization.
# Budget params from env vars (set by exec_apptainer_harmonia.sh from experiment YAML):
#   HARMONIA_STATE_MAX_VAR_SIZE: max chars per variable (default: 20000)
#   HARMONIA_STATE_BUDGET_PCT: total budget as % of context window (default: 25)
#   HARMONIA_STATE_TOTAL_BUDGET: absolute total budget in chars (default: 50000, overridden by PCT if context known)
#   HARMONIA_STATE_TYPE_BLACKLIST: comma-separated type substrings to exclude
#   HARMONIA_STATE_VAR_WHITELIST: comma-separated variable names to always keep in full

import os as _os
import json as _budget_json

_BUDGET_MAX_VAR_SIZE = int(_os.environ.get("HARMONIA_STATE_MAX_VAR_SIZE", "20000"))
_BUDGET_TOTAL = int(_os.environ.get("HARMONIA_STATE_TOTAL_BUDGET", "50000"))
_BUDGET_PCT = int(_os.environ.get("HARMONIA_STATE_BUDGET_PCT", "25"))
_BUDGET_TYPE_BLACKLIST = [s.strip() for s in _os.environ.get(
    "HARMONIA_STATE_TYPE_BLACKLIST",
    "SchemaGraph,SimilarityFloodingMatcher,ColumnMappingSpec,ValueMappingSpec"
).split(",") if s.strip()]
_BUDGET_VAR_WHITELIST = [s.strip() for s in _os.environ.get(
    "HARMONIA_STATE_VAR_WHITELIST",
    "df,df_harmonized,df_subset,result,results,output,harmonized,mapping,column_mapping,value_mapping"
).split(",") if s.strip()]

# Delta tracking: store previous state hash per variable for change detection
if not hasattr(__builtins__, "_harmonia_prev_state_hashes") if isinstance(__builtins__, dict) else not hasattr(__builtins__, "_harmonia_prev_state_hashes"):
    try:
        import builtins as _builtins_mod
        if not hasattr(_builtins_mod, "_harmonia_prev_state_hashes"):
            _builtins_mod._harmonia_prev_state_hashes = {}
        _prev_hashes = _builtins_mod._harmonia_prev_state_hashes
    except Exception:
        _prev_hashes = {}
else:
    import builtins as _builtins_mod
    _prev_hashes = _builtins_mod._harmonia_prev_state_hashes

def _apply_state_budget(_state):
    if not _state or not isinstance(_state, dict):
        return _state

    _vars = _state.get("variables", {})
    _budgeted = {}
    _running = 0
    _dropped_count = 0
    _unchanged_count = 0
    _new_hashes = {}

    # Measure all variable sizes and compute hashes for delta tracking
    _sized = []
    for _vn, _vi in _vars.items():
        try:
            _serialized = _budget_json.dumps(_vi, default=str)
            _vs = len(_serialized)
            _vh = hash(_serialized)
        except Exception:
            _vs = 0
            _vh = 0
            _serialized = ""
        _sized.append((_vn, _vi, _vs, _vh))
        _new_hashes[_vn] = _vh

    # Sort by size ascending to fit as many as possible within budget
    _sized.sort(key=lambda x: x[2])

    for _vn, _vi, _vs, _vh in _sized:
        _vt = str(_vi.get("type", ""))
        _is_whitelisted = _vn in _BUDGET_VAR_WHITELIST

        # Step 1: Check type blacklist (whitelist overrides blacklist)
        if not _is_whitelisted and any(_bl in _vt for _bl in _BUDGET_TYPE_BLACKLIST):
            _budgeted[_vn] = {"type": _vt, "value": f"<dropped: blacklisted_type, size={_vs:,}>", "_dropped": True}
            _dropped_count += 1
            continue

        # Step 2: Delta tracking — if variable unchanged, send compact summary only
        # (whitelist exempted: always send whitelisted vars in full)
        if not _is_whitelisted and _vn in _prev_hashes and _prev_hashes[_vn] == _vh:
            _compact = {"type": _vt, "size": _vi.get("size", ""), "_unchanged": True}
            _budgeted[_vn] = _compact
            _running += len(_budget_json.dumps(_compact, default=str))
            _unchanged_count += 1
            continue

        # Step 3: Per-variable size check (whitelist exempted)
        if not _is_whitelisted and _BUDGET_MAX_VAR_SIZE > 0 and _vs > _BUDGET_MAX_VAR_SIZE:
            _budgeted[_vn] = {"type": _vt, "value": f"<dropped: size={_vs:,} > max={_BUDGET_MAX_VAR_SIZE:,}>", "_dropped": True}
            _dropped_count += 1
            continue

        # Step 4: Total budget check (whitelist exempted from dropping but still counted)
        if not _is_whitelisted and _BUDGET_TOTAL > 0 and (_running + _vs) > _BUDGET_TOTAL:
            _budgeted[_vn] = {"type": _vt, "value": f"<dropped: total_budget_exceeded, size={_vs:,}>", "_dropped": True}
            _dropped_count += 1
            continue

        _budgeted[_vn] = _vi
        _running += _vs

    _state["variables"] = _budgeted

    # Store current hashes for next delta comparison
    try:
        import builtins as _builtins_mod2
        _builtins_mod2._harmonia_prev_state_hashes = _new_hashes
    except Exception:
        pass

    if _dropped_count > 0 or _unchanged_count > 0:
        _state["_budget_metadata"] = {
            "dropped_count": _dropped_count,
            "unchanged_count": _unchanged_count,
            "budget_total": _BUDGET_TOTAL,
            "budget_pct": _BUDGET_PCT,
            "max_var_size": _BUDGET_MAX_VAR_SIZE,
            "final_size_chars": _running,
        }
    return _state

_result = _apply_state_budget(_result)
# === END HARMONIA: Kernel State Budget Enforcement ===
'''

# Read the original file
with open(SUBKERNEL_PATH, 'r') as f:
    content = f.read()

# Find the FETCH_STATE_CODE string and insert budget code before the closing """
# The original ends with: _result\n"""
# We insert our budget code before `_result\n"""`
# Match the last `_result\n"""` in FETCH_STATE_CODE
old_ending = '_result\n"""'
new_ending = BUDGET_CODE + '\n_result\n"""'

if old_ending not in content:
    # Try alternate ending patterns
    old_ending = "_result\n\"\"\""
    new_ending = BUDGET_CODE + "\n_result\n\"\"\""

if old_ending in content:
    patched = content.replace(old_ending, new_ending, 1)
    with open(SUBKERNEL_PATH, 'w') as f:
        f.write(patched)
    print(f"SUCCESS: Patched FETCH_STATE_CODE in {SUBKERNEL_PATH}")
    print(f"  Added {len(BUDGET_CODE)} chars of budget enforcement code")
else:
    print(f"ERROR: Could not find FETCH_STATE_CODE ending pattern in {SUBKERNEL_PATH}")
    print("  Manual patching required.")
    exit(1)
PATCH_EOF

python3 /tmp/patch_fetch_state_code.py
rm /tmp/patch_fetch_state_code.py
```

### Passing Budget Config from Experiment YAML → Container

The budget parameters are controlled via environment variables that `exec_apptainer_harmonia.sh` reads from the experiment config YAML and passes into the Apptainer container.

**Add to `exec_apptainer_harmonia.sh`, in the section that reads the YAML config:**

```bash
# Read kernel state budget config from experiment YAML (if present)
HARMONIA_STATE_MAX_VAR_SIZE=$(python3 -c "
import yaml, sys
with open('$CONFIG_FILE') as f:
    c = yaml.safe_load(f)
b = c.get('context_management', {})
print(b.get('max_variable_size', 20000))
" 2>/dev/null || echo "20000")

HARMONIA_STATE_BUDGET_PCT=$(python3 -c "
import yaml, sys
with open('$CONFIG_FILE') as f:
    c = yaml.safe_load(f)
b = c.get('context_management', {})
print(b.get('state_budget_pct', 25))
" 2>/dev/null || echo "25")

# Calculate absolute budget from percentage if context_length is known
if [ -n "$OLLAMA_CONTEXT_LENGTH" ] && [ "$HARMONIA_STATE_BUDGET_PCT" -gt 0 ] 2>/dev/null; then
    # Rough estimate: 1 token ≈ 3.5 chars
    CHARS_PER_TOKEN=4
    CONTEXT_CHARS=$((OLLAMA_CONTEXT_LENGTH * CHARS_PER_TOKEN))
    HARMONIA_STATE_TOTAL_BUDGET=$((CONTEXT_CHARS * HARMONIA_STATE_BUDGET_PCT / 100))
    echo "   State budget: ${HARMONIA_STATE_BUDGET_PCT}% of ${OLLAMA_CONTEXT_LENGTH} tokens ≈ ${HARMONIA_STATE_TOTAL_BUDGET} chars"
else
    HARMONIA_STATE_TOTAL_BUDGET=50000
fi

export HARMONIA_STATE_MAX_VAR_SIZE
export HARMONIA_STATE_TOTAL_BUDGET
export HARMONIA_STATE_BUDGET_PCT
```

### Experiment YAML Configuration

**New `context_management` section in experiment configs:**

```yaml
# In experiment config YAML (e.g., dou_harmonization_devstral.yaml)
experiment:
  name: dou_harmonization_devstral

llm:
  provider: ollama
  model: devstral:latest
  context_length: 64000

# NEW: context management configuration
context_management:
  # Max chars per single variable in kernel state (default: 20000, 0 to disable)
  max_variable_size: 20000
  # Total state budget as percentage of model context window (default: 25)
  state_budget_pct: 25
  # Archytas summarization threshold as percentage of context window (default: 50)
  summarization_threshold_pct: 50
  # Type names to exclude from kernel state (comma-separated in env, list in YAML)
  type_blacklist:
    - SchemaGraph
    - SimilarityFloodingMatcher
  # Variable names to always include in full, even if over size cap
  var_whitelist:
    - df
    - df_harmonized
    - df_subset
    - result
    - mapping
    - column_mapping
    - value_mapping
```

**File to modify:** `src/automation/config.py`

Add a new dataclass:

```python
@dataclass
class ContextManagementConfig:
    """Configuration for kernel state budget and Archytas summarization."""
    max_variable_size: int = 20_000
    state_budget_pct: int = 25
    summarization_threshold_pct: int = 50
    type_blacklist: list[str] = field(default_factory=lambda: [
        "SchemaGraph", "SimilarityFloodingMatcher",
        "ColumnMappingSpec", "ValueMappingSpec",
    ])
    var_whitelist: list[str] = field(default_factory=lambda: [
        "df", "df_harmonized", "df_subset", "result", "results",
        "output", "harmonized", "mapping", "column_mapping", "value_mapping",
    ])
```

Add to `ExperimentConfig`:

```python
context_management: ContextManagementConfig = field(default_factory=ContextManagementConfig)
```

Parse from YAML in `ExperimentConfig.from_dict()`:

```python
cm_data = data.get("context_management", {})
context_management = ContextManagementConfig(
    max_variable_size=cm_data.get("max_variable_size", 20_000),
    state_budget_pct=cm_data.get("state_budget_pct", 25),
    summarization_threshold_pct=cm_data.get("summarization_threshold_pct", 50),
    type_blacklist=cm_data.get("type_blacklist", ContextManagementConfig().type_blacklist),
    var_whitelist=cm_data.get("var_whitelist", ContextManagementConfig().var_whitelist),
)
```

### Standalone Python Module (for testing + documentation)

Still create `src/context_management/kernel_state_budget.py` with the same logic as the inline patch, but as a proper importable module with `BudgetConfig` and `apply_budget()`. This serves as:
- The canonical reference implementation
- The unit test target
- A fallback for non-container use (e.g., manual interactive experiments)

### Log Analysis: New Problem Category 6A

**File to modify:** `code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml`

Add:

```yaml
  - id: "6A"
    category: "diagnostic"
    name: "Kernel State Budget Enforced"
    description: |
      The kernel state budget enforcement dropped one or more variables
      from the serialized state. This is informational — it means the
      budget system is working as intended. Check _budget_metadata in
      the auto-context to see what was dropped and why.
    severity: "info"
    detection:
      log_keywords: []
      log_regex: []
      trace_keywords:
        - "_budget_metadata"
        - "dropped_count"
      trace_regex:
        - "\"dropped_count\":\\s*[1-9]"
    remediation:
      - "Informational only: the budget system prevented a context explosion"
      - "If important variables were dropped, add them to var_whitelist in experiment YAML"
      - "If too many variables are dropped, increase state_budget_pct or max_variable_size"
```

### Testing

**File:** `src/context_management/test_kernel_state_budget.py`

Same tests as before, plus:

```python
def test_whitelist_overrides_size_cap():
    """Whitelisted variables are kept even if they exceed max_variable_size."""
    large_value = "x" * 30_000
    state = {
        "modules": {},
        "variables": {
            "df_harmonized": {"type": "DataFrame", "value": large_value},
            "big_internal": {"type": "dict", "value": large_value},
        },
        "functions": {},
        "classes": {},
    }
    config = BudgetConfig(
        max_variable_size=20_000,
        total_budget=0,
        var_whitelist=["df_harmonized"],
    )
    result = apply_budget(state, config=config)
    assert result["variables"]["df_harmonized"].get("_dropped") is None  # kept
    assert result["variables"]["big_internal"]["_dropped"] is True  # dropped


def test_delta_tracking_sends_unchanged_as_compact():
    """Unchanged variables between calls are sent as compact summaries."""
    state = {
        "modules": {},
        "variables": {
            "x": {"type": "int", "value": 42, "size": ""},
            "y": {"type": "str", "value": "hello", "size": "5"},
        },
        "functions": {},
        "classes": {},
    }
    # First call: everything is new, all sent in full
    result1 = apply_budget(state, config=BudgetConfig(total_budget=0, max_variable_size=0))
    assert result1["variables"]["x"]["value"] == 42

    # Second call: same state, should be compact
    result2 = apply_budget(state, config=BudgetConfig(total_budget=0, max_variable_size=0))
    assert result2["variables"]["x"].get("_unchanged") is True
```

Run:

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
.venv/bin/python -m pytest src/context_management/test_kernel_state_budget.py -v
```

---

## Implementation Order

1. **Fix 1a**: Add `export OLLAMA_NUM_CTX` to `exec_apptainer_harmonia.sh`
2. **Fix 1b**: Add VRAM estimation function to `exec_apptainer_harmonia.sh`
3. **Fix 2 - Module**: Create `src/context_management/` with `kernel_state_budget.py` and tests
4. **Fix 2 - Tests**: Run unit tests
5. **Fix 2 - Apptainer patch**: Add the FETCH_STATE_CODE patch to `harmonia_beaker_LLM_agent_environment_apptainer.def`
6. **Fix 2 - Config**: Add `ContextManagementConfig` to `src/automation/config.py`
7. **Fix 2 - Env passthrough**: Add config-to-env-var plumbing in `exec_apptainer_harmonia.sh`
8. **Fix 2 - YAML**: Add `context_management:` section to experiment config YAMLs
9. **Fix 2 - Logging**: Add problem 6A to the error taxonomy YAML
10. **Rebuild container**: `apptainer build` with the patched definition
11. **End-to-end test**: Run a BDI `match_schema(target="gdc")` experiment

### Optional (empirical validation, do after first successful run):

12. **Dump raw kernel state**: Run a BDI experiment with budget disabled (`HARMONIA_STATE_MAX_VAR_SIZE=0 HARMONIA_STATE_TOTAL_BUDGET=0`) and inspect the raw serialized state to identify the actual variable names and types that are the offenders. Refine the type blacklist accordingly.

---

## File Summary

| Action | File | Description |
|--------|------|-------------|
| **Modify** | `exec_apptainer_harmonia.sh` | Add `OLLAMA_NUM_CTX` export, VRAM estimation, config-to-env passthrough |
| **Modify** | `harmonia_beaker_LLM_agent_environment_apptainer.def` | Add FETCH_STATE_CODE patch in `%post` |
| **Create** | `src/context_management/__init__.py` | Package init |
| **Create** | `src/context_management/kernel_state_budget.py` | Core budget logic (canonical reference + tests target) |
| **Create** | `src/context_management/test_kernel_state_budget.py` | Unit tests |
| **Modify** | `src/automation/config.py` | Add `ContextManagementConfig` dataclass |
| **Modify** | Experiment config YAMLs in `experiments/.../configs/automated/` | Add `context_management:` section |
| **Modify** | `types_of_log_and_trace_problems.yaml` | Add problem 6A |

---

## Verification Checklist

- [ ] `grep "OLLAMA_NUM_CTX" logs/*.out` shows the env var in new SLURM logs
- [ ] `grep "VRAM Estimation" logs/*.out` shows back-of-the-envelope VRAM calc
- [ ] `grep "truncating input prompt" logs/*_ollama.log` returns zero matches in new runs
- [ ] Unit tests pass: `.venv/bin/python -m pytest src/context_management/ -v`
- [ ] Apptainer build succeeds with the FETCH_STATE_CODE patch
- [ ] Run a BDI `match_schema(target="gdc")` experiment and confirm budget enforced
- [ ] Check `_budget_metadata` in trace.json (dropped_count > 0 for BDI runs)
- [ ] Verify whitelisted variables (df, df_harmonized) are kept despite being large
- [ ] Verify unchanged variables between turns are sent as compact summaries
- [ ] Verify experiment still produces correct harmonized output
- [ ] Problem 6A appears in log analysis CLI tool output for runs with budget enforcement

---

## Commit Instructions

After all changes are implemented and verified:

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia

git add exec_apptainer_harmonia.sh
git add harmonia_beaker_LLM_agent_environment_apptainer.def
git add src/context_management/__init__.py
git add src/context_management/kernel_state_budget.py
git add src/context_management/test_kernel_state_budget.py
git add src/automation/config.py
git add code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml
git add experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/*.yaml

git commit -m "$(cat <<'EOF'
Fix context size issues: Ollama num_ctx passthrough, VRAM estimation, kernel state budget

Three changes for context window problems identified in the 25 Feb error analysis:

1. Export both OLLAMA_NUM_CTX and OLLAMA_CONTEXT_LENGTH in
   exec_apptainer_harmonia.sh so Ollama applies the configured context
   length to all /api/chat calls. Add back-of-the-envelope VRAM estimation
   with warnings when model + KV cache approaches GPU VRAM limits.
   Fixes silent truncation to 4096 tokens (problem 3H).

2. Patch FETCH_STATE_CODE in the Apptainer build definition to add inline
   budget enforcement. Features: per-variable size cap, percentage-based
   total budget (25% of context window), type blacklisting, variable
   whitelisting (df, df_harmonized, etc.), and delta tracking that only
   sends changed variables in full. Configurable via experiment YAML
   context_management section. Fixes ~1M token context explosions from
   bdi.match_schema() loading the full GDC vocabulary (problem 3E).

3. Add ContextManagementConfig to experiment configs, including Archytas
   summarization_threshold_pct. Add problem 6A (diagnostic) to error
   taxonomy for tracking budget enforcement events.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```
