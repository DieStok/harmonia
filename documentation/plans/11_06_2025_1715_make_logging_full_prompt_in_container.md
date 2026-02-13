# Implementation Plan: Log Full Composed LLM Context at Startup

**Date:** 2025-11-06
**Status:** Proposed
**Goal:** Add logging that captures the complete composed context/prompt that the LLM sees from all sources on its first turn, including model-specific additions. This enables comparison of what different LLM configurations actually receive.

Two complementary outputs:
1. **Human-readable stdout print** — full composed prompt printed to the SLURM log right after Beaker and Ollama have started, for quick visual inspection
2. **Structured JSON file** — per-experiment prompt composition log saved in the results directory, for systematic comparison across runs

---

## Background: How the LLM Context Is Assembled

The LLM receives messages assembled by `Agent.execute()` (in archytas) via `ChatHistory.records()`. The message ordering is:

```
1. system_message        ← ReAct prelude from build_prompt(custom_prelude=...)
2. auto_context_message  ← Domain prompt from BDIKitContext.auto_context() or CodeContext.auto_context()
3. summaries             ← Conversation summaries (empty on first turn)
4. user_preamble         ← Optional first user message (currently None)
5. raw_records           ← Conversation history (user messages + agent responses)
```

Additionally, **model-specific prompt instructions** are appended to the system message during `build_prompt()`:

| Model Class | `MODEL_PROMPT_INSTRUCTIONS` |
|---|---|
| `OllamaModel` | Instructions about tool messages and `final_answer` tool usage (~200 chars) |
| `AnyLLMModel` | Empty string `''` |
| `BaseArchytasModel` | Empty string `''` |

The system message is constructed by `build_prompt()` as:
```python
prelude + "\n" + MODEL_PROMPT_INSTRUCTIONS + tool_descriptions + "\n" + react_instructions
```

### Key Code Locations (inside container at `/opt/harmonia_src/`)

| Component | Container Path | Purpose |
|---|---|---|
| `Agent.execute()` | `archytas` package (installed) | Assembles messages, calls LLM |
| `ChatHistory.records()` | `archytas` package (installed) | Orders message records |
| `build_prompt()` | `archytas.react` module (installed) | Builds system message with prelude + model instructions |
| `BDIKitContext.auto_context()` | `/opt/harmonia_src/bdikit_context/context.py` | Renders domain system prompt via Jinja2 |
| `CodeContext.auto_context()` | `/opt/harmonia_src/code_context/context.py` | Returns hardcoded code assistant prompt |
| `PromptLoader` | `/opt/harmonia_src/bdikit_context/prompts/__init__.py` | Loads and renders Jinja2 templates |
| `ReActAgent.update_prompt()` | `archytas` package (installed) | Rebuilds system message |

### Existing Debug Hook

`Agent.execute()` already has a verbose debug path:
```python
if self.verbose:
    self.debug(event_type="llm_request", content=messages)
```

However, this logs **every** request (including follow-up tool calls), produces verbose output mixed into normal logs, and doesn't separate the prompt layers for easy comparison.

---

## Proposed Implementation

### Overview

Two outputs:

**Output A — Stdout print (visual inspection):**
Print the full composed prompt to stdout right after Beaker context initialization completes (before any user interaction). This ends up in the SLURM `.out` log file, so you can see it by reading the log.

**Output B — Structured JSON (systematic comparison):**
A one-shot hook on the agent's first `execute()` call writes a `full_prompt_composition.json` file to the results directory with each prompt layer separated and hashed.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ BDIKitContext.__init__() / CodeContext.__init__()                    │
│   ↓                                                                 │
│   1. Print full prompt to stdout (immediate, for SLURM log)         │
│   2. Register one-shot hook on agent.execute() that writes          │
│      structured JSON on first LLM call (deferred, for results dir)  │
└─────────────────────────────────────────────────────────────────────┘
```

### File 1: `src/prompt_logging.py` (NEW FILE)

```python
"""
Prompt composition logging for Harmonia.

Two capabilities:
1. print_prompt_composition() — prints full prompt to stdout for visual inspection
2. One-shot JSON logger — captures structured prompt layers on first LLM call
"""

