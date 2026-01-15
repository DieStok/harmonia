# Harmonia Metadata Agent Codebase Documentation

**Date:** 15-01-2026
**Author:** Generated documentation for the Harmonia data harmonization experiment automation framework

## Overview

This codebase automates data harmonization experiments using the BDI-Kit library within Beaker kernel environments. It enables:
- Running scripted LLM conversations for data harmonization tasks
- Supporting multiple LLM providers (Ollama for local models, OpenRouter for cloud)
- Executing experiments on HPC clusters via SLURM
- Capturing conversation traces, notebooks, and harmonized output files

## Directory Structure

```
harmonia/
├── src/
│   ├── automation/           # Experiment automation framework
│   │   ├── client.py         # WebSocket client for Beaker kernel communication
│   │   ├── runner.py         # Experiment execution orchestration
│   │   ├── config.py         # Configuration dataclasses
│   │   └── logger.py         # Trace and conversation logging
│   │
│   └── bdikit_context/       # BDI-Kit Beaker context package
│       ├── context.py        # BeakerContext implementation
│       ├── agent.py          # BDIKitAgent with tool definitions
│       ├── prompts/          # System prompt templates
│       └── procedures/       # Code templates for BDI-Kit functions
│           └── python3/
│               ├── match_schema.py
│               ├── match_values.py
│               ├── top_matches.py
│               ├── materialize_mapping.py
│               └── get_gdc_acceptable_values.py
│
├── experiments/
│   └── configs/              # YAML experiment configurations
│       ├── experiment_config.template  # Template with documentation
│       └── dou_harmonization_*.yaml    # Model-specific configs
│
├── jobs/                     # Generated SLURM job scripts
├── results/                  # Experiment output directories
├── logs/                     # SLURM stdout/stderr logs
│
├── run_experiment.py         # CLI entry point for running experiments
├── generate_jobs.py          # Script to generate SLURM job scripts
├── jupyter.def               # Apptainer container definition
├── jupyter.sif               # Built Apptainer image
├── sbatch_template.sh        # SLURM job template for OpenRouter
├── sbatch_template_gpu.sh    # SLURM job template for Ollama (GPU)
└── dou.csv                   # Sample dataset for harmonization
```

## Key Components

### 1. Automation Framework (`src/automation/`)

#### `client.py` - BeakerClient
Handles WebSocket communication with the Beaker Jupyter server.

**Key Methods:**
- `connect()` - Establishes WebSocket connection to Jupyter server
- `_set_context_magic(context_slug)` - Sets the BDI-Kit context using `%set_context` magic
- `send_llm_request(message)` - Sends user messages to the LLM agent
- `_receive_messages(timeout)` - Collects all response messages for a turn

**Connection Flow:**
```python
async with BeakerClient(base_url, xsrf_token) as client:
    await client._set_context_magic("bdikit_context")
    response = await client.send_llm_request("Load dou.csv...")
```

#### `runner.py` - ExperimentRunner
Orchestrates the full experiment lifecycle.

**Key Methods:**
- `run()` - Main execution loop for all conversation turns
- `_execute_turn(message_config)` - Executes a single conversation turn
- `_setup_output_directory()` - Creates timestamped results folder
- `_save_results()` - Saves trace.json and conversation.md

**Output Directory Structure:**
```
results/<experiment_name>_<timestamp>/
├── trace.json          # Full message trace with raw WebSocket data
├── conversation.md     # Human-readable conversation log
└── notebook.ipynb      # (planned) Jupyter notebook reconstruction
```

#### `config.py` - Configuration Dataclasses
Defines the structure of experiment configuration.

```python
@dataclass
class ExperimentConfig:
    name: str
    description: str

@dataclass
class LLMConfig:
    provider: str      # "ollama" or "openrouter"
    model: str
    base_url: str
    temperature: float

@dataclass
class MessageConfig:
    content: str
    wait_seconds: int
    decision_mode: str  # "auto_accept" or "manual"
```

