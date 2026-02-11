# Local Development Environment

## Overview

This `.venv` provides a **lightweight Python environment** for testing and developing harmonia code **outside the Apptainer container**.

## What's Included

✅ **Your code modules:**
- `bdikit_context` - Beaker contexts, agents, LLM adapters (anyllm)
- `automation` - Experiment runner, config loading, Beaker client
- `code_context` - Code execution context
- `evaluation` - Evaluation schemas and metrics

✅ **Core dependencies:**
- `beaker_kernel>=1.14.0`
- `any-llm-sdk` (with ollama, openai, anthropic support)
- `langchain-core`
- `aiohttp`, `pyyaml`, `pandas`, `pydantic`
- `pytest`, `pytest-asyncio`

❌ **NOT included (use container for these):**
- `bdi-kit` with full ML stack (torch, flair, gensim, etc.)
- Heavy ML model dependencies

## Usage

### Activate the environment

```bash
source activate_local_dev.sh
```

Or manually:
```bash
source .venv/bin/activate
export PYTHONPATH="/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src:$PYTHONPATH"
```

### Test imports

```python
from automation import load_config, ExperimentConfig
from bdikit_context.llm.anyllm import AnyLLMModel, ChatAnyLLM
from code_context.context import CodeContext
```

### Run tests

```bash
pytest src/  # (if you add tests)
```

### Interactive development

```bash
python  # Start Python REPL
>>> from automation import load_config
>>> config = load_config('experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_deepseek.yaml')
>>> print(config)
```

## Limitations

1. **bdikit ML features unavailable**: Schema matching, value matching, and other ML-heavy bdikit features require the full dependency stack in the container.

2. **BDIKitContext cannot execute procedures**: Procedures like `match_schema`, `match_values` require torch and other ML libraries.

3. **Container still needed for experiments**: All LLM experiments should run in the Apptainer container as documented.

## Purpose

This environment is for:
- **Testing automation code** (config loading, experiment setup)
- **Developing LLM adapters** (AnyLLMModel, ChatAnyLLM)
- **Interactive exploration** of config files and experiment structure
- **Unit testing** non-ML components

## Disk Space

The `.venv` and `.uv_cache` directories are excluded from git (see `.gitignore`).

To clean up:
```bash
rm -rf .venv .uv_cache
```

## Troubleshooting

**Problem:** Import errors for bdikit functions
- **Solution:** Use the container for full bdikit functionality

**Problem:** Disk space errors during installation
- **Solution:** The current .venv is already set up with core dependencies

**Problem:** Missing packages
- **Solution:** Install with uv:
  ```bash
  source .venv/bin/activate
  export UV_CACHE_DIR=/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/.uv_cache
  uv pip install <package>
  ```
