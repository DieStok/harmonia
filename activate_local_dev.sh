#!/bin/bash
# Activate local development environment for harmonia
# This provides access to your code (bdikit_context, automation, code_context)
# WITHOUT heavy ML dependencies (use container for full bdikit functionality)

# Activate the virtual environment
source /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/.venv/bin/activate

# Add src directory to Python path so your code is importable
export PYTHONPATH="/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src:$PYTHONPATH"

echo "✓ Local development environment activated"
echo ""
echo "Available modules:"
echo "  - bdikit_context (contexts, agents, LLM adapters)"
echo "  - automation (experiment runner, config loading, Beaker client)"
echo "  - code_context (code execution context)"
echo "  - evaluation (schemas, metrics)"
echo ""
echo "Note: Full bdikit ML features require the Apptainer container"
echo ""
echo "Test with:"
echo "  python -c 'from automation import load_config; print(load_config.__doc__)'"
