# Plan: Fix OpenRouter API Calls Going to OpenAI

**Date**: 2026-01-13
**Status**: Diagnosing root cause

---

## Problem Statement

Despite setting `LLM_SERVICE_PROVIDER=openrouter` in `.env` and fixing the `setdefault` issue in `src/bdikit_context/llm/__init__.py`, the LLM requests are still being sent to OpenAI's endpoint instead of OpenRouter.

**Error Evidence:**
```
openai.AuthenticationError: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-or-v1...339c. You can find your API key at https://platform.openai.com/account/api-keys.'
```

The OpenRouter API key (`sk-or-v1-...`) is being sent to `api.openai.com` instead of `openrouter.ai`.

---

## Architecture Analysis

### Control Flow for LLM Model Selection

1. **Beaker Server Startup** (`exec_apptainer_harmonia.sh`):
   - Loads `.env` via `--env-file .env`
   - Environment variables set in container

2. **Beaker-kernel Config** (`beaker_kernel/lib/config.py`):
   - `config = Config()` - Lazy loading wrapper (line 14379)
   - `ConfigClass` fields use `configfield()` which reads env vars via `os.getenv()` at instantiation time
   - Key fields:
     - `model_provider_import_path` ← `LLM_PROVIDER_IMPORT_PATH`
     - `model_name` ← `LLM_SERVICE_MODEL`
     - `llm_service_token` ← `LLM_SERVICE_TOKEN`

3. **Context Package Import** (`src/bdikit_context/__init__.py`):
   - `configure_llm_environment()` called on package import
   - Sets environment variables

4. **BeakerAgent Initialization** (`beaker_kernel/lib/agent.py` line 17617):
   ```python
   model = config.get_model()
   ```
   - Calls `config.get_model()` which:
     1. Gets provider config from `self.providers.get(self.provider, {})`
     2. Overrides with `self.model_provider_import_path` if set
     3. Creates model from import path

### CRITICAL TIMING ISSUE

The beaker-kernel's `config` is a **lazy-loading singleton**. When any attribute is accessed:
1. If `config_obj` is None, it calls `ConfigClass.from_config_file()`
2. `from_config_file()` calls `dotenv.load_dotenv()` then creates instance
3. `configfield()` reads env vars via `os.getenv()` **at that moment**

**The Problem**: The `config` singleton may be accessed (and thus instantiated) **BEFORE** `bdikit_context.__init__` runs `configure_llm_environment()`.

---

## Three Hypotheses

### Hypothesis 1: Timing - Config Loaded Before Environment Set

**Theory**: The beaker-kernel `config` object is instantiated BEFORE `src/bdikit_context/__init__.py` calls `configure_llm_environment()`.

**Evidence Supporting This**:
- The beaker server imports `beaker_kernel` modules first
- `config` is accessed when BeakerAgent is created
- The bdikit_context is loaded later when the context is selected

**Test Plan**:
1. Add debug prints to `configure_llm_environment()` to show when it runs
2. Add debug prints to check `os.environ.get("LLM_PROVIDER_IMPORT_PATH")` before/after
3. Check if `config.config_obj` is already set when bdikit_context loads

### Hypothesis 2: Cached Config Object Not Refreshed

**Theory**: Even if env vars are set, the `config.config_obj` is already instantiated and cached, so it uses stale values.

**Evidence**:
- `Config` is a singleton created at module load (`config = Config()`)
- Once `config_obj` is set, it's never re-read
- `configure_llm_environment()` sets env vars but doesn't reset the config

**Test Plan**:
1. Check `config.config_obj` value in a diagnostic script
2. Compare `config.model_provider_import_path` vs `os.environ.get("LLM_PROVIDER_IMPORT_PATH")`
3. Call `beaker_kernel.lib.config.reset_config()` after setting env vars

### Hypothesis 3: Wrong Import Path for OpenRouter

**Theory**: The import path `archytas.models.openrouter.OpenRouterModel` doesn't exist or isn't being used correctly.

**Evidence**:
- Archytas uses OpenAI SDK client by default
- OpenRouter might need special base_url configuration

