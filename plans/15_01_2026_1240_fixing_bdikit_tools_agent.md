# Plan: Fixing BDI-Kit Tools Agent Registration

**Date:** 15-01-2026 12:40
**Status:** In Progress
**Issue:** Agent responds "I don't have the tools needed" despite @tool() decorated methods

---

## Executive Summary

The BDI-Kit agent tools are not being registered with the LLM during experiment runs. The root cause is that the beaker-kernel's autodiscovery system cannot find the `bdikit_context` because it lacks proper **entry points configuration** in pyproject.toml.

---

## Root Cause Analysis

### How Beaker Discovers Contexts

Beaker-kernel uses Python entry points for autodiscovery:

1. **Entry Point Discovery** (`beaker_kernel/lib/autodiscovery.py:179-198`)
   ```python
   def autodiscover(mapping_type: ResourceType) -> dict[str, type]:
       group = f"beaker.{mapping_type}"  # e.g., "beaker.contexts"
       eps = entry_points(group=group)
       items = AutodiscoveryItems(eps)
       # ... also checks legacy JSON files in ~/.beaker/
   ```

2. **Build Hook Registration** (`beaker_kernel/builder/beaker.py:174-188`)
   - During wheel build, the `BeakerBuildHook` scans packages for subclasses of `BeakerContext`
   - Automatically adds them to `metadata.core.entry_points["beaker.contexts"]`
   - This is triggered by `[tool.hatch.build.hooks.beaker]` in pyproject.toml

### Current Problem

The `bdikit_context` package's pyproject.toml is **missing** the beaker build hook configuration:

```toml
# MISSING from pyproject.toml:
[tool.hatch.build.hooks.beaker]
# This empty section enables automatic entry point generation
```

Without this hook, the context is never registered with the `beaker.contexts` entry point group, so beaker cannot find or load it.

### How Tools Get Registered (When It Works)

1. **BDIKitContext** passes **BDIKitAgent** class to `BeakerContext.__init__`
2. **BeakerContext** instantiates the agent with subkernel tools:
   ```python
   self.agent = agent_cls(context=self, tools=self.subkernel.tools)
   ```
3. **BeakerAgent** collects tools and passes to **ReActAgent** (archytas):
   ```python
   super().__init__(tools=tools, ...)
   ```
4. **ReActAgent.make_tool_dict()** scans the agent instance for `@tool()` decorated methods

### Why "Context has no workflows" Appears

This is a **separate, non-blocking warning**:
- Beaker looks for `src/bdikit_context/workflows/*.yaml` files
- If missing, it disables workflow-specific tools (`attach_workflow`, etc.)
- This does NOT affect agent tools like `match_schema`, `match_values`, etc.

---

## Fix Implementation

### Fix 1: Add Beaker Build Hook (PRIMARY FIX)

**File:** `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/pyproject.toml`

**Add this section:**
```toml
[tool.hatch.build.hooks.beaker]
# Enables automatic context/agent discovery and entry point registration
# Finds BDIKitContext subclass and registers as beaker.contexts entry point
```

This already exists in the file (line 46-47) but may not be working correctly. Need to verify installation.

### Fix 2: Manual Entry Point Configuration (FALLBACK)

If the build hook doesn't work, add explicit entry points:

```toml
[project.entry-points."beaker.contexts"]
bdikit_context = "bdikit_context.context:BDIKitContext"
```

### Fix 3: Add Workflows Directory (OPTIONAL)

Create workflows to suppress the warning and enable workflow tools:

```bash
mkdir -p src/bdikit_context/workflows
cat > src/bdikit_context/workflows/harmonization.yaml << 'EOF'
name: "Data Harmonization"
description: "Standard BDI-Kit harmonization workflow"
stages:
  - name: "Load Data"
    description: "Load and subset the source dataset"
  - name: "Schema Matching"
    description: "Match columns to GDC schema"
  - name: "Value Mapping"
    description: "Map values between source and target vocabularies"
  - name: "Materialize"
    description: "Create the final harmonized table"
EOF
```

---

## Verification Steps

### Step 1: Check Entry Point Registration

After rebuilding the package:
```bash
# Inside container or with bdikit_context installed
python -c "
from importlib.metadata import entry_points
eps = entry_points(group='beaker.contexts')
print('Registered contexts:', list(eps.names))
print('bdikit_context:', 'bdikit_context' in eps.names)
"
```

Expected output:
```
Registered contexts: ['bdikit_context']
bdikit_context: True
```

### Step 2: Check Tool Discovery

```bash
python -c "
from bdikit_context.agent import BDIKitAgent
from archytas.tool_utils import is_tool
import inspect

# Check each method
for name, method in inspect.getmembers(BDIKitAgent, predicate=inspect.isfunction):
    if is_tool(method):
        print(f'Tool: {name}')
"
```

Expected output:
```
Tool: match_schema
Tool: top_matches
Tool: match_values
Tool: materialize_mapping
Tool: get_gdc_acceptable_values
```

### Step 3: Test with Interactive Server

Start an interactive Beaker server and manually test tool availability.

---

## Interactive Testing Setup

### Option A: Interactive GPU Session with Ollama