#### `logger.py` - Logging Classes
- **TraceLogger**: Captures full JSON traces with raw messages
- **ConversationLogger**: Creates markdown-formatted conversation logs
- **build_notebook_cells()**: Converts traces to Jupyter notebook format

### 2. BDI-Kit Context (`src/bdikit_context/`)

#### `context.py` - BDIKitContext
Beaker context that provides BDI-Kit tools to the LLM agent.

```python
class BDIKitContext(BeakerContext):
    enabled_subkernels = ["python3"]
    SLUG = "bdikit_context"

    def __init__(self, beaker_kernel, config):
        super().__init__(beaker_kernel, BDIKitAgent, config)
```

#### `agent.py` - BDIKitAgent
Defines tools available to the LLM for data harmonization.

**Available Tools:**
| Tool | Description |
|------|-------------|
| `match_schema()` | Maps source columns to GDC schema |
| `top_matches()` | Shows top 10 alternative column mappings |
| `match_values()` | Maps values between source and target columns |
| `materialize_mapping()` | Creates the final harmonized table |
| `get_gdc_acceptable_values()` | Lists valid values for GDC columns |

**Tool Declaration Example:**
```python
@tool()
async def match_schema(self, dataset: str, target: str, method: str, agent: AgentRef) -> str:
    """Performs schema mapping between source and target tables."""
    code = agent.context.get_code("match_schema", {...})
    result = await agent.context.evaluate(code, parent_header={})
    return result.get("return")
```

### 3. Experiment Configuration

Experiments are defined in YAML files in `experiments/configs/`.

**Key Sections:**
```yaml
experiment:
  name: "dou_harmonization_devstral"
  description: "Harmonize dou.csv using Devstral"

llm:
  provider: ollama          # or "openrouter"
  model: devstral:latest
  base_url: http://localhost:11434
  temperature: 0.0

messages:
  - content: |
      Load the file dou.csv as a dataframe...
    wait_seconds: 180
    decision_mode: auto_accept

output:
  base_dir: "./results"
  save_artifacts:
    - "dou_harmonized.csv"
```

### 4. Container Environment (`jupyter.def`)

The Apptainer container provides:
- Jupyter server with Beaker kernel
- BDI-Kit library for data harmonization
- Pre-installed bdikit_context package
- LLM provider libraries (langchain-ollama, langchain-openai)

**Context Registration:**
The bdikit_context is registered via legacy JSON mapping:
```
/usr/local/share/beaker/contexts/bdikit_context.json
```

## Sample Workflows

### Running an Experiment Locally

```bash
# Set environment variables
export OPENROUTER_API_KEY="your-key"
export LLM_SERVICE_PROVIDER="openrouter"
export LLM_SERVICE_MODEL="mistralai/devstral-small:free"

# Start the Beaker server in container
./exec_apptainer_harmonia.sh

# Run experiment (in another terminal)
python run_experiment.py experiments/configs/dou_harmonization_devstral.yaml
```

### Running Experiments on HPC (SLURM)

```bash
# Generate SLURM job scripts for all experiments
python generate_jobs.py

# Submit a single job
sbatch jobs/dou_harmonization_devstral.sh

# Submit all Ollama jobs (GPU required)
for job in jobs/*ollama*.sh; do sbatch $job; done

# Check job status
squeue -u $USER
```

### Launching Interactive Beaker Server

```bash
# Start container with Beaker server
./exec_apptainer_harmonia.sh

# Access JupyterLab in browser at http://localhost:8888
# Token is printed in console output
```

## LLM Provider Configuration

### Ollama (Local Models)
- Requires GPU partition on HPC
- Models must be pre-downloaded or pulled at runtime
- Environment variables:
  ```bash
  LLM_SERVICE_PROVIDER=ollama
  LLM_SERVICE_MODEL=devstral:latest
  OLLAMA_HOST=http://localhost:11434
  ```

