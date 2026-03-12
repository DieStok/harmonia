# WP-E: runner.py + config.py Configurable Input Files + LLMConfig Rename

## Implementation Progress

**Status:** Complete
**Date:** 2026-03-03

## Changes Made

### E1: Add `input_files` to `OutputConfig` in `src/automation/config.py`

- Added `input_files: list[str]` field to `OutputConfig` dataclass with default value `["dou.csv", "data.csv", "input.csv"]`
- Updated `ExperimentConfig.from_dict()` to parse `input_files` from the YAML `output:` section, with the same default fallback

This makes the set of input data files configurable per experiment, so experiments 2 and 3 (which use different input files) can declare their own filenames in the config YAML.

### E2: Use `input_files` in `src/automation/runner.py`

- Replaced the hardcoded `data_files = ["dou.csv", "data.csv", "input.csv"]` on line 337 of `_setup_kernel_working_directory()` with `data_files = self.config.output.input_files`
- The runner now reads the file list from the config instead of assuming a fixed set of filenames

### E3: Fix artifact path inconsistency in generation-1 configs

**Analysis of the problem:**
- 12 config YAML files used `"results/dou_harmonized.csv"`, `"results/column_mapping.json"`, and `"results/value_mapping.json"` in their message content (the LLM instructions)
- Generation-2 configs (those with prefixed names like `bdikit-tools_*`, `codeact_*`, `code-context_*`) used bare filenames without the `results/` prefix
- The `results/` prefix is wrong because the runner's `_setup_kernel_working_directory()` already changes the kernel's working directory to the results output folder, so files saved as `"results/dou_harmonized.csv"` would actually end up at `results/<run>/results/dou_harmonized.csv` -- a nested path

**Changes applied to 12 config files:**
- Removed `"results/"` prefix from all three artifact references in message content in all 12 files
- The `save_artifacts` section was already consistent (bare filenames) across all configs -- no changes needed there

**Additionally, 9 configs were missing `context: bdikit_context`:**
- Added `context: bdikit_context` to the `experiment:` section of 9 generation-1 configs that lacked it:
  - `dou_harmonization_anyllm_devstral.yaml`
  - `dou_harmonization_devstral-small.yaml`
  - `dou_harmonization_devstral.yaml`
  - `dou_harmonization_glm-4.5-air.yaml`
  - `dou_harmonization_glm-4.7-flash.yaml`
  - `dou_harmonization_nemotron-3-nano.yaml`
  - `dou_harmonization_olmo3.yaml`
  - `dou_harmonization_qwen3-coder.yaml`
  - `dou_harmonization_step-3.5-flash.yaml`

The 3 remaining configs that had `"results/"` in messages but already had `context:` set (minimax-m2.5, kimi-k2.5, deepseek-v3.2) only needed the path fix.

### E4: Rename `LLMConfig` to `ContainerLLMConfig` in `src/bdikit_context/config/__init__.py`

- Renamed the class from `LLMConfig` to `ContainerLLMConfig` (4 occurrences: class definition, `HarmoniaConfig.llm` type annotation + default_factory, and two constructor calls in `from_env()` and `from_yaml()`)
- Updated the docstring to clarify this is the "container environment" LLM config
- Searched for external references (`from bdikit_context.config import LLMConfig`, `bdikit_context.config.LLMConfig`) -- none found outside the file itself
- This eliminates the naming collision with `automation/config.py:LLMConfig` (the experiment config's LLM settings)

## Decisions Made

1. **Default value for `input_files`:** Used `["dou.csv", "data.csv", "input.csv"]` as default to preserve backward compatibility with existing configs that don't specify `input_files`.

2. **Config classification:** Identified generation-1 configs by two criteria: (a) missing `context:` field, and (b) having `"results/"` prefix in message content. Found that 3 configs (minimax-m2.5, kimi-k2.5, deepseek-v3.2) had `context:` already set but still had the old message format -- these were also fixed.

3. **Context value for generation-1 configs:** Used `bdikit_context` for all 9 because these configs all use the bdikit similarity-based harmonization workflow (they reference `bdikit_models:` section and use `similarity` method in messages).

## Issues Encountered

- The autoformatter/linter repeatedly reverted changes to YAML config files and the Python `__init__.py` file. Required multiple re-applications of the same edits using `replace_all` mode and full file rewrites to get changes to persist.

## Files Modified

**Source code:**
- `src/automation/config.py` -- added `input_files` field to `OutputConfig` and `from_dict()`
- `src/automation/runner.py` -- use `self.config.output.input_files` instead of hardcoded list
- `src/bdikit_context/config/__init__.py` -- renamed `LLMConfig` to `ContainerLLMConfig`

**Experiment configs (12 files, message path fix):**
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_deepseek-v3.2.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral-small.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_glm-4.5-air.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_glm-4.7-flash.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_kimi-k2.5.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_minimax-m2.5.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_nemotron-3-nano.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_olmo3.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_qwen3-coder.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_step-3.5-flash.yaml`

**Experiment configs (9 of the above 12, context field added):**
- All of the above except deepseek-v3.2, kimi-k2.5, minimax-m2.5 (which already had `context:` set)
