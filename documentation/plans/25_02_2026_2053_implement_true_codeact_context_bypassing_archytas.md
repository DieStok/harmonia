# Implementation Plan: True CodeAct Context (Bypassing Archytas ReAct)

**Date:** 2026-02-25
**Author:** dstoker + Claude
**Status:** Draft

---

## 1. Motivation: Why the Current code_context Is Not CodeAct

### Three agent paradigms in Harmonia

Harmonia needs to compare three agent strategies on the same harmonization task using the same execution environment (Beaker subkernel inside Apptainer):

| Paradigm | How the LLM acts | System prompt includes | Agent loop |
|---|---|---|---|
| **ReAct + domain tools** (`bdikit_context`) | LLM calls domain-specific tools (`match_schema`, `match_values`, etc.) via structured JSON tool calls. Each tool generates Python code from Jinja2 templates and executes via `agent.context.evaluate(code)`. | Archytas ReAct prelude + tool schemas for 5 domain tools + `run_code` + system tools (`final_answer`, `fail_task`, `ask_user`) | Archytas `ReActAgent.react_async()` |
| **ReAct + run_code only** (`code_context` today) | LLM calls a single generic `run_code(code: str)` tool via structured JSON tool calls. Same Archytas ReAct loop, but the only non-system tool is `run_code`. | Archytas ReAct prelude + tool schema for `run_code` + system tools (`final_answer`, `fail_task`, `ask_user`) | Archytas `ReActAgent.react_async()` |
| **True CodeAct** (this plan) | LLM writes Python code directly in its response text. No tool schemas. No JSON wrapping. Code is extracted from markdown code fences and executed. | Minimal prompt: "Write Python code. I will execute it and show you the output." | Custom loop (no Archytas) |

### Why this matters

The current `code_context` is **not** a CodeAct agent. It is a ReAct agent that happens to have only one generic tool (`run_code`). The distinction matters for experimental validity:

**Per the ReAct paper** ([Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models", ICLR 2023](https://arxiv.org/abs/2210.03629)): ReAct interleaves explicit reasoning traces (Thought) with discrete actions (tool calls). Each action is one atomic operation producing one Observation. The LLM must alternate between reasoning and acting.

**Per the CodeAct paper** ([Wang et al., "Executable Code Actions Elicit Better LLM Agents", ICML 2024](https://arxiv.org/abs/2402.01030), Section 3.2, Table 1): CodeAct replaces the entire tool-calling mechanism with executable code as the action space. Key findings:
- **~30% fewer actions** than ReAct on the same tasks (because one code block can contain multiple operations, control flow, error handling)
- **Up to 20% higher success rate** on complex multi-tool tasks (82 human-curated tasks on M3ToolEval)
- **Leverages pretraining**: LLMs are massively pretrained on Python code; JSON tool-call schemas are synthetic formats the LLM was never pretrained on

### Specific differences in practice

**Token overhead per turn:** In code_context today, each turn where the LLM wants to execute code includes: the ReAct prelude in the system prompt, tool schemas for `run_code` + `final_answer` + `fail_task` + `ask_user` bound via LangChain's `bind_tools()`, and the LLM must produce structured JSON `{"name": "run_code", "args": {"code": "..."}}`. In true CodeAct, the system prompt is minimal and the LLM writes code naturally.

**Actions per turn:** In ReAct+run_code, each `run_code` call is one action — the LLM must stop, wait for the observation, reason, and issue another tool call. In CodeAct, the LLM can write a single code block that loads data, inspects it, transforms it, and saves results — all in one turn.

**Completion signal:** In ReAct, the LLM must call `final_answer(answer="...")`. In CodeAct, the LLM simply responds with text and no code block.

### What this plan implements

A new Beaker context called `codeact_context` that:
- Bypasses Archytas entirely (no `ReActAgent`, no `BeakerAgent`)
- Calls the LLM directly via litellm
- Extracts code from markdown fences in the LLM's natural text response
- Executes code via `BeakerContext.execute()` (same Jupyter protocol path as `run_code`)
- Feeds stdout/stderr/errors back as the next user message
- Loops until the LLM responds with no code block, or a turn limit is reached

---

## 2. Architecture

### Current code_context flow (ReAct)

```
llm_request arrives via WebSocket
    |
BeakerKernel.llm_request() handler
    |
CodeContext.auto_context() -> system prompt (includes ReAct prelude from Archytas)
    |
Archytas ReActAgent.react_async()
    |-- Calls LLM with system prompt + tool schemas + chat history
    |-- LLM returns structured tool call: run_code(code="...")
    |-- Archytas dispatches tool call -> run_code() -> context.execute(code)
    |-- Subkernel executes, output captured
    |-- Output added as ToolMessage -> LLM called again
    |-- Loop until LLM calls final_answer()
    |
llm_response sent back via WebSocket
```

### New codeact_context flow (CodeAct)

```
llm_request arrives via WebSocket
    |
BeakerKernel.llm_request() handler
    |
CodeActContext.auto_context() -> system prompt (minimal, no tool schemas)
    |
CodeActContext handles the agent loop ITSELF (no Archytas):
    |-- Calls LLM directly via litellm with system prompt + chat history
    |-- LLM returns natural text, possibly containing ```python ... ``` blocks
    |-- CodeActContext extracts code blocks via regex
    |-- If code found: self.execute(code) -> subkernel executes, output captured
    |-- Output appended to chat history as observation
    |-- LLM called again with updated history
    |-- Loop until: no code block in response OR max turns reached
    |
llm_response sent back via WebSocket
```

### What is reused vs. new

| Component | Reused | New |
|---|---|---|
| Beaker subkernel (Python 3.11, all libraries) | Yes | - |
| `BeakerContext.execute()` (Jupyter protocol code execution) | Yes | - |
| WebSocket transport (`llm_request`/`llm_response`) | Yes | - |
| `run_experiment.py` / `ExperimentRunner` | Yes | - |
| `trace.json` / `conversation.md` logging | Yes | - |
| Apptainer container + bind mounts | Yes | - |
| `exec_apptainer_harmonia.sh` | Modified | Runtime context JSON added |
| Archytas ReActAgent | - | Bypassed entirely |
| `run_code` tool | - | Not used |
| Agent loop | - | Custom loop in CodeActContext |
| Code block extraction | - | New (regex) |
| LLM calling | - | Direct litellm call |

---

## 3. Files to Create

### 3.1 `src/codeact_context/__init__.py`

```python
from .context import CodeActContext
__all__ = ["CodeActContext"]
```

### 3.2 `src/codeact_context/agent.py`

This file defines a **non-Archytas agent** — a plain class that manages the LLM conversation and code extraction loop. It does NOT extend `BeakerAgent` or `ReActAgent`.

```python
"""
CodeAct agent loop — bypasses Archytas entirely.

Calls LLM directly via litellm, extracts code blocks from natural text responses,
executes them via BeakerContext.execute(), and feeds output back as observations.
"""

import re
import os
from typing import Optional
import litellm


# Regex to extract Python code blocks from markdown
CODE_BLOCK_PATTERN = re.compile(
    r"```(?:python|py)?\s*\n(.*?)```",
    re.DOTALL,
)


class CodeActAgentLoop:
    """
    A CodeAct agent loop that:
    1. Sends system prompt + conversation history to LLM via litellm
    2. Parses LLM response for ```python ... ``` code blocks
    3. If code found: executes via context.execute(), captures output
    4. Appends output as observation, calls LLM again
    5. If no code found: returns LLM text as final answer
    6. Stops after max_turns iterations

    This is NOT an Archytas agent. It does not use ReActAgent, BeakerAgent,
    tool schemas, or structured tool calls.
    """

    def __init__(
        self,
        model: str,
        system_prompt: str,
        max_turns: int = 30,
        temperature: float = 0.0,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.temperature = temperature
        self.history: list[dict] = []  # OpenAI-format messages

    def reset(self):
        """Clear conversation history for a new task."""
        self.history = []

    async def run(self, user_message: str, execute_fn, send_message_fn) -> str:
        """
        Run the CodeAct loop for one user message.

        Args:
            user_message: The user's request.
            execute_fn: async callable(code: str) -> ExecutionResult
                        (BeakerContext.execute or wrapper around it)
            send_message_fn: callable to send intermediate messages back to client
                             (for streaming code_cell, stream, etc.)

        Returns:
            The LLM's final text response (the turn where it produced no code).
        """
        self.history.append({"role": "user", "content": user_message})

        for turn in range(self.max_turns):
            # 1. Call LLM
            messages = [
                {"role": "system", "content": self.system_prompt},
                *self.history,
            ]
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
            )
            assistant_text = response.choices[0].message.content or ""
            self.history.append({"role": "assistant", "content": assistant_text})

            # 2. Extract code blocks
            code_blocks = CODE_BLOCK_PATTERN.findall(assistant_text)

            if not code_blocks:
                # No code -> LLM is giving final answer
                return assistant_text

            # 3. Execute each code block, collect output
            all_output = []
            for code in code_blocks:
                code = code.strip()
                if not code:
                    continue

                # Send code_cell message to client for display
                await send_message_fn("code_cell", {"code": code, "language": "python3"})

                # Execute in subkernel
                result = await execute_fn(code)

                # Collect stdout, stderr, errors
                output_parts = []
                if hasattr(result, 'stdout') and result.stdout:
                    stdout_text = result.stdout if isinstance(result.stdout, str) else "\n".join(result.stdout)
                    if stdout_text.strip():
                        output_parts.append(stdout_text.strip())
                        await send_message_fn("stream", {"name": "stdout", "text": stdout_text})
                if hasattr(result, 'stderr') and result.stderr:
                    stderr_text = result.stderr if isinstance(result.stderr, str) else "\n".join(result.stderr)
                    if stderr_text.strip():
                        output_parts.append(f"STDERR:\n{stderr_text.strip()}")
                        await send_message_fn("stream", {"name": "stderr", "text": stderr_text})
                if hasattr(result, 'error') and result.error:
                    error_text = str(result.error)
                    output_parts.append(f"ERROR:\n{error_text}")
                    await send_message_fn("error", {"traceback": [error_text]})
                if hasattr(result, 'return_value') and result.return_value is not None:
                    output_parts.append(f"Return value: {result.return_value}")

                if output_parts:
                    all_output.append("\n".join(output_parts))
                else:
                    all_output.append("[Code executed successfully with no output]")

            # 4. Append observation to history
            observation = "\n---\n".join(all_output)
            self.history.append({
                "role": "user",
                "content": f"[Execution output]\n{observation}",
            })

        # Max turns reached
        return f"[CodeAct agent reached maximum of {self.max_turns} turns without completing the task]"
```

**IMPORTANT implementation notes:**
- The exact attributes on the execution result object (`stdout`, `stderr`, `error`, `return_value`) must be verified against `BeakerContext.execute()`'s return type. Read `beaker_kernel/lib/context.py` lines ~720-935 to find the `ExecutionContext` class and its attributes. The pseudocode above uses placeholder attribute names — adjust to match the actual return type.
- The `send_message_fn` callback sends intermediate messages to the WebSocket client so that `run_experiment.py` sees the same `code_cell`, `stream`, and `error` message types it already handles. Check `BeakerContext.send_response()` for the exact API.

### 3.3 `src/codeact_context/context.py`

```python
"""
True CodeAct Beaker context — bypasses Archytas ReAct.

The LLM writes Python code in markdown fences. Code is extracted and executed
in the Beaker subkernel. No tool schemas, no ReAct prelude, no Archytas.
"""

import os
from pathlib import Path

from beaker_kernel.lib.context import BeakerContext
from .agent import CodeActAgentLoop
from prompt_logging import print_prompt_composition, register_prompt_json_logger


class CodeActContext(BeakerContext):
    """
    CodeAct context: LLM writes code naturally, no tool-call framework.

    Key differences from CodeContext:
    - Does NOT create a BeakerAgent/Archytas agent
    - Manages its own agent loop via CodeActAgentLoop
    - LLM is called directly via litellm (not through Archytas)
    - No tool schemas injected into the LLM prompt
    """

    SLUG = "codeact_context"
    enabled_subkernels = ["python3"]

    def __init__(self, beaker_kernel, config):
        # IMPORTANT: We still call super().__init__() but we need to handle
        # the fact that BeakerContext expects an agent_cls argument.
        #
        # Option A: Pass a dummy agent class and override llm_request handling.
        # Option B: Don't call super().__init__() and manually set up the subkernel.
        #
        # The safest approach is Option A — pass CodeAgent (minimal BeakerAgent)
        # so the subkernel initializes correctly, but override the llm_request
        # handler to use our own CodeActAgentLoop instead of Archytas.
        #
        # Import CodeAgent just for initialization (we won't use it for the loop)
        from code_context.agent import CodeAgent
        super().__init__(beaker_kernel, CodeAgent, config)

        # Build the CodeAct agent loop (replaces Archytas for conversation handling)
        model = os.environ.get("LLM_SERVICE_MODEL", "gpt-4o")
        provider = os.environ.get("LLM_SERVICE_PROVIDER", "openai")

        # litellm model string format: "provider/model" for non-OpenAI providers
        # Adjust based on how HARMONIA configures litellm
        if provider in ("openai",):
            litellm_model = model
        elif provider in ("ollama",):
            litellm_model = f"ollama/{model}"
        elif provider in ("anthropic",):
            litellm_model = f"anthropic/{model}"
        elif provider in ("openrouter",):
            litellm_model = f"openrouter/{model}"
        else:
            litellm_model = f"{provider}/{model}"

        temperature = float(os.environ.get("LLM_TEMPERATURE", "0.0"))
        max_turns = int(os.environ.get("CODEACT_MAX_TURNS", "30"))

        self.codeact_loop = CodeActAgentLoop(
            model=litellm_model,
            system_prompt="",  # Set in auto_context()
            max_turns=max_turns,
            temperature=temperature,
        )

    async def auto_context(self):
        """
        Provide the system prompt for the LLM.

        Supports custom prompts via HARMONIA_CODEACT_PROMPT env var.
        Falls back to HARMONIA_CODE_CONTEXT_PROMPT for compatibility.
        Falls back to a default CodeAct prompt.
        """
        custom_prompt_path = (
            os.environ.get("HARMONIA_CODEACT_PROMPT")
            or os.environ.get("HARMONIA_CODE_CONTEXT_PROMPT")
        )
        if custom_prompt_path and Path(custom_prompt_path).exists():
            prompt = Path(custom_prompt_path).read_text()
        else:
            prompt = f"""You are a data scientist working in a Python environment with a persistent Jupyter kernel.

You have access to pandas, numpy, and other data science libraries.

When you need to do something, write Python code in a ```python code block.
I will execute it and show you the output. You can then write more code based on the results.

When you are done with the task and want to give a final answer, just respond with text (no code block).

Important:
- Variables persist between code blocks (this is a persistent kernel session)
- Use print() to see output — bare expressions do not display
- If you get an error, read the traceback and fix your code
- Working directory: use os.getcwd() and os.listdir() to explore"""

        # Update the agent loop's system prompt
        self.codeact_loop.system_prompt = prompt

        if not hasattr(self, '_auto_context_logged'):
            print(f"\n{'=' * 80}")
            print(f"AUTO-CONTEXT (domain prompt) -- codeact_context [{len(prompt)} chars]:")
            print(f"{'=' * 80}")
            print(prompt)
            print(f"{'=' * 80}\n")
            self._auto_context_logged = True

        return prompt
```

**CRITICAL: Overriding the llm_request handler.**

The above context class initializes with a dummy `CodeAgent` so the subkernel works, but the actual LLM conversation must be handled by `CodeActAgentLoop`, not by Archytas. This requires overriding how `llm_request` messages are processed.

Look at `beaker_kernel/kernel.py` line ~548-640 where `llm_request` is handled. The current flow is:

```python
async def llm_request(self, message):
    ...
    result = await self.context.agent.react_async(request, react_context=...)
    ...
```

To override this, you have two options:

**Option 1 (preferred): Override at the context level.** Add a method to `CodeActContext` that Beaker's kernel calls instead of `agent.react_async()`. Check if `BeakerContext` has a hook for this (e.g., a `handle_llm_request` method that can be overridden). If so, override it.

**Option 2: Monkey-patch the agent.** Replace `self.agent.react_async` with a wrapper that calls `self.codeact_loop.run()` instead. This is hacky but requires zero changes to beaker-kernel.

**The implementer must read `beaker_kernel/kernel.py` lines 548-640 and `beaker_kernel/lib/context.py`** to determine which approach is viable. The key constraint is: the LLM conversation must go through `CodeActAgentLoop.run()`, not through Archytas' `react_async()`.

---

## 4. Files to Modify

### 4.1 `exec_apptainer_harmonia.sh`

Add a runtime context JSON for `codeact_context`, alongside the existing ones for `bdikit_context` and `code_context`.

**Find the section** (around line 820-844) where `bdikit_context.json` and `code_context.json` are created. Add:

```bash
# Create codeact_context.json
cat > "${RUNTIME_CONTEXTS_DIR}/codeact_context.json" << 'EOF'
{
    "slug": "codeact_context",
    "package": "codeact_context.context",
    "class_name": "CodeActContext"
}
EOF
```

No other changes needed — the source code is already mounted via `--bind ${SCRIPT_DIR}/src:/opt/harmonia_src:ro` and `PYTHONPATH` includes `/opt/harmonia_src`.

### 4.2 `src/automation/client.py` — `_find_context()` method (line 124)

The current logic prefers `bdikit_context`. Add support for a `context` field in the experiment config YAML so the correct context is selected automatically.

**Current** (lines 124-144):
```python
async def _find_context(self, context_name: str = None) -> Optional[str]:
    ...
    selected_context = context_name
    if not selected_context:
        for ctx in contexts:
            if "bdikit" in ctx.lower():
                selected_context = ctx
                break
        if not selected_context and contexts:
            selected_context = contexts[0]
    return selected_context
```

**Change:** The `connect()` method (line 59) and `_get_or_create_session()` (line 81) already accept a `context_name` parameter but it's never passed from outside. Thread it through from the config:

1. Add `context: Optional[str] = None` field to `ExperimentConfig` in `config.py`
2. Pass it from `ExperimentRunner` to `BeakerClient.connect(context_name=config.context)`
3. The `_find_context()` logic already handles `context_name` correctly — if provided, it uses it directly

### 4.3 `src/automation/config.py` — `ExperimentConfig`

Add a `context` field:

```python
@dataclass
class ExperimentConfig:
    ...
    context: Optional[str] = None  # "bdikit_context", "code_context", or "codeact_context"
```

Parse it from the YAML:
```python
context=exp.get("context"),  # in from_dict()
```

### 4.4 `generate_env.py`

Add support for `HARMONIA_CODEACT_PROMPT` environment variable, similar to `HARMONIA_CODE_CONTEXT_PROMPT`. Read it from `prompts.codeact_prompt` in the YAML config.

Add to the `PromptsConfig` dataclass in `config.py`:
```python
codeact_prompt: Optional[str] = None
```

### 4.5 `src/automation/runner.py` — `ExperimentRunner`

Pass the context name to the client connection:

**Current** (somewhere in `run()`):
```python
await self.client.connect()
```

**Change to:**
```python
await self.client.connect(context_name=self.config.context)
```

And update `BeakerClient.connect()` signature to accept `context_name`:

```python
async def connect(self, context_name: str = None) -> None:
    ...
    selected_context = await self._get_or_create_session(context_name)
```

---

## 5. Example Experiment Config YAML

Create a new config at `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_devstral.yaml`:

```yaml
experiment:
  name: dou_harmonization_codeact_devstral
  description: >
    Harmonize Dou et al. 2020 metadata to GDC schema using CodeAct
    (code-only, no tools). LLM writes Python code directly.
  context: codeact_context

llm:
  provider: openrouter
  model: mistralai/devstral-small-2505
  temperature: 0.0

prompts:
  codeact_prompt: codeact_prompts/v1_harmonization/prompt.txt

messages:
  - content: >
      You have a CSV file called `dou.csv` in the current directory.
      This contains metadata from the Dou et al. 2020 study.

      Your task is to harmonize this metadata to the GDC (Genomic Data Commons) schema.
      This means:
      1. Load the CSV and inspect its columns and values
      2. Map the column names to GDC-compatible column names
      3. Map the values to GDC-acceptable values where applicable
      4. Save the harmonized table as `harmonized_table.csv`
      5. Save the column mapping as `column_mapping.json`
      6. Save the value mapping as `value_mapping.json`

      The GDC schema expects columns like: project_id, case_submitter_id,
      sample_type, primary_diagnosis, tissue_or_organ_of_origin, etc.

      Start by loading and inspecting the data.
    wait_seconds: 600
    decision_mode: auto_accept

output:
  base_dir: ./results
  save_artifacts:
    - harmonized_table.csv
    - column_mapping.json
    - value_mapping.json

evaluation:
  gold_standard: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/harmonized_table.csv
  input_file: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/dou_2020/dou.csv
  gold_column_mapping: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/column_mapping.json
  gold_value_mapping: /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/value_mapping.json
```

### Custom prompt file

Create `experiments/experiment_1_harmonia_dou2020_gdc/prompts/codeact_prompts/v1_harmonization/prompt.txt` with a domain-specific CodeAct prompt (the exact prompt content is a research variable — start with the default from the context and iterate).

---

## 6. Implementation Steps (Ordered)

### Step 1: Read Beaker's llm_request handler

Read `beaker_kernel/kernel.py` lines 548-640 and `beaker_kernel/lib/context.py` to understand:
- How `llm_request` is dispatched to the context/agent
- Whether `BeakerContext` has an overridable method for handling LLM requests
- What the execution result object looks like (attributes of `ExecutionContext`)

This determines whether Option 1 or Option 2 from Section 3.3 is used.

### Step 2: Create `src/codeact_context/` package

Create `__init__.py`, `agent.py`, and `context.py` as specified in Section 3.

Adjust the `CodeActAgentLoop` based on findings from Step 1:
- Correct the execution result attribute names
- Implement the correct `send_message_fn` callback using `BeakerContext.send_response()`
- Choose and implement the llm_request override mechanism

### Step 3: Add runtime context registration

Edit `exec_apptainer_harmonia.sh` to add `codeact_context.json` (Section 4.1).

### Step 4: Add context selection to config/client

Edit `config.py`, `client.py`, and `runner.py` as specified in Sections 4.2-4.5.

### Step 5: Add env var support

Edit `generate_env.py` to handle `HARMONIA_CODEACT_PROMPT` from the `prompts.codeact_prompt` config field.

### Step 6: Create experiment config + prompt

Create the YAML config and prompt file from Section 5.

### Step 7: Rebuild Apptainer container

The container must be rebuilt because `src/codeact_context/` is new source code that gets mounted into the container. However, since it's bind-mounted (not baked in), this may not require a rebuild — verify that `PYTHONPATH=/opt/harmonia_src` and the bind of `${SCRIPT_DIR}/src:/opt/harmonia_src:ro` in `exec_apptainer_harmonia.sh` will pick up the new package.

If litellm is already installed in the container (it is), no rebuild is needed.

### Step 8: Test

1. Start Beaker: `./exec_apptainer_harmonia.sh --config <codeact_config.yaml>`
2. Verify `codeact_context` appears in `/contexts` endpoint
3. Run automated experiment: `python run_experiment.py <codeact_config.yaml>`
4. Check `trace.json` — should show `code_cell` and `stream` messages without Archytas tool-call structure
5. Check `conversation.md` — should show natural code blocks, not JSON tool calls
6. Run metrics: `.venv/bin/python src/evaluation/calculate_metrics.py`

---

## 7. Open Questions (RESOLVED — see Section 9 for answers)

---

## 8. What NOT to Change

- **Do not modify beaker-kernel source.** All changes are in Harmonia's source code.
- **Do not modify Archytas.** The CodeAct loop bypasses it entirely.
- **Do not modify bdikit_context or code_context.** They continue to work as before.
- **Do not modify the tracing/logging infrastructure.** The existing `trace.json` and `conversation.md` loggers in `runner.py` and `manual_runner.py` should work unchanged, since they already handle `code_cell`, `stream`, `llm_response`, and `error` message types.

---

## 9. Resolved Open Questions (Investigation Results, 2026-02-25)

### Q1: llm_request override mechanism — RESOLVED

**Answer: Override `react_async()` on a custom `BeakerAgent` subclass (clean, no monkey-patching).**

Investigation of `beaker_kernel/kernel.py` (line ~570) shows the key dispatch line:

```python
task = asyncio.create_task(self.context.agent.react_async(request, react_context={"message": message}))
```

There is **no overridable hook** on `BeakerContext` for LLM request handling. The dispatch goes directly to `self.context.agent.react_async()`. The cleanest approach is:

- Create `CodeActAgent(BeakerAgent)` that **overrides `react_async()`**
- Inside the override, call `CodeActAgentLoop.run()` instead of Archytas' ReAct loop
- The `react_context={"message": message}` provides the parent Jupyter message for response routing
- `CodeActContext` passes `CodeActAgent` to `super().__init__()`, so subkernel initialization works normally
- The kernel's `llm_request` handler works completely unchanged

This avoids monkey-patching and keeps all custom logic in our own code.

### Q2: Execution result object — RESOLVED

**Answer: `BeakerContext.execute()` returns `ExecutionTask` (asyncio.Task subclass). `await` it to get a plain dict.**

`ExecutionTask` is defined in `beaker_kernel/lib/utils.py`:

```python
class ExecutionTask(asyncio.Task):
    execute_request_msg: JupyterMessage | None
```

When awaited, returns a dictionary with these keys:

| Key | Type | Contents |
|-----|------|----------|
| `stdout_list` | `list[str]` | All captured stdout lines |
| `stderr_list` | `list[str]` | All captured stderr lines |
| `error` | `dict\|None` | `{"ename": ..., "evalue": ..., "traceback": [...]}` or `None` |
| `return` | `Any` | Return value of the last expression |
| `result` | `dict` | execute_reply content (`status`: `"ok"` or `"error"`) |
| `display_data_list` | `list[dict]` | Display data (plots, images) |
| `command` | `str` | The code that was executed |
| `done` | `bool` | Completion flag |

**Usage:**
```python
result = await self.context.execute("print('hello')")
stdout = "".join(result["stdout_list"])   # "hello\n"
error = result["error"]                    # None if OK
```

**NOTE:** The pseudocode in Section 3.2 uses attribute access (`result.stdout`) — this is WRONG. The real API uses dict access (`result["stdout_list"]`). The implementation corrects this.

There is also `context.evaluate()` which wraps `execute()` and parses the return value through the subkernel's parser.

### Q3: Intermediate message sending — RESOLVED

**Answer: Use `self.context.beaker_kernel.send_response("iopub", msg_type, content, parent_header=...)`.**

The `BeakerKernel` instance (accessible as `self.context.beaker_kernel`) has `send_response()`. The `parent_header` comes from `react_context["message"].header` passed to `react_async()`. Message types: `"code_cell"`, `"stream"`, `"error"`, `"llm_response"`.

### Q4: Token budget / context window management — RESOLVED

**Answer: Implement two configurable strategies.**

When conversation history approaches the context window limit:

1. **Strategy "summarize"** (default): Ask the LLM to produce a summary of what was done so far, including a list of all variables currently in the environment. Uses a configurable Jinja2 prompt template (`HARMONIA_CODEACT_SUMMARY_TEMPLATE` env var or default template). The summary replaces the conversation history.

2. **Strategy "truncate"**: Cut the middle 60% of conversation history, keeping the first 20% and last 20% of messages intact. Simple and deterministic.

Configurable via `CODEACT_CONTEXT_STRATEGY` env var: `"summarize"` (default), `"truncate"`, or `"none"` (no management, litellm will error on overflow).

Token counting uses litellm's `token_counter()` function with the model name for accurate per-model counting.

### Q5: Prompt design — RESOLVED

**Answer: Create a simple domain-specific harmonization prompt file, configurable via `HARMONIA_CODEACT_PROMPT` env var.**

A dedicated prompt file at `experiments/.../prompts/codeact_prompts/v1_harmonization/prompt.txt` provides domain-specific instructions. The `auto_context()` method reads it via env var, falling back to a generic default.

---

## 10. Corrections to Section 3 Pseudocode

The pseudocode in Sections 3.2 and 3.3 has several inaccuracies discovered during investigation. The actual implementation differs in these ways:

1. **Execution result is a dict, not an object with attributes.** Use `result["stdout_list"]` not `result.stdout`.
2. **`CodeActAgentLoop` does not need `send_message_fn`.** Instead, `CodeActAgent.react_async()` has access to the parent message via `react_context` and can call `self.context.beaker_kernel.send_response()` directly.
3. **The agent class is `CodeActAgent(BeakerAgent)` with `react_async()` override**, not a separate class passed alongside a dummy `CodeAgent`.
4. **Context window management is implemented** (not deferred to v2 as the original plan suggested for Q4).