### OpenRouter (Cloud Models)
- Requires API key
- Environment variables:
  ```bash
  LLM_SERVICE_PROVIDER=openrouter
  LLM_SERVICE_MODEL=mistralai/devstral-small:free
  OPENROUTER_API_KEY=your-key
  ```

## Tool Calling Requirements

**Important:** The Beaker kernel uses Archytas ReAct agent which requires LLMs to support function/tool calling. Models without tool support will fail.

**Models with Tool Support (Ollama):**
- devstral:latest
- devstral-small-2:latest
- qwen3-coder:30b
- olmo-3.1:32b (NOT olmo-3:latest)

**Models WITHOUT Tool Support:**
- olmo-3:latest
- Some free-tier OpenRouter models

## Tool Registration Architecture

### How Beaker Discovers Contexts

Beaker-kernel uses Python entry points for autodiscovery:

```python
# In beaker_kernel/lib/autodiscovery.py
def autodiscover(mapping_type: ResourceType) -> dict[str, type]:
    group = f"beaker.{mapping_type}"  # e.g., "beaker.contexts"
    eps = entry_points(group=group)
    # ...
```

### Entry Point Configuration

The `bdikit_context` package must register itself with beaker via entry points in `pyproject.toml`:

```toml
[project.entry-points."beaker.contexts"]
bdikit_context = "bdikit_context.context:BDIKitContext"
```

### Tool Registration Flow

1. **BDIKitContext** passes **BDIKitAgent** class to `BeakerContext.__init__`
2. **BeakerContext** instantiates the agent with subkernel tools
3. **BeakerAgent** passes tools to **ReActAgent** (archytas)
4. **ReActAgent.make_tool_dict()** scans for `@tool()` decorated methods

### Verifying Tool Registration

```bash
# Check entry points in container
apptainer exec jupyter.sif python -c "
from importlib.metadata import entry_points
eps = entry_points(group='beaker.contexts')
print('beaker.contexts:', list(eps.names))
"

# Check tools are discovered
apptainer exec jupyter.sif python -c "
from bdikit_context.agent import BDIKitAgent
from archytas.tool_utils import is_tool
import inspect
tools = [n for n, m in inspect.getmembers(BDIKitAgent) if is_tool(m)]
print('Tools:', tools)
"
```

## Troubleshooting

### "Agent says it doesn't have tools"
**Root Cause:** The `bdikit_context` package entry point is not registered.

**Fix:** Ensure `pyproject.toml` has:
```toml
[project.entry-points."beaker.contexts"]
bdikit_context = "bdikit_context.context:BDIKitContext"
```

Then rebuild the Apptainer image.

### "Context has no workflows: disabling tools"
This message appears in Beaker logs but doesn't affect BDI-Kit tools. The tools are registered via the agent, not workflows. This warning only disables workflow-specific tools (`attach_workflow`, `update_workflow_stage`, etc.).

### "Model does not support tools"
Ensure the model supports function calling. For Ollama, test with:
```bash
curl http://localhost:11434/api/chat -d '{
  "model": "devstral:latest",
  "messages": [{"role": "user", "content": "Hello"}],
  "tools": [{"type": "function", "function": {"name": "test", "parameters": {}}}]
}'
```

### Connection Errors
- Verify Jupyter server is running on expected port
- Check XSRF token is being passed correctly
- Ensure WebSocket upgrade is supported

### Missing Columns in dou.csv
The experiment prompts reference specific columns. Verify the CSV has:
`Country, Histologic_Grade_FIGO, Histologic_type, FIGO_stage, BMI, Age, Race, Ethnicity, Gender, Tumor_Focality, Tumor_Size_cm`

## File Outputs

After a successful experiment run:
- `results/<name>_<timestamp>/trace.json` - Full execution trace
- `results/<name>_<timestamp>/conversation.md` - Readable conversation log
- `dou_harmonized.csv` - Harmonized output (in working directory)
- `logs/<name>_<jobid>.out/.err` - SLURM job logs