**Test Plan**:
1. Verify `archytas.models.openrouter` module exists in container
2. Check if OpenRouterModel sets base_url to `https://openrouter.ai/api/v1`
3. Verify the import path is correct

---

## Diagnostic Script

Create `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/diagnose_llm.py`:

```python
#!/usr/bin/env python3
"""Diagnostic script to debug LLM provider configuration."""

import os
import sys

def main():
    print("=" * 60)
    print("LLM Provider Diagnostic Script")
    print("=" * 60)

    # Step 1: Check environment variables BEFORE any imports
    print("\n[1] Environment variables BEFORE imports:")
    print(f"    LLM_SERVICE_PROVIDER:     {os.environ.get('LLM_SERVICE_PROVIDER', 'NOT SET')}")
    print(f"    LLM_PROVIDER_IMPORT_PATH: {os.environ.get('LLM_PROVIDER_IMPORT_PATH', 'NOT SET')}")
    print(f"    LLM_SERVICE_MODEL:        {os.environ.get('LLM_SERVICE_MODEL', 'NOT SET')}")
    print(f"    LLM_SERVICE_TOKEN:        {os.environ.get('LLM_SERVICE_TOKEN', 'NOT SET')[:20]}..." if os.environ.get('LLM_SERVICE_TOKEN') else "    LLM_SERVICE_TOKEN:        NOT SET")
    print(f"    OPENROUTER_API_KEY:       {os.environ.get('OPENROUTER_API_KEY', 'NOT SET')[:20]}..." if os.environ.get('OPENROUTER_API_KEY') else "    OPENROUTER_API_KEY:       NOT SET")

    # Step 2: Import beaker-kernel config and check if already loaded
    print("\n[2] Importing beaker_kernel.lib.config...")
    from beaker_kernel.lib.config import config, reset_config

    print(f"    config.config_obj is None: {config.config_obj is None}")

    # Step 3: Check config values (this will trigger lazy load if needed)
    print("\n[3] Accessing config values (triggers lazy load):")
    print(f"    config.provider:                  {config.provider}")
    print(f"    config.model_provider_import_path: {config.model_provider_import_path}")
    print(f"    config.model_name:                 {config.model_name}")
    print(f"    config.llm_service_token:          {config.llm_service_token[:20]}..." if config.llm_service_token else "    config.llm_service_token:          NOT SET")

    # Step 4: Check environment AFTER config load
    print("\n[4] Environment variables AFTER config load:")
    print(f"    LLM_PROVIDER_IMPORT_PATH: {os.environ.get('LLM_PROVIDER_IMPORT_PATH', 'NOT SET')}")

    # Step 5: Import bdikit_context (this calls configure_llm_environment)
    print("\n[5] Importing bdikit_context (runs configure_llm_environment)...")
    import bdikit_context

    # Step 6: Check environment AFTER bdikit_context import
    print("\n[6] Environment variables AFTER bdikit_context import:")
    print(f"    LLM_PROVIDER_IMPORT_PATH: {os.environ.get('LLM_PROVIDER_IMPORT_PATH', 'NOT SET')}")
    print(f"    LLM_SERVICE_MODEL:        {os.environ.get('LLM_SERVICE_MODEL', 'NOT SET')}")
    print(f"    LLM_SERVICE_TOKEN:        {os.environ.get('LLM_SERVICE_TOKEN', 'NOT SET')[:20]}..." if os.environ.get('LLM_SERVICE_TOKEN') else "    LLM_SERVICE_TOKEN:        NOT SET")

    # Step 7: Check if config reflects the new values (it won't - it's cached!)
    print("\n[7] Config values AFTER bdikit_context (cached - won't change!):")
    print(f"    config.model_provider_import_path: {config.model_provider_import_path}")
    print(f"    config.model_name:                 {config.model_name}")

    # Step 8: Try resetting config
    print("\n[8] Resetting config and re-checking:")
    reset_config()
    print(f"    config.config_obj is None after reset: {config.config_obj is None}")
    print(f"    config.model_provider_import_path: {config.model_provider_import_path}")
    print(f"    config.model_name:                 {config.model_name}")

    # Step 9: Test get_model()
    print("\n[9] Testing config.get_model():")
    model = config.get_model()
    print(f"    Model type: {type(model)}")
    print(f"    Model class: {model.__class__.__name__}")
    if hasattr(model, 'model_name'):
        print(f"    Model name: {model.model_name}")
    if hasattr(model, 'base_url'):
        print(f"    Base URL: {model.base_url}")

    # Step 10: Check if archytas OpenRouter model exists
    print("\n[10] Checking archytas.models.openrouter:")
    try:
        from archytas.models.openrouter import OpenRouterModel
        print(f"    OpenRouterModel found: {OpenRouterModel}")
        # Check if it has base_url
        import inspect
        sig = inspect.signature(OpenRouterModel.__init__)
        print(f"    __init__ parameters: {list(sig.parameters.keys())}")
    except ImportError as e:
        print(f"    ERROR: {e}")

    print("\n" + "=" * 60)
    print("DIAGNOSIS COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
```

