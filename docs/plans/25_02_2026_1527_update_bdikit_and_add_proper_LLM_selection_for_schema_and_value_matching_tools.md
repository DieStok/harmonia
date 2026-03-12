# Plan: Update bdi-kit to v0.9 and Add Configurable LLM Selection for Schema/Value Matching

**Date:** 25 February 2026
**Status:** Ready for implementation

## 1. Problem Statement

Harmonia's bdi-kit dependency is pinned to a very old WIP commit (`41f6c26`, version `0.5.0.dev0`) that:
- Has no `llm`, `llm_numeric`, `magneto_zs_llm`, `magneto_ft_llm` methods (only `gpt`)
- Uses hardcoded OpenAI calls (no litellm, no flexible model selection)
- Has a different internal structure (`bdikit.schema_matching.one2one.*` vs `bdikit.schema_matching.*`)
- Uses `column_mapping` parameter name (v0.9 renamed it to `attribute_matches`)

Additionally, when the agent uses LLM-based schema/value matching methods, there is no way to configure which LLM model bdi-kit uses internally. The model defaults to `openai/gpt-4o-mini` and cannot be overridden from experiment config.

## 2. Goals

1. **Upgrade bdi-kit from 0.5.0.dev0 to v0.9.0** in `pyproject.toml`
2. **Fix all breaking API changes** in Harmonia code (parameter names, method names, imports)
3. **Add 6 new HARMONIA_* env vars** to control which LLM bdi-kit uses for each matching method
4. **Wire env vars end-to-end:** YAML config -> generate_env.py -> exec_apptainer_harmonia.sh -> container -> agent code -> bdi-kit procedure templates
5. **Rebuild the Apptainer container**

## 3. Context: Two Separate LLM Integration Points

**Critical distinction:** Harmonia has two separate LLM integration points:

| Integration Point | Library | Purpose |
|---|---|---|
| **Top-level agent** (Beaker/Archytas) | any-llm-sdk (via `AnyLLMModel`) | The AI agent that reasons, calls tools, talks to user |
| **bdi-kit internal** (schema/value matching) | litellm (inside bdi-kit v0.9) | LLM calls within `method="llm"`, `magneto_*_llm`, etc. |

This plan only touches the **bdi-kit internal** side. The top-level agent's LLM backend is addressed in a separate plan.

## 4. Current State (Container: bdi-kit 0.5.0.dev0)

### 4.1 Installed version
- Pinned in `pyproject.toml` line 25: `"bdi-kit @ git+https://github.com/VIDA-NYU/bdi-kit.git@41f6c26e66064dd2aa6b436c023c98e4a96d1b5e"`
- Container reports: `bdi-kit: 0.5.0.dev0`
- Schema matchers available: `similarity_flooding, coma, cupid, distribution_based, jaccard_distance, gpt, ct_learning, two_phase, max_val_sim`
- Value matchers available: `tfidf, edit_distance, embedding, fasttext, gpt`
- Internal structure: `bdikit.schema_matching.one2one.*`, `bdikit.value_matching.*`

### 4.2 API signatures in container
```python
match_schema(source, target='gdc', method='coma', method_args=None)
match_values(source, target, column_mapping, method='tfidf', method_args=None)
```

### 4.3 Agent code (agent.py) currently lists methods that DON'T EXIST in the container
```python
VALID_SCHEMA_METHODS = [
    "similarity_flooding", "coma", "cupid", "distribution_based",
    "jaccard_distance", "two_phase", "max_val_sim",
    "magneto_zs_bp", "magneto_ft_bp",  # NOT in v0.5
    "magneto_zs_llm", "magneto_ft_llm",  # NOT in v0.5
    "llm"  # NOT in v0.5 (only "gpt" exists)
]
VALID_VALUE_METHODS = ["edit_distance", "llm", "llm_numeric", "tfidf", "embedding"]
# "llm" and "llm_numeric" NOT in v0.5 (only "gpt" exists)
```

## 5. Target State (bdi-kit v0.9.0)

