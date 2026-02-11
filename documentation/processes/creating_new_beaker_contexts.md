# Creating New Beaker Contexts

This guide explains how to create custom Beaker contexts with your own tools to experiment with different LLM agent configurations.

## What is a Context?

A Beaker **context** defines:
1. **System prompt** - Instructions for the LLM (via `auto_context()` method)
2. **Agent** - The agent class that handles LLM interactions
3. **Tools** - Custom functions the LLM can call
4. **Subkernel procedures** - Code templates executed in the Python kernel

## Minimum Requirements

A working context needs:
1. `SLUG` class variable (unique identifier)
2. `auto_context()` method (provides system prompt to LLM)
3. An agent class passed to `super().__init__()`

**Without `auto_context()`, the LLM has no instructions and communication fails.**

## Quick Start: Minimal Context

### 1. Create the directory structure

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
mkdir -p src/my_context/procedures/python3
```

### 2. Create `src/my_context/__init__.py`

```python
from .context import MyContext
__all__ = ["MyContext"]
```

### 3. Create `src/my_context/context.py`

```python
from beaker_kernel.lib.context import BeakerContext
from beaker_kernel.lib.agent import BeakerAgent

class MyContext(BeakerContext):
    """My custom context."""

    SLUG = "my_context"  # Unique identifier
    enabled_subkernels = ["python3"]

    def __init__(self, beaker_kernel, config):
        super().__init__(beaker_kernel, BeakerAgent, config)

    async def auto_context(self):
        """THE CRITICAL METHOD - provides system prompt to LLM."""
        return """You are a helpful assistant.

Write Python code to help the user with their tasks.
Be concise and focused."""
```

### 4. Register the context in `pyproject.toml`

Add to the `[project.entry-points."beaker.contexts"]` section:

```toml
[project.entry-points."beaker.contexts"]
bdikit_context = "bdikit_context.context:BDIKitContext"
code_context = "code_context.context:CodeContext"
my_context = "my_context.context:MyContext"  # Add this line
```

### 5. Add runtime mapping in `exec_apptainer_harmonia.sh`

Find the section that creates JSON mappings and add:

```bash
cat > "${RUNTIME_CONTEXTS_DIR}/my_context.json" << 'EOF'
{
    "slug": "my_context",
    "package": "my_context.context",
    "class_name": "MyContext"
}
EOF
```

### 6. Test

Restart Beaker and select "my_context" from the context dropdown.

---

## Adding Custom Tools

Tools let the LLM call specific functions. There are two approaches:

### Approach A: Simple Tools (Function-based)

Create a custom agent with tools using the `@tool` decorator:

```python
# src/my_context/agent.py
from beaker_kernel.lib.agent import BeakerAgent
from langchain_core.tools import tool

class MyAgent(BeakerAgent):
    """Agent with custom tools."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Register tools
        self.tools = [self.calculate_stats, self.format_table]

    @tool
    def calculate_stats(self, data: str) -> str:
        """Calculate basic statistics for the given data.

        Args:
            data: Description of the data to analyze
        """
        # This runs in the agent process, not the subkernel
        return f"Calculating stats for: {data}"

    @tool
    def format_table(self, columns: list[str], rows: list[list]) -> str:
        """Format data as a markdown table.

        Args:
            columns: Column headers
            rows: Table rows
        """
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join(["---"] * len(columns)) + " |"
        body = "\n".join("| " + " | ".join(map(str, row)) + " |" for row in rows)
        return f"{header}\n{sep}\n{body}"
```

Update your context to use this agent:

```python
# src/my_context/context.py
from beaker_kernel.lib.context import BeakerContext
from .agent import MyAgent

class MyContext(BeakerContext):
    SLUG = "my_context"

    def __init__(self, beaker_kernel, config):
        super().__init__(beaker_kernel, MyAgent, config)  # Use MyAgent

    async def auto_context(self):
        return """You have access to these tools:
- calculate_stats: Analyze data statistics
- format_table: Create markdown tables

Use these tools to help the user."""
```

### Approach B: Subkernel Procedures (Code Execution)

For tools that need to execute Python code in the Jupyter kernel:

```python
# src/my_context/agent.py
from beaker_kernel.lib.agent import BeakerAgent

class MyAgent(BeakerAgent):
    """Agent with subkernel procedures."""

    @BeakerAgent.procedure()
    async def analyze_dataframe(self, df_name: str) -> str:
        """Analyze a pandas DataFrame in the kernel.

        Args:
            df_name: Name of the DataFrame variable
        """
        # This Jinja2 template is executed in the subkernel
        code = """
import pandas as pd

