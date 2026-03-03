# WP-C: Provider Prefix Consolidation & generate_jobs.py Overhaul

**Date:** 2026-03-03
**Status:** Complete

## Summary

Consolidated three separate copies of the litellm provider prefix mapping into a single shared module, and overhauled `generate_jobs.py` to match current operational practices.

## Changes Made

### C1: Created `src/bdikit_context/llm/provider_prefixes.py`

New shared module containing the canonical `LITELLM_PROVIDER_PREFIX` dictionary (15 providers). This is the single source of truth for mapping Harmonia provider names to litellm model string prefixes.

### C2: Updated `src/bdikit_context/llm/litellm_model.py`

Replaced the inline `LITELLM_PROVIDER_PREFIX` dict literal (lines 55-74) with:
```python
from .provider_prefixes import LITELLM_PROVIDER_PREFIX
```
No behavioral change -- the dict content is identical.

### C3: Updated `src/bdikit_context/agent.py`

- Added import: `from bdikit_context.llm.provider_prefixes import LITELLM_PROVIDER_PREFIX`
- Replaced the local `provider_prefixes` dict (with trailing slashes) and hardcoded `known_prefixes` tuple in `_build_litellm_model()` with dynamic lookups against the shared table.
- The `known_prefixes` tuple is now built dynamically: `tuple(f"{p}/" for p in set(filter(None, LITELLM_PROVIDER_PREFIX.values())))`.
- The prefix lookup now uses: `LITELLM_PROVIDER_PREFIX.get(base_provider, base_provider)` with format `f"{prefix}/{model}"` (slash added at call site, matching the canonical pattern).

### C4: Updated `src/codeact_context/context.py`

- Added import: `from bdikit_context.llm.provider_prefixes import LITELLM_PROVIDER_PREFIX`
- Removed the local 6-entry `provider_prefixes` dict (which was missing deepseek, mistral, cohere, together, perplexity, fireworks, azure, bedrock).
- Updated model string construction from `f"{prefix}{model}"` (no slash) to `f"{prefix}/{model}"` (with slash), matching the canonical format used by litellm_model.py.
- For `openai` (prefix=None), returns just `model` without prefix, which is correct.

### C5: Overhauled `generate_jobs.py`

1. **Updated DEFAULTS:** time_limit 01:00:00 -> 02:00:00, memory 8G -> 20G, tmpspace 1 -> 50, timeout 300 -> 600.
2. **Associated env auto-detection:** For each config, checks for `<config_stem>_associated.env` in the same directory. If found, uses it instead of the global `--env-file`.
3. **Added `--auto-gpu` / `--no-gpu` flags:** Auto-GPU is enabled by default. When a config's provider is in `LOCAL_LLM_PROVIDERS` (ollama, anyllm:ollama, litellm:ollama, local, anyllm:local), the GPU template is auto-selected. `--no-gpu` disables this. `--gpu` forces GPU template regardless.
4. **Added generation header:** Every generated script gets a comment block with timestamp, source config, template used, and regeneration command.
5. **Removed `--env-file` default of `.env`:** Now defaults to `None` with auto-detection fallback to `.env`.
6. **Updated `generate_job_script` signature:** Added `auto_gpu=True` parameter.
7. **Replaced emoji markers** in output with `[ok]` / `[FAIL]` for better log readability.

### C6: Updated sbatch template comments

In both `sbatch_template.sh` and `sbatch_template_gpu.sh`, replaced "any-llm support" with "litellm support" in the exec_apptainer_harmonia.sh comment block.

## Decisions Made

- **Slash placement:** The canonical format is `f"{prefix}/{model}"` where the slash is added at the call site, not stored in the prefix table. This matches how `litellm_model.py`'s `_build_model_string()` already worked. Both `agent.py` and `context.py` were updated to use this pattern.
- **Unknown provider fallback:** When a provider is not in `LITELLM_PROVIDER_PREFIX`, the fallback is `base_provider` itself (i.e., `LITELLM_PROVIDER_PREFIX.get(base_provider, base_provider)`), so unknown providers produce `provider/model` format. This matches the previous behavior in `agent.py`.
- **`known_prefixes` in agent.py:** Built dynamically from the shared table values rather than being a hardcoded tuple, so new providers added to the shared table are automatically recognized.

## Verification

- All 5 modified/created Python files pass `ast.parse()` syntax checks.
- The shared import `from bdikit_context.llm.provider_prefixes import LITELLM_PROVIDER_PREFIX` works correctly when `PYTHONPATH=src`, loading all 15 providers.

## Files Changed

| File | Action |
|------|--------|
| `src/bdikit_context/llm/provider_prefixes.py` | Created (new shared module) |
| `src/bdikit_context/llm/litellm_model.py` | Modified (replaced dict with import) |
| `src/bdikit_context/agent.py` | Modified (import + refactored _build_litellm_model) |
| `src/codeact_context/context.py` | Modified (import + refactored model string construction) |
| `generate_jobs.py` | Modified (major overhaul) |
| `sbatch_template.sh` | Modified (comment update) |
| `sbatch_template_gpu.sh` | Modified (comment update) |