---

## ACTUAL Root Cause (Discovered via Diagnostics)

**The container has OLD versions of beaker_kernel and archytas that don't support multiple LLM providers!**

### Version Analysis

| Package | Container Version | Latest Version | Multi-Provider Support |
|---------|-------------------|----------------|------------------------|
| beaker_kernel | 1.6.2 | 1.14.0 | Only in >= 1.10+ |
| archytas | (old) | (new) | Only in newer versions |

### Key Findings from Diagnostics

1. **Container's archytas** does NOT have `archytas.models` module at all
2. **Container's ReActAgent** takes `model: str` as just a model name (hardcoded to OpenAI)
3. **Container's BeakerAgent** uses `self.MODEL` (a string) not `config.get_model()`
4. **No OpenRouterModel class exists** in the container's archytas

### Why OpenAI is Called

The old archytas `ReActAgent.__init__` signature:
```python
def __init__(self, *, model: str = 'gpt-4-1106-preview', api_key: str | None = None, ...)
```

It directly uses the OpenAI client internally - there's no provider abstraction!

---

## Required Fix: Rebuild Container

The ONLY solution is to update the container with newer package versions.

### Changes Made to pyproject.toml

```toml
# Before:
dependencies = [
  "beaker_kernel~=1.6.2",
  ...
]

# After:
dependencies = [
  # Updated to 1.14+ for multi-provider LLM support (get_model, providers config)
  "beaker_kernel>=1.14.0",
  ...
]
requires-python = ">=3.10"  # Updated from >=3.8
```

### Rebuild Steps

1. Get a compute node with enough scratch space:
   ```bash
   srun --mem 20G --time 04:00:00 --gres=tmpspace:35G --pty bash
   ```

2. Navigate to harmonia directory:
   ```bash
   cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
   ```

3. Run the build script:
   ```bash
   ./build_apptainer.sh
   ```

4. Wait for build to complete (may take 15-30 minutes)

5. Test the new container:
   ```bash
   apptainer exec --bind .:/jupyter --pwd /jupyter --env-file .env jupyter.sif python check_archytas.py
   ```

---

## Files Modified

| File | Change |
|------|--------|
| `pyproject.toml` | Updated beaker_kernel to >=1.14.0, Python to >=3.10 |
| `src/bdikit_context/__init__.py` | Added `reset_config()` call (for future-proofing) |
| `.env` | Added `LLM_SERVICE_TOKEN` and `LLM_PROVIDER_IMPORT_PATH` |

## Files Created

| File | Purpose |
|------|---------|
| `diagnose_llm.py` | Diagnostic script |
| `quick_test.py` | Quick verification script |
| `check_archytas.py` | Check archytas version/features |

---

## Verification Steps (After Rebuild)

1. Run `check_archytas.py` to verify OpenRouterModel exists
2. Run `quick_test.py` to verify config loads correctly
3. Start Beaker server and run experiment:
   ```bash
   ./exec_apptainer_harmonia.sh &
   sleep 30
   python run_experiment.py --config experiments/configs/dou_harmonization.yaml --token 89f73481102c46c0bc13b2998f9a4fce
   ```
4. Verify no OpenAI 401 errors in output