```bash
# Start 4-hour interactive GPU session
srun -J harmonia_interactive_claude-code \
    --partition=gpu \
    --gpus-per-node=1 \
    --mem=80G \
    --time=04:00:00 \
    --pty bash

# Inside the session:
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia

# Start Ollama server
OLLAMA_DIR=/hpc/compgen/projects/ollama/ollama_run/analysis/dstoker
$OLLAMA_DIR/start_ollama.sh &

# Wait for Ollama to start
sleep 30

# Set environment
export LLM_BASE_URL=http://$(hostname):11434
export OLLAMA_HOST=http://$(hostname):11434

# Get a dynamic port
PORT=$((8100 + (RANDOM % 100)))

# Start Beaker server
apptainer exec \
    --nv \
    --bind .:/jupyter \
    --pwd /jupyter \
    --env JUPYTER_SERVER=http://localhost:$PORT \
    --env LLM_SERVICE_PROVIDER=ollama \
    --env LLM_SERVICE_MODEL=devstral:latest \
    --env LLM_BASE_URL=$LLM_BASE_URL \
    --env OLLAMA_HOST=$OLLAMA_HOST \
    jupyter.sif \
    beaker dev watch --ip 0.0.0.0 --port $PORT
```

### Option B: Test with OpenRouter (No GPU Required)

```bash
# Start 4-hour CPU session
srun -J harmonia_interactive_claude-code \
    --mem=20G \
    --time=04:00:00 \
    --pty bash

# Inside the session:
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia

PORT=$((8100 + (RANDOM % 100)))

# Start Beaker server with OpenRouter
apptainer exec \
    --bind .:/jupyter \
    --pwd /jupyter \
    --env-file .env \
    --env JUPYTER_SERVER=http://localhost:$PORT \
    --env LLM_SERVICE_PROVIDER=openrouter \
    --env LLM_SERVICE_MODEL=mistralai/devstral-small:free \
    jupyter.sif \
    beaker dev watch --ip 0.0.0.0 --port $PORT

# Connect from your machine:
echo "Connect to: http://$(hostname):$PORT"
```

### SSH Tunnel Command (for remote access)

From your local machine:
```bash
ssh -L 8100:<node_hostname>:<port> <username>@hpcs05.op.umcutrecht.nl
# Then open http://localhost:8100 in browser
```

---

## Debugging Commands

### Check Installed Packages in Container

```bash
apptainer exec jupyter.sif pip list | grep -E "beaker|bdikit|archytas"
```

### Check Entry Points in Container

```bash
apptainer exec jupyter.sif python -c "
from importlib.metadata import entry_points
for group in ['beaker.contexts', 'beaker.subkernels', 'beaker.integrations']:
    eps = entry_points(group=group)
    print(f'{group}: {list(eps.names)}')
"
```

### Check Agent Tools Directly

```bash
apptainer exec jupyter.sif python -c "
from bdikit_context.agent import BDIKitAgent
from bdikit_context.context import BDIKitContext
print('BDIKitContext.SLUG:', BDIKitContext.SLUG)
print('BDIKitAgent:', BDIKitAgent)
print('Agent tools:', [m for m in dir(BDIKitAgent) if not m.startswith('_')])
"
```

### Enable Debug Logging

Add to experiment or manual test:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('beaker_kernel').setLevel(logging.DEBUG)
logging.getLogger('archytas').setLevel(logging.DEBUG)
```

---

## Failure Modes and Mitigations

### Failure Mode 1: Entry Point Not Found

**Symptom:** `entry_points(group='beaker.contexts')` returns empty

**Cause:** Package not installed in editable mode, or build hook not running

**Fix:** Reinstall package:
```bash
pip install -e ".[all]"
# or rebuild container
```

### Failure Mode 2: Context Found But Agent Has No Tools

**Symptom:** Context loads but agent says "I don't have tools"

**Cause:** @tool() decorator not being applied correctly

**Fix:** Verify decorator import and usage:
```python
from archytas.tool_utils import tool  # Must be from archytas
```

### Failure Mode 3: LLM Doesn't Support Tool Calling

**Symptom:** Tools registered but LLM ignores them

**Cause:** Model doesn't support function calling (e.g., olmo-3:latest)

**Fix:** Use tool-capable models:
- devstral:latest (123B) ✅
- devstral-small-2:latest (24B) ✅
- olmo-3.1:32b ✅ (NOT olmo-3:latest ❌)
- qwen3-coder:30b ✅

### Failure Mode 4: PyTorch 2.6 Compatibility

**Symptom:** `UnpicklingError: Weights only load failed` with ct_learning method

**Cause:** PyTorch 2.6 changed `torch.load` defaults

**Fix:** Use `similarity` method instead of `ct_learning`

---

## Implementation Checklist

- [ ] Verify pyproject.toml has `[tool.hatch.build.hooks.beaker]` section
- [ ] Add explicit entry points as fallback
- [ ] Rebuild Apptainer image with updated package
- [ ] Test entry point registration in container
- [ ] Test tool discovery in container
- [ ] Run interactive test with Ollama
- [ ] Verify tools appear in LLM responses
- [ ] Update documentation with findings

---

## Related Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package configuration, entry points |
| `src/bdikit_context/context.py` | BDIKitContext class (registered context) |
| `src/bdikit_context/agent.py` | BDIKitAgent with @tool() methods |
| `jupyter.sif` | Apptainer image with installed packages |
| `src/automation/runner.py` | Experiment runner that creates sessions |

---

## Expected Outcomes

After fixes are implemented:

1. **Entry points registered:** `beaker.contexts` contains `bdikit_context`
2. **Tools discovered:** Agent has `match_schema`, `match_values`, etc.
3. **LLM uses tools:** Agent calls tools to complete harmonization tasks
4. **Experiments succeed:** Full harmonization workflow completes

---

## Next Steps After This Fix

1. Run comprehensive tests with all tool-capable models
2. Collect results and compare model performance
3. Create summary report of harmonization accuracy
4. Document the fix for future reference
