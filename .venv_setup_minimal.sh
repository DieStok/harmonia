#!/bin/bash
# Minimal .venv setup for local testing (WITHOUT heavy ML dependencies)
# Use this for testing automation, config, LLM adapters
# For full bdikit functionality, use the Apptainer container

cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
export UV_CACHE_DIR=/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/.uv_cache
export TMPDIR=/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/.tmp
mkdir -p $UV_CACHE_DIR $TMPDIR

source .venv/bin/activate

echo "=== Installing core runtime dependencies (no ML) ==="
uv pip install \
    'beaker_kernel>=1.14.0' \
    'jinja2>=3.0' \
    'pyyaml>=6.0' \
    'aiohttp>=3.8' \
    'pandas' \
    'pydantic' \
    'langchain-core' \
    'pytest' \
    'pytest-asyncio'

echo "=== Installing any-llm-sdk (lightweight) ==="
uv pip install 'any-llm-sdk[ollama,openai,anthropic] @ git+https://github.com/mozilla-ai/any-llm.git'

echo "=== Installing your code in editable mode (no bdi-kit dep) ==="
# Create a temporary pyproject.toml WITHOUT bdi-kit dependency
cat > pyproject_minimal.toml << 'PYPROJECT'
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "harmonia-local"
version = "0.0.1"
dependencies = [
    "beaker_kernel>=1.14.0",
    "jinja2>=3.0",
    "any-llm-sdk",
    "langchain-core",
    "pyyaml>=6.0",
    "aiohttp>=3.8",
    "pandas",
    "pydantic",
]

[tool.hatch.build.targets.wheel]
packages = ["src/bdikit_context", "src/automation", "src/code_context", "src/evaluation"]
PYPROJECT

# Install using the minimal pyproject
pip install --no-build-isolation --no-deps -e . --config-settings editable_mode=compat

echo "=== Setup complete ==="
echo "Limitations: bdikit ML features unavailable (use container for those)"
echo "Available: automation, config loading, LLM adapters, evaluation schemas"