import json
import os
import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from langchain_core.messages import BaseMessage


# ============================================================
# OUTPUT A: Stdout printing for visual inspection
# ============================================================

def print_prompt_composition(agent, context_slug: str) -> None:
    """
    Print the full composed prompt to stdout for visual inspection.

    Call this from Context.__init__() AFTER super().__init__() completes.
    At that point, the agent's system message and auto-context are already set.

    This captures:
    - The system message (ReAct prelude + model instructions + tool descriptions)
    - The auto-context message (domain prompt)
    - Model-specific prompt instructions
    - Custom prelude (if any)

    Args:
        agent: The BeakerAgent/BDIKitAgent instance (has .chat_history, .model)
        context_slug: "bdikit_context" or "code_context"
    """
    separator = "=" * 80

    print(f"\n{separator}")
    print(f"FULL PROMPT COMPOSITION — {context_slug}")
    print(f"Model class: {agent.model.__class__.__name__}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(separator)

    # Layer 1: System message
    system_msg = agent.chat_history.system_message
    if system_msg:
        content = system_msg.message.content if hasattr(system_msg, 'message') else str(system_msg)
        print(f"\n{'─' * 40}")
        print("LAYER 1: SYSTEM MESSAGE (ReAct prelude + model instructions)")
        print(f"{'─' * 40}")
        print(content)
        print(f"[{len(content)} chars]")

    # Layer 2: Auto-context message
    auto_ctx = agent.chat_history.auto_context_message
    if auto_ctx:
        content = auto_ctx.content if isinstance(auto_ctx, BaseMessage) else str(auto_ctx)
        # If it's an AutoContextMessage wrapper, get inner content
        if hasattr(auto_ctx, 'content'):
            content = auto_ctx.content
        print(f"\n{'─' * 40}")
        print("LAYER 2: AUTO-CONTEXT MESSAGE (domain prompt)")
        print(f"{'─' * 40}")
        print(content)
        print(f"[{len(content)} chars]")

    # Layer 3: Model-specific prompt instructions (logged separately for awareness)
    model_instructions = getattr(agent.model, 'MODEL_PROMPT_INSTRUCTIONS', '')
    print(f"\n{'─' * 40}")
    print("MODEL-SPECIFIC PROMPT INSTRUCTIONS")
    print(f"{'─' * 40}")
    if model_instructions.strip():
        print(model_instructions)
        print(f"[{len(model_instructions)} chars]")
    else:
        print("(none — empty for this model class)")

    # Custom prelude
    custom_prelude = getattr(agent, 'custom_prelude', None)
    if custom_prelude:
        print(f"\n{'─' * 40}")
        print("CUSTOM PRELUDE (overrides default ReAct prelude)")
        print(f"{'─' * 40}")
        print(custom_prelude)
        print(f"[{len(custom_prelude)} chars]")

    # User preamble
    preamble = agent.chat_history.user_preamble
    if preamble:
        content = preamble.message.content if hasattr(preamble, 'message') else str(preamble)
        print(f"\n{'─' * 40}")
        print("USER PREAMBLE")
        print(f"{'─' * 40}")
        print(content)
        print(f"[{len(content)} chars]")

    print(f"\n{separator}")
    print("END PROMPT COMPOSITION")
    print(f"{separator}\n")


# ============================================================
# OUTPUT B: Structured JSON logging for systematic comparison
# ============================================================

def _message_to_dict(msg: BaseMessage) -> dict:
    """Convert a LangChain message to a serializable dict."""
    return {
        "type": msg.__class__.__name__,  # SystemMessage, HumanMessage, AIMessage
        "content": msg.content if isinstance(msg.content, str) else str(msg.content),
    }


def _content_hash(text: str) -> str:
    """SHA-256 hash of content for comparison across runs."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def build_prompt_composition_log(
    messages: list[BaseMessage],
    model_class_name: str,
    model_prompt_instructions: str,
    custom_prelude: Optional[str],
    experiment_name: str,
    run_id: str,
    context_slug: str,
) -> dict:
    """
    Build a structured log of the full prompt composition.

    Args:
        messages: The full list of messages as assembled by ChatHistory.records()
        model_class_name: e.g. "OllamaModel", "AnyLLMModel"
        model_prompt_instructions: The MODEL_PROMPT_INSTRUCTIONS string
        custom_prelude: The custom_prelude if set, else None
        experiment_name: From experiment config
        run_id: 8-char hex run ID
        context_slug: "bdikit_context" or "code_context"

    Returns:
        Dict suitable for JSON serialization
    """
    composition = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "experiment_name": experiment_name,
            "context_type": context_slug,
            "model_class": model_class_name,
        },
        "layers": {},
        "messages_sent_to_llm": [],
        "summary": {},
    }

    # Decompose messages into layers
    # Message order from ChatHistory.records():
    #   0: system_message (SystemMessage)
    #   1: auto_context_message (HumanMessage with domain prompt)
    #   2+: summaries, user_preamble, raw_records

    for i, msg in enumerate(messages):
        msg_dict = _message_to_dict(msg)
        msg_dict["index"] = i
        msg_dict["content_hash"] = _content_hash(msg_dict["content"])
        msg_dict["char_count"] = len(msg_dict["content"])
        composition["messages_sent_to_llm"].append(msg_dict)

    # Identify layers by position and type
    if messages:
        system_content = messages[0].content if isinstance(messages[0].content, str) else str(messages[0].content)
        composition["layers"]["system_message"] = {
            "description": "ReAct prelude + model-specific instructions + tool descriptions",
            "content": system_content,
            "content_hash": _content_hash(system_content),
            "char_count": len(system_content),
            "custom_prelude_used": custom_prelude is not None,
            "custom_prelude_value": custom_prelude,
        }

    if len(messages) > 1:
        auto_ctx_content = messages[1].content if isinstance(messages[1].content, str) else str(messages[1].content)
        composition["layers"]["auto_context_message"] = {
            "description": "Domain-specific system prompt (BDIKit harmonization or Code execution)",
            "content": auto_ctx_content,
            "content_hash": _content_hash(auto_ctx_content),
            "char_count": len(auto_ctx_content),
        }

    # Model-specific instructions (embedded in system message but logged separately for comparison)
    composition["layers"]["model_prompt_instructions"] = {
        "description": "Model-class-specific prompt additions (e.g., OllamaModel tool message handling)",
        "model_class": model_class_name,
        "content": model_prompt_instructions,
        "content_hash": _content_hash(model_prompt_instructions) if model_prompt_instructions else None,
        "char_count": len(model_prompt_instructions),
        "is_empty": len(model_prompt_instructions.strip()) == 0,
    }

    # Summary stats
    total_chars = sum(len(m.content) if isinstance(m.content, str) else len(str(m.content)) for m in messages)
    composition["summary"] = {
        "total_messages": len(messages),
        "total_char_count": total_chars,
        "layer_count": len(composition["layers"]),
        "has_custom_prelude": custom_prelude is not None,
        "has_model_specific_instructions": len(model_prompt_instructions.strip()) > 0,
    }

    return composition


def write_prompt_composition_log(
    composition: dict,
    results_dir: Path,
) -> Path:
    """
    Write prompt composition log to results directory.

    Args:
        composition: Output of build_prompt_composition_log()
        results_dir: Path to the experiment results directory

    Returns:
        Path to the written JSON file
    """
    output_path = results_dir / "full_prompt_composition.json"
    output_path.write_text(json.dumps(composition, indent=2, ensure_ascii=False))
    return output_path


def register_prompt_json_logger(agent, context_slug: str) -> None:
    """
    Register a one-shot monkey-patch on Agent.execute() to capture
    prompt composition as structured JSON on the first LLM call.

    After firing once, it unwraps itself so subsequent calls are unaffected.

    Args:
        agent: The BeakerAgent/BDIKitAgent instance
        context_slug: "bdikit_context" or "code_context"
    """
    results_dir_env = os.environ.get("HARMONIA_RESULTS_DIR")
    if not results_dir_env:
        # No results dir configured — skip JSON logging
        return

    results_dir = Path(results_dir_env)
    original_execute = agent.execute

    async def logging_execute_wrapper(*args, **kwargs):
        """One-shot wrapper: logs prompt composition, then unwraps."""
        # Capture messages the same way execute() does
        records = await agent.chat_history.records(auto_update_context=True)
        messages = [record.message for record in records]

        # Get model-specific info
        model_class_name = agent.model.__class__.__name__
        model_prompt_instructions = getattr(agent.model, 'MODEL_PROMPT_INSTRUCTIONS', '')
        custom_prelude = getattr(agent, 'custom_prelude', None)

        # Build and write log
        run_id = os.environ.get("HARMONIA_RUN_ID", "unknown")
        experiment_name = os.environ.get("HARMONIA_EXPERIMENT_NAME", "unknown")

        composition = build_prompt_composition_log(
            messages=messages,
            model_class_name=model_class_name,
            model_prompt_instructions=model_prompt_instructions,
            custom_prelude=custom_prelude,
            experiment_name=experiment_name,
            run_id=run_id,
            context_slug=context_slug,
        )

        try:
            output_path = write_prompt_composition_log(composition, results_dir)
            print(f"[PROMPT LOG] Structured prompt composition written to: {output_path}")
        except Exception as e:
            print(f"[PROMPT LOG] Warning: Failed to write prompt composition: {e}")

        # Unwrap — restore original execute for all subsequent calls
        agent.execute = original_execute

        # Call the real execute
        return await original_execute(*args, **kwargs)

    agent.execute = logging_execute_wrapper
```

### File 2: Modify `src/bdikit_context/context.py`

**Current signature:**
```python
class BDIKitContext(BeakerContext):
    def __init__(self, beaker_kernel, config):
        super().__init__(beaker_kernel, BDIKitAgent, config)
        self.prompt_loader = get_prompt_loader()
```

**Proposed modification — add after `super().__init__()`:**

```python
from prompt_logging import print_prompt_composition, register_prompt_json_logger

class BDIKitContext(BeakerContext):
    def __init__(self, beaker_kernel, config):
        super().__init__(beaker_kernel, BDIKitAgent, config)
        self.prompt_loader = get_prompt_loader()

        # OUTPUT A: Print full prompt to stdout (visible in SLURM log)
        print_prompt_composition(self.agent, context_slug="bdikit_context")

        # OUTPUT B: Register one-shot JSON logger for first LLM call
        register_prompt_json_logger(self.agent, context_slug="bdikit_context")
```

### File 3: Modify `src/code_context/context.py`

Apply the same pattern. `CodeContext` currently does not have an explicit `__init__`, so one must be added.

**Current:**
```python
class CodeContext(BeakerContext):
    enabled_subkernels = ["python3"]
    SLUG = "code_context"

    async def auto_context(self):
        return f"""You are a Python code execution assistant..."""
```

**Proposed modification:**

```python
from prompt_logging import print_prompt_composition, register_prompt_json_logger

class CodeContext(BeakerContext):
    enabled_subkernels = ["python3"]
    SLUG = "code_context"

    def __init__(self, beaker_kernel, config):
        super().__init__(beaker_kernel, CodeAgent, config)

        # OUTPUT A: Print full prompt to stdout (visible in SLURM log)
        print_prompt_composition(self.agent, context_slug="code_context")

        # OUTPUT B: Register one-shot JSON logger for first LLM call
        register_prompt_json_logger(self.agent, context_slug="code_context")

    async def auto_context(self):
        return f"""You are a Python code execution assistant..."""
```

**Note:** Verify that `CodeAgent` is already imported in `code_context/context.py`. If not, add `from code_context.agent import CodeAgent`.

### File 4: Modify `exec_apptainer_harmonia.sh`

**Purpose:** Pass the results directory path and run ID as environment variables into the container so that `prompt_logging.py` knows where to write the JSON.

**Current state:** The script already sets up `RESULTS_DIR` as a bash variable and creates the results directory. It also has `RUN_ID`.

**Proposed modification — add to the `--env` flags passed to Apptainer:**

Find the section where Apptainer is launched (around the `apptainer exec` / `apptainer run` command). Add these environment variable passes:

```bash
# In the apptainer exec command, add to existing --env flags:
--env HARMONIA_RESULTS_DIR="${RESULTS_DIR}" \
--env HARMONIA_RUN_ID="${RUN_ID}" \
--env HARMONIA_EXPERIMENT_NAME="${EXPERIMENT_NAME}" \
```

**Where to find these variables in the script:**
- `RESULTS_DIR` — already computed from experiment name + timestamp + run ID
- `RUN_ID` — already generated (8-char hex) or passed via `--run-id`
- `EXPERIMENT_NAME` — already parsed from the config YAML

**Also bind-mount the results directory** (if not already bound) so the container can write to it:

```bash
--bind "${RESULTS_DIR}:${RESULTS_DIR}" \
```

---

## What You See in the SLURM Log (Output A)

When you `cat` or `tail` the SLURM `.out` file after a job starts, you'll see:

```
================================================================================
FULL PROMPT COMPOSITION — bdikit_context
Model class: AnyLLMModel
Timestamp: 2025-11-06T17:15:00+00:00
================================================================================

────────────────────────────────────────
LAYER 1: SYSTEM MESSAGE (ReAct prelude + model instructions)
────────────────────────────────────────
You are a helpful assistant. You will be given a task to complete...
[Think, Act, Observe loop instructions...]
[Tool descriptions...]
[1179 chars]

────────────────────────────────────────
LAYER 2: AUTO-CONTEXT MESSAGE (domain prompt)
────────────────────────────────────────
You are a data harmonization agent specialized in mapping biomedical metadata...
## Schema Matching
...
[3581 chars]

────────────────────────────────────────
MODEL-SPECIFIC PROMPT INSTRUCTIONS
────────────────────────────────────────
(none — empty for this model class)

================================================================================
END PROMPT COMPOSITION
================================================================================
```

For an OllamaModel run, the model-specific section would instead show:

```
────────────────────────────────────────
MODEL-SPECIFIC PROMPT INSTRUCTIONS
────────────────────────────────────────
If you receive a message with a role of `tool` in response to a tool being
called, the user has not seen the content of that message...
Be sure to always use the `final_answer` tool to report back to the user.
[~200 chars]
```

---

## What You Get in the Results Directory (Output B)

The `full_prompt_composition.json` file:

```json
{
  "metadata": {
    "timestamp": "2025-11-06T17:15:00+00:00",
    "run_id": "a1b2c3d4",
    "experiment_name": "experiment_1_dou2020_devstral",
    "context_type": "bdikit_context",
    "model_class": "AnyLLMModel"
  },
  "layers": {
    "system_message": {
      "description": "ReAct prelude + model-specific instructions + tool descriptions",
      "content": "You are a helpful assistant...",
      "content_hash": "a1b2c3d4e5f6g7h8",
      "char_count": 1179,
      "custom_prelude_used": false,
      "custom_prelude_value": null
    },
    "auto_context_message": {
      "description": "Domain-specific system prompt (BDIKit harmonization or Code execution)",
      "content": "You are a data harmonization agent specialized in...",
      "content_hash": "h8g7f6e5d4c3b2a1",
      "char_count": 3581
    },
    "model_prompt_instructions": {
      "description": "Model-class-specific prompt additions",
      "model_class": "AnyLLMModel",
      "content": "",
      "content_hash": null,
      "char_count": 0,
      "is_empty": true
    }
  },
  "messages_sent_to_llm": [
    {
      "type": "SystemMessage",
      "content": "You are a helpful assistant...",
      "index": 0,
      "content_hash": "a1b2c3d4e5f6g7h8",
      "char_count": 1179
    },
    {
      "type": "HumanMessage",
      "content": "You are a data harmonization agent...",
      "index": 1,
      "content_hash": "h8g7f6e5d4c3b2a1",
      "char_count": 3581
    }
  ],
  "summary": {
    "total_messages": 2,
    "total_char_count": 4760,
    "layer_count": 3,
    "has_custom_prelude": false,
    "has_model_specific_instructions": false
  }
}
```

---

## Comparison Workflow

With this logging in place, comparing prompts across experiments becomes:

```bash
# Quick visual comparison — just read the SLURM logs
diff <(grep -A 999 'FULL PROMPT COMPOSITION' logs/run_A.out | grep -B 999 'END PROMPT COMPOSITION') \
     <(grep -A 999 'FULL PROMPT COMPOSITION' logs/run_B.out | grep -B 999 'END PROMPT COMPOSITION')

# Compare system messages between two runs (structured)
jq '.layers.system_message.content_hash' results/run_A/full_prompt_composition.json
jq '.layers.system_message.content_hash' results/run_B/full_prompt_composition.json

# Diff the auto-context (domain prompt) between runs
diff <(jq -r '.layers.auto_context_message.content' results/run_A/full_prompt_composition.json) \
     <(jq -r '.layers.auto_context_message.content' results/run_B/full_prompt_composition.json)

# Check if model-specific instructions differ
jq '.layers.model_prompt_instructions' results/run_*/full_prompt_composition.json

# Quick summary across all runs
for f in results/*/full_prompt_composition.json; do
  echo "$(dirname $f | xargs basename): $(jq -c '.summary' $f)"
done
```

---

## Implementation Checklist

1. [ ] Create `src/prompt_logging.py` with:
   - `print_prompt_composition()` — stdout printer for SLURM logs
   - `build_prompt_composition_log()` — JSON builder
   - `write_prompt_composition_log()` — JSON writer
   - `register_prompt_json_logger()` — one-shot execute() wrapper
2. [ ] Modify `src/bdikit_context/context.py` — add `print_prompt_composition()` + `register_prompt_json_logger()` calls to `BDIKitContext.__init__()`
3. [ ] Modify `src/code_context/context.py` — add `__init__()` with same calls, using `context_slug="code_context"`
4. [ ] Modify `exec_apptainer_harmonia.sh` — pass `HARMONIA_RESULTS_DIR`, `HARMONIA_RUN_ID`, `HARMONIA_EXPERIMENT_NAME` as `--env` flags
5. [ ] Test: Run an experiment, verify prompt appears in SLURM `.out` log
6. [ ] Test: Verify `full_prompt_composition.json` appears in results dir
7. [ ] Test: Compare output between OllamaModel and AnyLLMModel runs to verify model-specific instructions are captured
8. [ ] Test: Verify the one-shot JSON behavior (file is written once, subsequent execute() calls are not wrapped)

---

## Design Decisions and Alternatives Considered

### Why two outputs?

**Stdout print (Output A)** is for quick visual inspection — you `cat` the SLURM log and immediately see what the LLM was told. No need to navigate to the results directory or use `jq`. This fires at context initialization time, before any user interaction.

**Structured JSON (Output B)** is for systematic comparison across experiment runs. Content hashes enable quick equality checks. Layer decomposition makes diffs targeted. This fires on the first actual LLM call, so it captures the messages exactly as they're sent.

### Why print at init time instead of first execute()?

The stdout print fires at `Context.__init__()` time because:
- It's visible immediately when tailing the SLURM log
- No need to wait for user interaction
- The system message and auto-context are already fully composed by the time `__init__()` completes (BeakerContext sets them up during `super().__init__()`)

The JSON logger fires at first `execute()` because:
- It captures messages exactly as assembled by `ChatHistory.records()` — the real sequence sent to the LLM
- Includes any additional messages added between init and first call

### Why monkey-patch `execute()` instead of using the existing `verbose` debug?

The existing `self.verbose` debug path in `Agent.execute()`:
- Logs **every** call, not just the first
- Mixes with other debug output
- Uses `self.debug()` which goes to the Beaker debug channel, not a file
- Doesn't separate prompt layers for comparison

The monkey-patch approach:
- Fires exactly once (first call)
- Writes a dedicated, structured file
- Self-removes after firing (no ongoing overhead)
- Captures layer decomposition for comparison

### Why JSON instead of plain text for Output B?

- Machine-readable for automated comparison pipelines
- Content hashes enable quick equality checks without full diff
- Structured layers make it easy to extract specific components
- Can be pretty-printed for human reading with `jq .`

### Why environment variables instead of config file?

- `RESULTS_DIR` and `RUN_ID` are dynamic per-run values
- `exec_apptainer_harmonia.sh` already computes them
- Adding to `.env` would require regeneration per run
- `--env` flags are the simplest injection mechanism

### Risk: `ChatHistory.records()` called twice on first turn

The monkey-patch calls `records(auto_update_context=True)` to capture messages, then `execute()` calls it again. The `auto_update_context` triggers `update_auto_context()` which recomputes the auto-context hash — but since the content hasn't changed between the two calls (same turn), the SHA-1 match means no work is duplicated. The only cost is the extra `records()` call, which is negligible.

### Risk: CodeContext may not have `__init__`

`CodeContext` currently inherits `__init__` from `BeakerContext`. Adding an `__init__` override requires calling `super().__init__(beaker_kernel, CodeAgent, config)` explicitly. Check if `CodeContext` already imports `CodeAgent` — if not, add the import.

### Risk: Stdout print at init sees incomplete auto-context

The `auto_context` is registered during `BeakerContext.__init__()` via `set_auto_context()`, but its content_updater hasn't been called yet at that point — it fires on the first `records()` call. So the stdout print reads the `default_content` of the `AutoContextMessage`, which may be "Default context" (the literal string passed to `set_auto_context()`), not the actual rendered prompt.

**Mitigation:** In `print_prompt_composition()`, after reading `auto_context_message`, also call `await self.auto_context()` directly and print that as "DOMAIN PROMPT (from auto_context())". This is the actual content that will be used. Alternatively, make `print_prompt_composition` async and call `auto_context_message.update_content()` first.

**Simplest mitigation:** Make the print function async and trigger the update:
```python
async def print_prompt_composition(agent, context, context_slug):
    # Force auto-context update so we see the real content
    auto_ctx_content = await context.auto_context()
    # ... print auto_ctx_content instead of reading from chat_history
```

Then call it with:
```python
asyncio.ensure_future(print_prompt_composition(self.agent, self, "bdikit_context"))
```

Or simpler: call `context.auto_context()` directly since it's the source of truth.

---

## Dependencies

- Python standard library only (`json`, `hashlib`, `os`, `datetime`, `pathlib`, `asyncio`)
- `langchain_core.messages.BaseMessage` (already available in container)
- No new pip packages required

---

## Amendment: New Considerations (13-02-2026)

**Context:** Since this plan was written, the configurable prompts feature has been implemented (committed 13-02-2026 in `52db395`). This changes the implementation landscape in several ways.

### A1. BDIKitContext.__init__() is now significantly larger

The current `__init__()` already:
1. Creates per-instance `PromptLoader` from `HARMONIA_PROMPTS_DIR`
2. Calls `super().__init__()` (creates agent)
3. Overrides ReAct prelude from `HARMONIA_REACT_PRELUDE`
4. Calls `_override_tool_descriptions()` from `HARMONIA_TOOL_PROMPTS_DIR`
5. Calls `_log_prompt_config()` (prints JSON of env var settings)
6. In `auto_context()`: prints full system prompt on first call via `_system_prompt_logged` flag

**Impact on prompt logging:** The prompt logging calls must go **after** all overrides (steps 1-4), so the logged prompt reflects the actual configured state. The existing `_log_prompt_config()` and the `_system_prompt_logged` hack in `auto_context()` should be **replaced** by the proper `print_prompt_composition()` and `register_prompt_json_logger()` calls.

### A2. CodeContext now has an explicit `__init__()`

The plan originally noted that `CodeContext` might not have `__init__()`. It now does (added during configurable prompts work), and it already imports `CodeAgent`. The prompt logging calls can simply be appended to the existing `__init__()`.

### A3. Three additional env vars needed inside the container

The exec script already has `RESULTS_DIR=/workspace/results` inside the container, and `RUN_ID` and `EXPERIMENT_NAME` exist as shell variables. The plan requires:
- `HARMONIA_RESULTS_DIR=/workspace/results` (or reuse existing `RESULTS_DIR`)
- `HARMONIA_RUN_ID=${RUN_ID}`
- `HARMONIA_EXPERIMENT_NAME=${EXPERIMENT_NAME}`

**Decision:** Reuse the existing `RESULTS_DIR` env var (already set to `/workspace/results` at line 862 of exec script) instead of creating a redundant `HARMONIA_RESULTS_DIR`. The register function should read `os.environ.get("RESULTS_DIR")`. For `RUN_ID` and `EXPERIMENT_NAME`, add new `--env` flags since these are not currently passed into the container.

### A4. The async timing issue resolution

The plan flagged that `print_prompt_composition()` at init time may see "Default context" instead of the rendered prompt. The current code already works around this differently — `auto_context()` prints the system prompt on its first call via the `_system_prompt_logged` flag.

**Resolution for Output A:** Make `print_prompt_composition()` async. Call `await context.auto_context()` directly to get the rendered prompt, rather than reading from `chat_history.auto_context_message` which may not be populated yet. Schedule it via `asyncio.ensure_future()` from `__init__()`. However, since `__init__()` is sync and the event loop may not be running yet, the safer approach is:
- Keep Output A (stdout) as a **sync** function that prints only the layers available at init time (system message, custom prelude, model instructions, prompt config env vars).
- For the auto-context layer (domain prompt), rely on the existing first-call print already in `auto_context()`, but clean it up to be part of `print_prompt_composition()`.
- Output B (JSON) fires on first `execute()` via the monkey-patch, at which point `records()` has all messages correctly assembled — this already handles the timing issue.

**Simplest correct approach:** Split Output A into two parts:
- Part 1 (sync, at init): Print system message (ReAct prelude), model instructions, custom prelude, prompt config env vars
- Part 2 (at first auto_context call): Print the rendered domain prompt
- Output B (at first execute): Write full JSON with all layers

### A5. Configurable prompts information should be in the JSON

The structured JSON should include:
- Which `HARMONIA_*` env vars were set (prompt dirs, prelude paths)
- Whether default or custom prompts were used for each layer
- The content hashes of each prompt variant for A/B test identification

This is already partially handled by the existing `_log_prompt_config()` output, but should be merged into the structured JSON.

### A6. Updated implementation checklist

1. [ ] Create `src/prompt_logging.py` (as specified in plan, with amendments from A3 and A5)
2. [ ] Modify `src/bdikit_context/context.py`:
   - Replace `_log_prompt_config()` with `print_prompt_composition()`
   - Remove `_system_prompt_logged` flag from `auto_context()`
   - Add `register_prompt_json_logger()` call at end of `__init__()`
3. [ ] Modify `src/code_context/context.py`:
   - Add `print_prompt_composition()` and `register_prompt_json_logger()` calls to existing `__init__()`
4. [ ] Modify `exec_apptainer_harmonia.sh`:
   - Add `--env HARMONIA_RUN_ID=${RUN_ID}` and `--env HARMONIA_EXPERIMENT_NAME=${EXPERIMENT_NAME}` after line 863
   - `RESULTS_DIR` already set — reuse it
5. [ ] Test: Verify prompt appears in SLURM `.out` log
6. [ ] Test: Verify `full_prompt_composition.json` appears in results dir
7. [ ] Test: Verify the one-shot JSON behavior