### 5.1 API signatures in v0.9
```python
match_schema(source, target='gdc', method='magneto_ft_bp', method_args=None, standard_args=None, use_cache=True)
match_values(source, target, attribute_matches, method='tfidf', source_context=None, target_context=None, method_args=None, standard_args=None, output_format='dataframe', use_cache=True)
```

### 5.2 Available methods in v0.9
**Schema matchers:** `similarity_flooding, coma, cupid, distribution_based, jaccard_distance, two_phase, max_val_sim, magneto_zs_bp, magneto_ft_bp, magneto_zs_llm, magneto_ft_llm, llm`

**Value matchers:** `tfidf, edit_distance, embedding, fasttext, llm, llm_numeric`

### 5.3 How LLM model names are passed in v0.9
bdi-kit v0.9 uses **litellm** internally. Model names are passed via `method_args`:

```python
# Schema matching with LLM
bdi.match_schema(df, target="gdc", method="llm", method_args={"model_name": "openai/gpt-4o-mini"})
bdi.match_schema(df, target="gdc", method="magneto_ft_llm", method_args={"reranker_model": "openai/gpt-4o-mini"})

# Value matching with LLM
bdi.match_values(df, target, attr_matches, method="llm", method_args={"model_name": "openai/gpt-4o-mini"})
bdi.match_values(df, target, attr_matches, method="llm_numeric", method_args={"model_name": "openai/gpt-4o-mini"})
bdi.match_values(df, target, attr_matches, method="embedding", method_args={"model_name": "bert-base-multilingual-cased"})
```

### 5.4 Key breaking changes from v0.5 to v0.9
| Aspect | v0.5.0.dev0 | v0.9.0 |
|---|---|---|
| `match_values` param | `column_mapping` | `attribute_matches` |
| LLM schema method name | `gpt` | `llm` |
| LLM value method name | `gpt` | `llm` |
| Magneto methods | not present | `magneto_zs_bp`, `magneto_ft_bp`, `magneto_zs_llm`, `magneto_ft_llm` |
| `llm_numeric` value method | not present | present |
| LLM backend | hardcoded OpenAI | litellm (any provider via `model_name`) |
| Default schema method | `coma` | `magneto_ft_bp` |
| Matcher factory | `SchemaMatchers` enum | `get_schema_matcher()` function |
| Internal package structure | `bdikit.schema_matching.one2one.*` | `bdikit.schema_matching.*` |

### 5.5 two_phase matcher and LLM sub-methods
In v0.9, `TwoPhase` accepts `top_k_matcher` and `schema_matcher` as constructor kwargs:
```python
TwoPhase(
    top_k=20,
    top_k_matcher=MagnetoFTBP(),  # default, non-LLM
    schema_matcher=SimFlood(),     # default, non-LLM
)
```
These sub-matchers CAN be LLM-based classes, but by design we let `two_phase` use its **non-LLM defaults** unless the user explicitly constructs sub-matchers. The HARMONIA_LLM_* vars only apply when the agent explicitly requests an LLM-based method name.

## 6. New Environment Variables

Six new `HARMONIA_*` env vars control which LLM bdi-kit uses internally:

| Env Var | Controls | bdi-kit `method_args` key | Default |
|---|---|---|---|
| `HARMONIA_LLM_FOR_INSTANCE_MATCHING` | value matching `llm` method | `model_name` | `$LLM_SERVICE_MODEL` |
| `HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING` | value matching `llm_numeric` | `model_name` | `$LLM_SERVICE_MODEL` |
| `HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING` | value matching `embedding` | `model_name` | `bert-base-multilingual-cased` |
| `HARMONIA_LLM_FOR_SCHEMA_MATCHING` | schema matching `llm` | `model_name` | `$LLM_SERVICE_MODEL` |
| `HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING` | schema matching `magneto_zs_llm` | `reranker_model` | `$LLM_SERVICE_MODEL` |
| `HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING` | schema matching `magneto_ft_llm` | `reranker_model` | `$LLM_SERVICE_MODEL` |