df = {{ df_name }}
summary = {
    'shape': df.shape,
    'columns': list(df.columns),
    'dtypes': df.dtypes.to_dict(),
    'missing': df.isnull().sum().to_dict()
}
print(summary)
"""
        # Execute in subkernel and return result
        result = await self.context.execute(code, {"df_name": df_name})
        return result
```

Or use separate template files:

```
src/my_context/
├── procedures/
│   └── python3/
│       └── analyze_dataframe.py  # Jinja2 template
├── agent.py
└── context.py
```

`procedures/python3/analyze_dataframe.py`:
```python
import pandas as pd

df = {{ df_name }}
summary = {
    'shape': df.shape,
    'columns': list(df.columns),
    'dtypes': df.dtypes.to_dict(),
    'missing': df.isnull().sum().to_dict()
}
print(summary)
```

---

## Rich System Prompts with Jinja2 Templates

For complex system prompts, use Jinja2 templates like bdikit_context:

```
src/my_context/
├── prompts/
│   └── system/
│       └── main.j2
├── context.py
└── ...
```

`prompts/system/main.j2`:
```jinja2
You are an expert data analyst assistant.

## Available Tools
{% for tool in tools %}
- **{{ tool.name }}**: {{ tool.description }}
{% endfor %}

## Guidelines
1. Always explain your reasoning
2. Use tools when appropriate
3. Ask clarifying questions if needed

## Current Environment
- Working directory: /workspace
- Data files: /workspace/data/
- Output directory: /workspace/results/
```

Load in context:

```python
from beaker_kernel.lib.context import BeakerContext
from beaker_kernel.lib.templates import PromptLoader

class MyContext(BeakerContext):
    SLUG = "my_context"

    def __init__(self, beaker_kernel, config):
        super().__init__(beaker_kernel, MyAgent, config)
        self.prompt_loader = PromptLoader(self)

    async def auto_context(self):
        tools = [
            {"name": "analyze_dataframe", "description": "Analyze DataFrame statistics"},
            {"name": "plot_chart", "description": "Create visualizations"},
        ]
        return self.prompt_loader.get_system_prompt(tools=tools)
```

---

## Testing Your Context

### 1. Without Rebuilding Container (Development)

The `exec_apptainer_harmonia.sh` script:
- Binds `src/` to `/opt/harmonia_src` in the container
- Sets `PYTHONPATH` so new contexts are importable
- Creates JSON mappings for context discovery

Just restart Beaker after making changes.

### 2. For Production (Rebuild Container)

Update `harmonia_beaker_LLM_agent_environment_apptainer.def`:

```bash
echo "=== Verifying my_context installation ==="
python3 -c "from my_context.context import MyContext; print('MyContext imported successfully')"
```

And add the JSON mapping:

```bash
cat > /usr/local/share/beaker/contexts/my_context.json << 'EOF'
{
    "slug": "my_context",
    "package": "my_context.context",
    "class_name": "MyContext"
}
EOF
```

Then rebuild:
```bash
srun -J apptainer_build --time=02:00:00 --mem=32G --gres=tmpspace:100G bash
./build_harmonia_apptainer.sh
```

---

## Example: bdikit_context Structure

Reference implementation:

```
src/bdikit_context/
├── __init__.py           # Package init, LLM config
├── __about__.py          # Version info
├── context.py            # BDIKitContext class
├── agent.py              # BDIKitAgent with 5 tools
├── llm/                  # LLM provider integration
│   ├── __init__.py
│   └── anyllm.py         # any-llm-sdk integration
├── procedures/           # Subkernel code templates
│   └── python3/
│       ├── match_schema.py
│       ├── top_matches.py
│       ├── match_values.py
│       ├── materialize_mapping.py
│       └── get_gdc_acceptable_values.py
└── prompts/              # System prompt templates
    └── system/
        └── main.j2
```

---

## Debugging Tips

1. **Check logs**: Look at `logs/*_beaker.log` for errors
2. **Context not found**: Verify JSON mapping exists and package is importable
3. **LLM not responding**: Check `auto_context()` returns a non-empty string
4. **Tools not working**: Verify tools are registered in agent's `tools` list
5. **Import errors**: Check `PYTHONPATH` includes `/opt/harmonia_src`

### Test import manually:
```bash
apptainer exec \
    --bind ./src:/opt/harmonia_src:ro \
    --env PYTHONPATH=/opt/harmonia_src \
    harmonia_beaker_LLM_agent_environment_apptainer.sif \
    python3 -c "from my_context.context import MyContext; print('OK')"
```

---

## Quick Reference

| Component | Purpose | Required? |
|-----------|---------|-----------|
| `SLUG` | Unique context identifier | Yes |
| `auto_context()` | System prompt for LLM | **Yes** (critical!) |
| Agent class | Handles LLM interactions | Yes (can use default `BeakerAgent`) |
| Tools | Functions LLM can call | No (optional) |
| Procedures | Subkernel code templates | No (optional) |
| Prompts | Jinja2 system prompt templates | No (optional) |