**Note:** The embedding model defaults to bdi-kit's built-in default (`bert-base-multilingual-cased`) rather than `LLM_SERVICE_MODEL`, since it's not an LLM but a sentence-transformer model.

## 7. Implementation Steps

### Step 1: Update `pyproject.toml` — pin to bdi-kit v0.9.0

**File:** `harmonia_metadata_agent/analysis/dstoker/harmonia/pyproject.toml`

**Change line 25 from:**
```
"bdi-kit @ git+https://github.com/VIDA-NYU/bdi-kit.git@41f6c26e66064dd2aa6b436c023c98e4a96d1b5e",
```
**To:**
```
"bdi-kit @ git+https://github.com/VIDA-NYU/bdi-kit.git@v0.9.0",
```

Also add litellm as an explicit dependency (bdi-kit v0.9 requires it, but we want it available in the container for the HARMONIA_LLM_* env vars to work with litellm's provider format):
```
"litellm",
```

### Step 2: Update `agent.py` — fix method names and parameter

**File:** `harmonia_metadata_agent/analysis/dstoker/harmonia/src/bdikit_context/agent.py`

#### 2a. Update VALID_SCHEMA_METHODS and default
The method list is already correct for v0.9 (it was written for v0.9 but the container had v0.5). Verify and keep:
```python
VALID_SCHEMA_METHODS = [
    "similarity_flooding", "coma", "cupid", "distribution_based",
    "jaccard_distance", "two_phase", "max_val_sim",
    "magneto_zs_bp", "magneto_ft_bp",
    "magneto_zs_llm", "magneto_ft_llm", "llm"
]
DEFAULT_SCHEMA_METHOD = "magneto_ft_bp"
```

#### 2b. Update VALID_VALUE_METHODS
Already correct for v0.9. Verify and keep:
```python
VALID_VALUE_METHODS = ["edit_distance", "llm", "llm_numeric", "tfidf", "embedding"]
DEFAULT_VALUE_METHOD = "tfidf"
```

#### 2c. Add method_args construction logic
Add a helper function that reads the HARMONIA_LLM_* env vars and constructs the appropriate `method_args` dict for a given method:

```python
import os

def _get_method_args_for_schema(method: str) -> dict:
    """Build method_args dict for schema matching based on HARMONIA_* env vars."""
    fallback = os.environ.get("LLM_SERVICE_MODEL", "openai/gpt-4o-mini")
    if method == "llm":
        model = os.environ.get("HARMONIA_LLM_FOR_SCHEMA_MATCHING", fallback)
        return {"model_name": model}
    elif method == "magneto_zs_llm":
        model = os.environ.get("HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING", fallback)
        return {"reranker_model": model}
    elif method == "magneto_ft_llm":
        model = os.environ.get("HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING", fallback)
        return {"reranker_model": model}
    return {}

def _get_method_args_for_values(method: str) -> dict:
    """Build method_args dict for value matching based on HARMONIA_* env vars."""
    fallback = os.environ.get("LLM_SERVICE_MODEL", "openai/gpt-4o-mini")
    if method == "llm":
        model = os.environ.get("HARMONIA_LLM_FOR_INSTANCE_MATCHING", fallback)
        return {"model_name": model}
    elif method == "llm_numeric":
        model = os.environ.get("HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING", fallback)
        return {"model_name": model}
    elif method == "embedding":
        model = os.environ.get("HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING", "bert-base-multilingual-cased")
        return {"model_name": model}
    return {}
```

#### 2d. Update match_schema tool to pass method_args
In `match_schema()`, change the `get_code()` call to include `method_args`:

```python
method_args = _get_method_args_for_schema(method)
code = agent.context.get_code(
    "match_schema",
    {
        "dataset": dataset,
        "target": target,
        "method": method,
        "method_args": method_args,
    },
)
```

#### 2e. Update match_values tool to pass method_args
In `match_values()`, change the `get_code()` call to include `method_args`:

```python
method_args = _get_method_args_for_values(method)
code = agent.context.get_code(
    "match_values",
    {
        "dataset": dataset,
        "column_mapping": tuple(column_mapping.split(',')),
        "target": target,
        "method": method,
        "method_args": method_args,
    },
)
```

### Step 3: Update procedure templates

#### 3a. Update `match_schema.py` template
**File:** `harmonia_metadata_agent/analysis/dstoker/harmonia/src/bdikit_context/procedures/python3/match_schema.py`

**From:**
```python
import bdikit as bdi
column_mappings = bdi.match_schema({{ dataset }}, target="{{ target }}", method="{{ method }}")
column_mappings.to_markdown()
```

**To:**
```python
import bdikit as bdi
column_mappings = bdi.match_schema({{ dataset }}, target="{{ target }}", method="{{ method }}"{% if method_args %}, method_args={{ method_args }}{% endif %})
column_mappings.to_markdown()
```

#### 3b. Update `match_values.py` template
**File:** `harmonia_metadata_agent/analysis/dstoker/harmonia/src/bdikit_context/procedures/python3/match_values.py`

**From:**
```python
import bdikit as bdi
value_mappings = bdi.match_values({{ dataset }}, column_mapping={{ column_mapping }}, target="{{ target }}", method="{{ method }}")
value_mappings.to_markdown()
```

**To:**
```python
import bdikit as bdi
value_mappings = bdi.match_values({{ dataset }}, attribute_matches={{ column_mapping }}, target="{{ target }}", method="{{ method }}"{% if method_args %}, method_args={{ method_args }}{% endif %})
value_mappings.to_markdown()
```

**Note:** `column_mapping` is renamed to `attribute_matches` in the bdi-kit API call, but the Jinja2 template variable `{{ column_mapping }}` can keep its name since it holds the same data (the tuple of source/target column names).

### Step 4: Update `generate_env.py`

**File:** `harmonia_metadata_agent/analysis/dstoker/harmonia/generate_env.py`

Add handling for the new `bdikit_models` config section. After the prompts handling block (around line 166), add:

```python
# Handle bdikit_models configuration (LLMs used by bdi-kit for schema/value matching)
bdikit_models = config.get('bdikit_models', {})
bdikit_model_vars = {
    'instance_matching_llm': 'HARMONIA_LLM_FOR_INSTANCE_MATCHING',
    'numeric_instance_matching_llm': 'HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING',
    'embedding_model_for_instance_matching': 'HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING',
    'schema_matching_llm': 'HARMONIA_LLM_FOR_SCHEMA_MATCHING',
    'magneto_zero_shot_schema_matching_llm': 'HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING',
    'magneto_fine_tuned_schema_matching_llm': 'HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING',
}
for yaml_key, env_var in bdikit_model_vars.items():
    value = bdikit_models.get(yaml_key)
    if value:
        env_content = update_env_value(env_content, env_var, value)
```

### Step 5: Update `exec_apptainer_harmonia.sh`

**File:** `harmonia_metadata_agent/analysis/dstoker/harmonia/exec_apptainer_harmonia.sh`

#### 5a. Read and log the new env vars (after line 248)
After reading LLM_PROVIDER and LLM_MODEL from the .env file, add:

```bash
# Read bdi-kit LLM configuration from .env for display
BDIKIT_LLM_INSTANCE=$(grep "^HARMONIA_LLM_FOR_INSTANCE_MATCHING=" "$ENV_FILE" | cut -d '=' -f2)
BDIKIT_LLM_NUMERIC=$(grep "^HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING=" "$ENV_FILE" | cut -d '=' -f2)
BDIKIT_EMBEDDING=$(grep "^HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING=" "$ENV_FILE" | cut -d '=' -f2)
BDIKIT_LLM_SCHEMA=$(grep "^HARMONIA_LLM_FOR_SCHEMA_MATCHING=" "$ENV_FILE" | cut -d '=' -f2)
BDIKIT_LLM_MAGNETO_ZS=$(grep "^HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING=" "$ENV_FILE" | cut -d '=' -f2)
BDIKIT_LLM_MAGNETO_FT=$(grep "^HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING=" "$ENV_FILE" | cut -d '=' -f2)
```

#### 5b. Print them in the startup display
Add a section to display the bdi-kit LLM config (near the existing LLM display):

```bash
# Display bdi-kit LLM configuration if any are set
if [ -n "$BDIKIT_LLM_INSTANCE" ] || [ -n "$BDIKIT_LLM_SCHEMA" ]; then
    echo ""
    echo "BDI-Kit Internal LLM Configuration:"
    [ -n "$BDIKIT_LLM_INSTANCE" ] && echo "   Instance matching LLM:          $BDIKIT_LLM_INSTANCE"
    [ -n "$BDIKIT_LLM_NUMERIC" ] && echo "   Numeric instance matching LLM:   $BDIKIT_LLM_NUMERIC"
    [ -n "$BDIKIT_EMBEDDING" ] && echo "   Embedding model:                 $BDIKIT_EMBEDDING"
    [ -n "$BDIKIT_LLM_SCHEMA" ] && echo "   Schema matching LLM:             $BDIKIT_LLM_SCHEMA"
    [ -n "$BDIKIT_LLM_MAGNETO_ZS" ] && echo "   Magneto zero-shot LLM:           $BDIKIT_LLM_MAGNETO_ZS"
    [ -n "$BDIKIT_LLM_MAGNETO_FT" ] && echo "   Magneto fine-tuned LLM:          $BDIKIT_LLM_MAGNETO_FT"
else
    echo ""
    echo "BDI-Kit Internal LLM Configuration: (defaults - using top-level LLM: $LLM_MODEL)"
fi
```

#### 5c. Include in .experiment_id JSON
Add the bdi-kit model config to the `.experiment_id` JSON file (around line 290):

```json
  "bdikit_llm_instance_matching": "${BDIKIT_LLM_INSTANCE:-$LLM_MODEL}",
  "bdikit_llm_schema_matching": "${BDIKIT_LLM_SCHEMA:-$LLM_MODEL}",
```

### Step 6: Update `prompt_logging.py`

**File:** `harmonia_metadata_agent/analysis/dstoker/harmonia/src/prompt_logging.py`

Add the new HARMONIA_LLM_* vars to the logged env vars in `print_prompt_composition()` (around line 85) and `build_prompt_composition_log()` (around line 142):

```python
"HARMONIA_LLM_FOR_INSTANCE_MATCHING": os.environ.get("HARMONIA_LLM_FOR_INSTANCE_MATCHING"),
"HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING": os.environ.get("HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING"),
"HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING": os.environ.get("HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING"),
"HARMONIA_LLM_FOR_SCHEMA_MATCHING": os.environ.get("HARMONIA_LLM_FOR_SCHEMA_MATCHING"),
"HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING": os.environ.get("HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING"),
"HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING": os.environ.get("HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING"),
```

### Step 7: Update experiment YAML configs

**Directory:** `harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc/configs/`

Add a new optional `bdikit_models` section to YAML configs. Example:

```yaml
# Optional: override which LLMs bdi-kit uses internally for matching.
# If not specified, all default to the top-level llm.model value.
bdikit_models:
  instance_matching_llm: openai/gpt-4o-mini
  numeric_instance_matching_llm: openai/gpt-4o-mini
  # embedding_model_for_instance_matching: bert-base-multilingual-cased  # default
  schema_matching_llm: openai/gpt-4o-mini
  magneto_zero_shot_schema_matching_llm: openai/gpt-4o-mini
  magneto_fine_tuned_schema_matching_llm: openai/gpt-4o-mini
```

Since the default falls back to `LLM_SERVICE_MODEL`, existing configs without this section will continue to work unchanged — the agent's top-level LLM will be used for bdi-kit's internal calls too.

### Step 8: Rebuild the Apptainer container

```bash
srun -J apptainer_build_claude-code --time=02:00:00 --mem=40G --gres=tmpspace:100G bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
./build_harmonia_apptainer.sh
```

### Step 9: Verify the container

After rebuild, verify:

```bash
srun -J verify_claude-code --time=00:15:00 --mem=10G bash -c "
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
apptainer exec harmonia_beaker_LLM_agent_environment_apptainer.sif python3 -c '
import bdikit
print(\"bdikit version:\", bdikit.__version__)

import inspect, bdikit.api as api
print(\"match_schema sig:\", inspect.signature(api.match_schema))
print(\"match_values sig:\", inspect.signature(api.match_values))

# Verify LLM matchers exist
from bdikit.schema_matching.llm import LLM
print(\"LLM schema matcher:\", inspect.signature(LLM.__init__))

from bdikit.value_matching.llm import LLM as VLLM
print(\"LLM value matcher:\", inspect.signature(VLLM.__init__))

from bdikit.schema_matching.magneto import MagnetoFTLLM, MagnetoZSLLM
print(\"MagnetoFTLLM:\", inspect.signature(MagnetoFTLLM.__init__))
print(\"MagnetoZSLLM:\", inspect.signature(MagnetoZSLLM.__init__))

# Verify litellm is available
import litellm
print(\"litellm version:\", litellm.__version__)

# Verify HARMONIA_* env vars are readable
import os
for var in [\"HARMONIA_LLM_FOR_INSTANCE_MATCHING\", \"HARMONIA_LLM_FOR_SCHEMA_MATCHING\"]:
    print(f\"{var}: {os.environ.get(var, \"(not set)\")}\"  )
'
"
```

## 8. Files Changed Summary

| File | Change Type | Description |
|---|---|---|
| `pyproject.toml` | Edit | Pin bdi-kit to v0.9.0, add litellm dependency |
| `src/bdikit_context/agent.py` | Edit | Add `_get_method_args_for_schema()`, `_get_method_args_for_values()` helpers; update `match_schema()` and `match_values()` to pass `method_args` |
| `src/bdikit_context/procedures/python3/match_schema.py` | Edit | Add `method_args` parameter, use Jinja2 conditional |
| `src/bdikit_context/procedures/python3/match_values.py` | Edit | Rename `column_mapping` to `attribute_matches` in API call, add `method_args` |
| `generate_env.py` | Edit | Add `bdikit_models` config section handling |
| `exec_apptainer_harmonia.sh` | Edit | Read, display, and log the 6 new HARMONIA_* env vars |
| `src/prompt_logging.py` | Edit | Log the 6 new HARMONIA_* env vars |
| `experiments/.../configs/**/*.yaml` | Edit (optional) | Add `bdikit_models:` section |
| Container `.sif` | Rebuild | Rebuild with new bdi-kit version |

## 9. Testing Plan

1. **Unit: method_args construction** — verify `_get_method_args_for_schema("llm")` returns `{"model_name": value}` and `_get_method_args_for_schema("coma")` returns `{}`
2. **Unit: generate_env.py** — verify a config with `bdikit_models:` section produces correct env vars in the output .env file
3. **Integration: container build** — verify bdi-kit v0.9 is installed and all imports succeed
4. **Integration: end-to-end** — run a manual experiment using `method="llm"` for schema matching and verify the correct model is used (check litellm debug output)

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| bdi-kit v0.9 has new dependencies that conflict with beaker_kernel | Check dependency resolution during container build; pin specific versions if needed |
| litellm needs API keys for cloud providers | API keys are already passed via .env files; litellm reads standard env vars (OPENAI_API_KEY etc.) |
| Old configs break because method names changed | VALID_SCHEMA_METHODS was already written for v0.9; the only actual API break is `column_mapping` -> `attribute_matches` in the procedure template |
| Container rebuild takes ~1 hour | Build can run in parallel with code changes; backup existing .sif before rebuild |

## 11. Execution Order

Steps 1-7 can all be done **before** the container rebuild (Step 8). The code changes are to the source files that get copied into the container at build time.

Recommended parallel execution:
1. Do Steps 1-7 (code changes) first
2. Start Step 8 (container rebuild) as a background SLURM job
3. While container builds, review the code changes and prepare test configs
4. When build completes, run Step 9 (verification)
