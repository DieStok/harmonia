# Implementation Plan: Logging for Context Management and Tool Telemetry

**Date:** 26 February 2026, 13:21 UTC
**Supersedes:** Nothing (companion to `26_02_2026_1243_new_context_management_implementation_plan.md`)
**Relationship:** This plan should be implemented *alongside* or *immediately after* the context management plan. Several changes here (M2, M4) depend on Archytas modifications from that plan.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Current Logging Architecture](#2-current-logging-architecture)
3. [Changes Overview](#3-changes-overview)
4. [HIGH PRIORITY Changes](#4-high-priority-changes)
   - [H1: Capture chat_history WebSocket messages](#h1-capture-chat_history-websocket-messages)
   - [H2: Fix tool_calls extraction bug](#h2-fix-tool_calls-extraction-bug)
   - [H3: Save experiment config in results](#h3-save-experiment-config-in-results)
5. [MEDIUM PRIORITY Changes](#5-medium-priority-changes)
   - [M1: Add context_metrics to TurnRecord and trace.json](#m1-add-context_metrics-to-turnrecord-and-tracejson)
   - [M2: Log summarization events as structured data](#m2-log-summarization-events-as-structured-data)
   - [M3: Add Archytas event hooks for Beaker relay](#m3-add-archytas-event-hooks-for-beaker-relay)
   - [M4: Extend log analysis tool with context management categories](#m4-extend-log-analysis-tool-with-context-management-categories)
6. [Implementation Order](#6-implementation-order)
7. [Verification Checklist](#7-verification-checklist)
8. [Appendix A: OutboundChatHistory Schema](#appendix-a-outboundchathistory-schema)
9. [Appendix B: Current msg_type Handling Matrix](#appendix-b-current-msg_type-handling-matrix)

---

## 1. Problem Statement

Harmonia runs metadata harmonization experiments and needs to diagnose *why* certain model+harness combinations fail. The current logging captures user messages, agent responses, timing, and raw WebSocket messages — but has **critical gaps**:

1. **Context management is invisible.** There is no per-turn record of how much context is used, whether summarization fired, or what the context window limits are. Yet Beaker *already sends* this data via `chat_history` WebSocket messages — Harmonia just doesn't capture it.

2. **Tool call tracking is broken.** The client checks for `msg_type == "thought"` but Beaker sends `msg_type == "llm_thought"`. Result: `tool_calls` is always `[]` in trace.json, even when the agent used tools. This breaks failure mode 3B ("LLM not using tools") detection.

3. **Experiment config is not preserved.** Results directories don't contain the config that produced them. When correlating failures to settings, you must manually find the config file — which may have been modified since the experiment ran.

4. **Summarization events are unstructured.** Archytas logs summarization to Python `logging.warning()` / `print()`, which ends up in SLURM stdout. It's not machine-parseable and not in trace.json.

5. **The log analysis tool can't detect context management failures.** Problems like "summarization never triggered despite high fill" or "context window unknown" cannot be detected because the data isn't in the trace.

---

## 2. Current Logging Architecture

### 2.1 Data Flow

```
User message
    │
    ▼
BeakerClient.send_message()          ← Harmonia (client.py)
    │  sends llm_request via WebSocket
    ▼
Beaker kernel.llm_request()          ← Beaker (kernel.py:548-639)
    │  invokes agent.execute()
    │  emits: status, llm_thought, beaker__execute_input,
    │         beaker__execute_reply, llm_response, code_cell
    │  then: send_chat_history()      ← KEY: token counts, context info
    ▼
BeakerClient._receive_until_complete()
    │  collects raw_messages
    │  extracts: final content, response_type, tool_calls
    ▼
AgentResponse → TraceLogger.log_turn() → trace.json
                ConversationLogger      → conversation.md
```

### 2.2 What Beaker's `send_chat_history()` Already Sends

After every `llm_request`, Beaker sends a `chat_history` WebSocket message (kernel.py:293-326) with this payload (defined by Archytas's `OutboundChatHistory` dataclass in chat_history.py:114-123):

```python
{
    "records": [                    # per-message records with token_count
        {
            "message": {...},
            "uuid": "abc123",
            "token_count": 450,     # ← per-message token count
            "metadata": {},
            "react_loop_id": 1
        }, ...
    ],
    "system_message": "...",
    "tool_token_usage_estimate": 3500,  # ← tool schema overhead
    "model": {
        "provider": "OllamaModel",
        "model_name": "devstral:latest",
        "context_window": 128000        # ← from model.contextsize()
    },
    "message_token_count": 12000,       # ← sum of message tokens
    "summary_token_count": 500,         # ← sum of summary tokens
    "overhead_token_count": 200,        # ← system message overhead
    "summarization_threshold": 64000,   # ← from model.summarization_threshold
    "token_estimate": 16200             # ← total estimated tokens used
}
```

**This data is already computed and transmitted.** The client simply ignores it.

### 2.3 What's Currently Captured vs. Ignored

| WebSocket msg_type | Captured in client.py | Captured in manual_runner.py | In trace.json |
|---|---|---|---|
| `status` | ✅ (completion signal) | ✅ (as raw_message) | ✅ in raw_messages |
| `llm_response` | ✅ (final content) | ✅ | ✅ |
| `code_cell` | ✅ (final content) | ✅ | ✅ |
| `stream` | ✅ (stdout appended) | ❌ | ✅ in raw_messages |
| `error` | ✅ (traceback) | ✅ | ✅ |
| `llm_thought` | ❌ BUG (checks "thought") | ❌ BUG (checks "thought") | ✅ in raw_messages |
| `chat_history` | ❌ NOT CAPTURED | ❌ NOT CAPTURED | ❌ |
| `debug_event` | ❌ | ❌ | ✅ in raw_messages |
| `beaker__execute_input` | ❌ | ❌ | ✅ in raw_messages |
| `beaker__execute_reply` | ❌ | ❌ | ✅ in raw_messages |
| `kernel_state_info` | ❌ | ❌ | ❌ |
| `llm_observation` | ❌ | ❌ | ✅ in raw_messages |

### 2.4 The tool_calls Bug

In both `client.py:325` and `manual_runner.py:214`:

```python
elif msg_type == "thought":        # ← WRONG: Beaker sends "llm_thought"
    thought = content.get("thought", "")
    if "Action:" in thought:
        tool_calls.append({"thought": thought})
```

Meanwhile, actual WebSocket messages show `msg_type == "llm_thought"`. Evidence from trace raw_messages:
```
Turn 3: llm_thought: thought=Calling tool 'match_values', tool_name=match_values, ...
```

The messages ARE in `raw_messages` (they're captured by the generic collector), but the structured `tool_calls` extraction never fires because of the wrong msg_type string.

---

## 3. Changes Overview

| ID | Priority | Codebases | Effort | Dependencies |
|---|---|---|---|---|
| H1 | HIGH | Harmonia only | ~40 lines | None |
| H2 | HIGH | Harmonia only | ~15 lines | None |
| H3 | HIGH | Harmonia only | ~25 lines | None |
| M1 | MEDIUM | Harmonia only | ~50 lines | H1 |
| M2 | MEDIUM | Archytas + Harmonia | ~60 lines | Context mgmt plan |
| M3 | MEDIUM | Archytas + Beaker + Harmonia | ~85 lines | M2 |
| M4 | MEDIUM | Harmonia (analysis tool) | ~120 lines | M1 |

---

## 4. HIGH PRIORITY Changes

### H1: Capture `chat_history` WebSocket Messages

**Goal:** Extract per-turn context metrics from the `chat_history` message Beaker already sends.

**Why this is the biggest win:** Zero changes to Archytas or Beaker. The data already flows through the WebSocket. We just need to catch it.

#### Step H1.1: Add `context_snapshot` field to `AgentResponse`

**File:** `src/automation/client.py`

Add a new optional field to the `AgentResponse` dataclass:

```python
@dataclass
class AgentResponse:
    """Response from the Beaker agent."""
    content: str
    response_type: str  # "llm_response", "code_cell", "stream", "error"
    raw_messages: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    tool_calls: list[dict] = field(default_factory=list)
    context_snapshot: Optional[dict] = None                      # ← ADD
```

**Line reference:** After line 25 in `src/automation/client.py`.

#### Step H1.2: Capture `chat_history` in `BeakerClient.send_message()`

**File:** `src/automation/client.py`

In the `send_message()` method (lines 276-343), add a local variable and capture logic:

```python
async def send_message(self, message: str, timeout: Optional[float] = None) -> AgentResponse:
    # ... existing code through line 304 ...
    tool_calls = []
    context_snapshot = None                                      # ← ADD

    try:
        async for raw_msg in self._receive_until_complete(msg_id, timeout):
            responses.append(raw_msg)
            msg_type = raw_msg.get("msg_type", "")
            content = raw_msg.get("content", {})

            if msg_type == "llm_response":
                # ... existing ...
            elif msg_type == "code_cell":
                # ... existing ...
            elif msg_type == "stream":
                # ... existing ...
            elif msg_type == "error":
                # ... existing ...
            elif msg_type == "llm_thought":                      # ← FIX (see H2)
                # ... see H2 ...
            elif msg_type == "chat_history":                     # ← ADD
                context_snapshot = _extract_context_snapshot(content)

    except asyncio.TimeoutError:
        response_type = "timeout"
        final_content = f"Request timed out after {timeout} seconds"

    duration = asyncio.get_event_loop().time() - start_time

    return AgentResponse(
        content=final_content,
        response_type=response_type,
        raw_messages=responses,
        duration_seconds=duration,
        tool_calls=tool_calls,
        context_snapshot=context_snapshot,                       # ← ADD
    )
```

**IMPORTANT:** The `chat_history` message is sent by Beaker **after** `llm_response` (see kernel.py:639). However, `_receive_until_complete()` currently breaks on `llm_response` (line 376). The `chat_history` message arrives *after* the break condition.

There are two approaches to handle this:

**Option A (Recommended): Continue reading briefly after completion signal.**

Modify `_receive_until_complete()` to yield one more message after the completion signal:

```python
async def _receive_until_complete(
    self, parent_msg_id: str, timeout: float
) -> AsyncIterator[dict]:
    """Receive messages until the request is complete."""
    end_time = asyncio.get_event_loop().time() + timeout
    got_completion = False
    post_completion_deadline = None

    while True:
        remaining = end_time - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError()

        # After completion, allow a short window for trailing messages (chat_history)
        if got_completion:
            if post_completion_deadline is None:
                post_completion_deadline = asyncio.get_event_loop().time() + 2.0
            if asyncio.get_event_loop().time() >= post_completion_deadline:
                break

        try:
            wait_timeout = 2.0 if got_completion else min(remaining, 30.0)
            msg = await asyncio.wait_for(
                self.ws.receive_json(),
                timeout=wait_timeout,
            )
        except asyncio.TimeoutError:
            if got_completion:
                break  # No more trailing messages
            if asyncio.get_event_loop().time() < end_time:
                continue
            raise

        # Check if this message is for our request
        parent_header = msg.get("parent_header", {})
        if parent_header.get("msg_id") != parent_msg_id:
            continue

        msg_type = msg.get("msg_type", "")
        yield msg

        # Check for completion signals
        if msg_type in ("llm_response", "error", "execute_reply"):
            got_completion = True
        elif msg_type == "status":
            if msg.get("content", {}).get("execution_state") == "idle":
                got_completion = True
```

**Option B (Simpler): Don't modify `_receive_until_complete()`. Instead, let the `chat_history` data come from `raw_messages` post-hoc.**

After constructing the `AgentResponse`, scan `raw_messages` for `chat_history`:

```python
# After the try/except block, before return:
if context_snapshot is None:
    for raw_msg in responses:
        if raw_msg.get("msg_type") == "chat_history":
            context_snapshot = _extract_context_snapshot(raw_msg.get("content", {}))
            break
```

This won't work because `chat_history` arrives after the loop breaks and is NOT in `raw_messages`. **Option A is required.**

#### Step H1.3: Add `_extract_context_snapshot()` helper

**File:** `src/automation/client.py`

Add this function near the top of the file (after imports, before the `AgentResponse` class):

```python
def _extract_context_snapshot(chat_history_content: dict) -> dict:
    """Extract context metrics from a Beaker chat_history WebSocket message.

    The chat_history message is sent by Beaker after every llm_request and
    contains token counts, context window size, and summarization threshold
    from Archytas's OutboundChatHistory dataclass.

    Args:
        chat_history_content: The 'content' dict from a chat_history WebSocket message.

    Returns:
        Dict with context metrics suitable for inclusion in trace.json.
    """
    model_info = chat_history_content.get("model", {})
    context_window = model_info.get("context_window")
    token_estimate = chat_history_content.get("token_estimate")
    summarization_threshold = chat_history_content.get("summarization_threshold")

    snapshot = {
        "token_estimate": token_estimate,
        "context_window": context_window,
        "summarization_threshold": summarization_threshold,
        "message_token_count": chat_history_content.get("message_token_count"),
        "summary_token_count": chat_history_content.get("summary_token_count"),
        "overhead_token_count": chat_history_content.get("overhead_token_count"),
        "tool_token_usage_estimate": chat_history_content.get("tool_token_usage_estimate"),
        "model_provider": model_info.get("provider"),
        "model_name": model_info.get("model_name"),
    }

    # Compute fill percentage if both values are known
    if token_estimate is not None and context_window is not None and context_window > 0:
        snapshot["fill_pct"] = round(100.0 * token_estimate / context_window, 1)
    else:
        snapshot["fill_pct"] = None

    # Compute headroom to summarization threshold
    if token_estimate is not None and summarization_threshold is not None:
        snapshot["tokens_until_summarization"] = summarization_threshold - token_estimate
    else:
        snapshot["tokens_until_summarization"] = None

    return snapshot
```

#### Step H1.4: Capture `chat_history` in `ManualExperimentRunner`

**File:** `src/automation/manual_runner.py`

The manual runner's `_handle_message()` (lines 188-302) also needs the same fix. Since the manual runner passively monitors all WebSocket traffic, `chat_history` messages will arrive naturally.

In `_handle_message()`, add handling for `chat_history` messages associated with pending requests. The manual runner stores pending requests keyed by the *request's* msg_id. But `chat_history` messages have `parent_header.msg_id` matching the original `llm_request` msg_id — so they'll be caught by the existing `elif parent_msg_id in self._pending_requests` branch.

Add a new field to the pending request dict and capture:

```python
# In _handle_message(), line 199-206, when creating a new pending request:
if msg_type == "llm_request":
    user_message = content.get("request", "")
    self._pending_requests[msg_id] = {
        "user_message": user_message,
        "start_time": asyncio.get_event_loop().time(),
        "raw_messages": [msg],
        "tool_calls": [],
        "context_snapshot": None,                               # ← ADD
    }

# In the elif branch (lines 210+), add:
elif parent_msg_id in self._pending_requests:
    pending = self._pending_requests[parent_msg_id]
    pending["raw_messages"].append(msg)

    if msg_type == "llm_thought":                               # ← FIX (see H2)
        # ... (see H2 for fix)
    elif msg_type == "chat_history":                            # ← ADD
        pending["context_snapshot"] = _extract_context_snapshot(content)
    elif msg_type == "llm_response":
        # ... existing turn logging ...
```

Import `_extract_context_snapshot` from `client.py` or duplicate the function. Then pass `context_snapshot` to the trace logger (requires M1 to add the field — but we can store it in `raw_messages` for now).

**Note:** The `_extract_context_snapshot` function should be importable:
```python
from .client import _extract_context_snapshot
```

---

### H2: Fix tool_calls Extraction Bug

**Goal:** Fix the wrong `msg_type` string and extract structured tool data.

#### Step H2.1: Fix msg_type string in `client.py`

**File:** `src/automation/client.py`, line 325

Change:
```python
elif msg_type == "thought":
    # Track tool calls from thoughts
    thought = content.get("thought", "")
    if "Action:" in thought:
        tool_calls.append({"thought": thought})
```

To:
```python
elif msg_type == "llm_thought":
    # Track tool calls from thoughts
    # Beaker sends msg_type "llm_thought" (not "thought")
    # Content has: {"thought": str, "tool_name": str, "tool_input": str}
    tool_call = {
        "thought": content.get("thought", ""),
        "tool_name": content.get("tool_name"),
        "tool_input": content.get("tool_input"),
    }
    tool_calls.append(tool_call)
```

**Why structured data matters:** The log analysis tool's 3B detection ("LLM not using tools") currently checks `if tool_calls is empty`. With structured data, it can also check *which* tools were called and whether they succeeded.

#### Step H2.2: Fix msg_type string in `manual_runner.py`

**File:** `src/automation/manual_runner.py`, line 214

Same fix:
```python
if msg_type == "llm_thought":
    # Beaker sends msg_type "llm_thought" (not "thought")
    tool_call = {
        "thought": content.get("thought", ""),
        "tool_name": content.get("tool_name"),
        "tool_input": content.get("tool_input"),
    }
    pending["tool_calls"].append(tool_call)
```

#### Step H2.3: Verify with existing trace data

After implementing, re-run any experiment and verify that `tool_calls` in trace.json is populated when the agent uses tools. Cross-check with `raw_messages` — any `llm_thought` in raw_messages should correspond to an entry in `tool_calls`.

**Test data:** The trace at `results/dou_harmonization_anyllm_devstral_20260211_155251_d0b5043b/trace.json` has turns with `llm_thought` messages in `raw_messages` but `tool_calls: []`. After the fix, those same turns should have populated `tool_calls`.

---

### H3: Save Experiment Config in Results

**Goal:** Copy the resolved experiment config into the results directory so each result is self-documenting.

#### Step H3.1: Add config saving to `ExperimentRunner.run()`

**File:** `src/automation/runner.py`

After the output directory is created (line 48) and before the experiment starts, save a copy of the config:

```python
# In __init__, after self.output_dir.mkdir() (line 48):

# Save experiment config for provenance
self._save_experiment_config()
```

Add the method:

```python
def _save_experiment_config(self) -> None:
    """Save a snapshot of the experiment configuration to the results directory."""
    import yaml

    config_snapshot = {
        "experiment": {
            "name": self.config.name,
            "description": self.config.description,
            "manual_mode": self.config.manual_mode,
            "dataset_metadata": self.config.dataset_metadata,
            "context": self.config.context,
        },
        "llm": {
            "provider": self.config.llm.provider,
            "model": self.config.llm.model,
            "temperature": self.config.llm.temperature,
            "context_length": self.config.llm.context_length,
        },
        "context_management": {
            "python_kernel": {
                "max_variable_size": self.config.context_management.python_kernel.max_variable_size,
                "state_budget_pct": self.config.context_management.python_kernel.state_budget_pct,
                "type_blacklist": self.config.context_management.python_kernel.type_blacklist,
                "var_whitelist": self.config.context_management.python_kernel.var_whitelist,
            },
            "archytas": {
                "summarization_threshold_pct": self.config.context_management.archytas.summarization_threshold_pct,
                "context_window_override": self.config.context_management.archytas.context_window_override,
                "max_tokens": self.config.context_management.archytas.max_tokens,
                "tool_output_summarization_threshold": self.config.context_management.archytas.tool_output_summarization_threshold,
                "tool_output_snippet_size": self.config.context_management.archytas.tool_output_snippet_size,
                "max_react_steps": self.config.context_management.archytas.max_react_steps,
                "max_errors": self.config.context_management.archytas.max_errors,
                "summarization_model": self.config.context_management.archytas.summarization_model,
                "summarization_model_provider": self.config.context_management.archytas.summarization_model_provider,
            },
        },
        "evaluation": {
            "gold_standard": self.config.evaluation.gold_standard,
            "input_file": self.config.evaluation.input_file,
        },
        "decision_handling": {
            "default_mode": self.config.decision_handling.default_mode,
        },
        "messages": [
            {"content": m.content, "wait_seconds": m.wait_seconds, "decision_mode": m.decision_mode}
            for m in self.config.messages
        ],
        "_metadata": {
            "saved_at": datetime.utcnow().isoformat(),
            "run_id": os.environ.get("RUN_ID", "unknown"),
        },
    }

    config_path = self.output_dir / ".experiment_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_snapshot, f, default_flow_style=False, sort_keys=False)
```

**Note:** Add `import yaml` and `import os` to the imports at top of runner.py (os is already imported).

#### Step H3.2: Add config saving to `ManualExperimentRunner`

**File:** `src/automation/manual_runner.py`

Same pattern, in the `start()` method after the loggers are initialized (after line 101):

```python
# Save experiment config for provenance
self._save_experiment_config()
```

Copy the same `_save_experiment_config()` method into `ManualExperimentRunner`. (Or extract it as a standalone function in a shared utility and import it in both runners.)

---

## 5. MEDIUM PRIORITY Changes

### M1: Add `context_metrics` to TurnRecord and trace.json

**Goal:** Include the context snapshot from H1 as a first-class field in the trace, not buried in raw_messages.

**Depends on:** H1 (context_snapshot capture).

#### Step M1.1: Add `context_metrics` to `TurnRecord`

**File:** `src/automation/logger.py`

Extend the `TurnRecord` dataclass (lines 13-22):

```python
@dataclass
class TurnRecord:
    """Record of a single conversation turn."""
    turn: int
    user_message: str
    agent_response: str
    response_type: str
    tool_calls: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    raw_messages: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    context_metrics: Optional[dict] = None                       # ← ADD
```

#### Step M1.2: Add `context_management_config` to `ExperimentTrace`

**File:** `src/automation/logger.py`

Extend `ExperimentTrace` (lines 26-37):

```python
@dataclass
class ExperimentTrace:
    """Complete trace of an experiment run."""
    experiment_name: str
    description: str
    llm_provider: str
    llm_model: str
    start_time: str
    end_time: Optional[str] = None
    turns: list[TurnRecord] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    status: str = "running"
    error_message: Optional[str] = None
    context_management_config: Optional[dict] = None             # ← ADD
```

Update `to_dict()` (line 39-58) to include the new field:

```python
def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for JSON serialization."""
    return {
        "experiment": {
            "name": self.experiment_name,
            "description": self.description,
        },
        "llm": {
            "provider": self.llm_provider,
            "model": self.llm_model,
        },
        "timing": {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_seconds": self.total_duration_seconds,
        },
        "status": self.status,
        "error_message": self.error_message,
        "context_management_config": self.context_management_config,  # ← ADD
        "turns": [asdict(t) for t in self.turns],
    }
```

#### Step M1.3: Pass `context_metrics` through the logging pipeline

**File:** `src/automation/logger.py`

Extend `TraceLogger.log_turn()` (lines 91-114):

```python
def log_turn(
    self,
    turn: int,
    user_message: str,
    agent_response: str,
    response_type: str,
    tool_calls: list[dict] = None,
    duration_seconds: float = 0.0,
    raw_messages: list[dict] = None,
    context_metrics: dict = None,                                # ← ADD
) -> None:
    """Log a conversation turn."""
    if self.trace is None:
        raise RuntimeError("Experiment not started. Call start_experiment first.")

    record = TurnRecord(
        turn=turn,
        user_message=user_message,
        agent_response=agent_response,
        response_type=response_type,
        tool_calls=tool_calls or [],
        duration_seconds=duration_seconds,
        raw_messages=raw_messages or [],
        context_metrics=context_metrics,                         # ← ADD
    )
    self.trace.turns.append(record)
```

#### Step M1.4: Pass context_metrics from runner to logger

**File:** `src/automation/runner.py`

In `_run_turn()` (lines 150-196), pass the context snapshot:

```python
# Log the turn
self.trace_logger.log_turn(
    turn=self.current_turn,
    user_message=msg_config.content,
    agent_response=response.content,
    response_type=response.response_type,
    tool_calls=response.tool_calls,
    duration_seconds=response.duration_seconds,
    raw_messages=response.raw_messages,
    context_metrics=response.context_snapshot,                   # ← ADD
)
```

#### Step M1.5: Pass context_management_config at experiment start

**File:** `src/automation/runner.py`

After `start_experiment()` is called, set the config:

```python
# In run(), after trace_logger.start_experiment() (line 72-77):
self.trace_logger.trace.context_management_config = {
    "python_kernel": {
        "max_variable_size": self.config.context_management.python_kernel.max_variable_size,
        "state_budget_pct": self.config.context_management.python_kernel.state_budget_pct,
    },
    "archytas": {
        "summarization_threshold_pct": self.config.context_management.archytas.summarization_threshold_pct,
        "context_window_override": self.config.context_management.archytas.context_window_override,
        "max_react_steps": self.config.context_management.archytas.max_react_steps,
        "max_errors": self.config.context_management.archytas.max_errors,
        "summarization_model": self.config.context_management.archytas.summarization_model,
    },
}
```

#### Step M1.6: Same for manual runner

Pass `context_snapshot` from the pending request's `context_snapshot` field (added in H1.4) to the trace logger's `log_turn()` call in `manual_runner.py`'s `_handle_message()` at lines 226, 256, and 283.

#### Resulting trace.json Schema

After M1, each turn in trace.json gains a `context_metrics` field:

```json
{
  "turns": [
    {
      "turn": 1,
      "user_message": "...",
      "agent_response": "...",
      "response_type": "llm_response",
      "tool_calls": [
        {"thought": "...", "tool_name": "run_code", "tool_input": "..."}
      ],
      "duration_seconds": 15.9,
      "context_metrics": {
        "token_estimate": 4200,
        "context_window": 128000,
        "fill_pct": 3.3,
        "summarization_threshold": 64000,
        "tokens_until_summarization": 59800,
        "message_token_count": 3500,
        "summary_token_count": 0,
        "overhead_token_count": 200,
        "tool_token_usage_estimate": 500,
        "model_provider": "OllamaModel",
        "model_name": "devstral:latest"
      },
      "raw_messages": [...],
      "timestamp": "2026-02-10T18:16:06.297483"
    }
  ],
  "context_management_config": {
    "python_kernel": { "max_variable_size": 20000, "state_budget_pct": 25 },
    "archytas": { "summarization_threshold_pct": 50, "context_window_override": null, ... }
  }
}
```

---

### M2: Log Summarization Events as Structured Data

**Goal:** When Archytas summarizes conversation history, emit a structured event that Beaker can relay as a WebSocket message and Harmonia can capture.

**Depends on:** Context management plan (which modifies Archytas's summarizers.py).

#### Step M2.1: Add structured summarization logging in Archytas

**File:** `/hpc/compgen/projects/llm_GEO_project/archytas/archytas/summarizers.py`

The existing code at line 303-309 uses `logger.warning()` to dump full prompts and outputs. Replace with structured logging:

```python
# In default_history_summarizer() or wherever summarization executes:
import json as _json

# After summarization completes, emit a structured log event
summarization_event = {
    "event_type": "summarization",
    "trigger": "history_threshold",          # or "loop_completion"
    "messages_summarized": len(messages_to_summarize),
    "input_tokens_estimate": input_token_count,   # if available
    "output_tokens_estimate": output_token_count,  # if available
    "summarization_model": getattr(summ_model, 'model_name', 'primary'),
    "timestamp": datetime.now(timezone.utc).isoformat(),
}
logger.info("SUMMARIZATION_EVENT: %s", _json.dumps(summarization_event))
```

**Note:** The exact implementation depends on what the context management plan does to `summarizers.py`. This step should be coordinated with that plan's Step 7 (tool output summarization thresholds) and Step 8 (summarization model).

#### Step M2.2: Emit summarization event via Archytas callback (see M3)

If M3 is also implemented, use the callback mechanism instead of just logging.

---

### M3: Add Archytas Event Hooks for Beaker Relay

**Goal:** Clean event-driven architecture: Archytas emits events → Beaker relays via WebSocket → Harmonia captures.

**Depends on:** M2 (structured summarization logging), context management plan.

#### Step M3.1: Add event callback to Archytas Agent

**File:** `/hpc/compgen/projects/llm_GEO_project/archytas/archytas/agent.py`

Add an optional callback in `Agent.__init__()`:

```python
class Agent:
    def __init__(self, ...):
        # ... existing init ...
        self.event_callback: Optional[Callable[[str, dict], None]] = None
```

#### Step M3.2: Emit events from summarizers

**File:** `/hpc/compgen/projects/llm_GEO_project/archytas/archytas/summarizers.py`

After summarization completes:

```python
# Emit event via agent callback if registered
if agent and hasattr(agent, 'event_callback') and agent.event_callback:
    agent.event_callback("summarization_complete", {
        "trigger": trigger_type,
        "messages_summarized": count,
        "summarization_model": model_name,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    })
```

#### Step M3.3: Register callback in Beaker's BeakerAgent

**File:** `/hpc/compgen/projects/llm_GEO_project/beaker-kernel/beaker_kernel/lib/agent.py`

In `BeakerAgent.__init__()`:

```python
class BeakerAgent(ReActAgent):
    def __init__(self, ...):
        super().__init__(...)
        self.event_callback = self._relay_event

    def _relay_event(self, event_type: str, data: dict):
        """Relay Archytas events to the WebSocket as debug_event messages."""
        self.context.beaker_kernel.log(f"archytas_{event_type}", data)
```

This causes summarization events to appear as `debug_event` WebSocket messages with event type `archytas_summarization_complete`.

#### Step M3.4: Capture in Harmonia client

**File:** `src/automation/client.py`

Add `debug_event` handling in `send_message()`:

```python
elif msg_type == "debug_event":
    event_data = content.get("body", {})
    event_name = content.get("event", "")
    if event_name.startswith("archytas_summarization"):
        # Store summarization event alongside context_metrics
        if context_snapshot is None:
            context_snapshot = {}
        context_snapshot.setdefault("summarization_events", []).append(event_data)
```

---

### M4: Extend Log Analysis Tool with Context Management Categories

**Goal:** Add new failure mode categories that detect context management issues using the new `context_metrics` data.

**Depends on:** M1 (context_metrics in trace.json).

#### Step M4.1: Add new problem classes to taxonomy YAML

**File:** `code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml`

Add these new problem classes:

```yaml
  # ===========================================================================
  # Category 6: Context Management Failures
  # ===========================================================================

  - id: "6A"
    category: "context_management"
    name: "Context Window Unknown (Summarization Disabled)"
    description: |
      The model's context window size is null/unknown, which causes
      model.summarization_threshold to return None, which causes
      needs_summarization() to always return False. Summarization is
      effectively disabled. This typically happens with Ollama models
      when the API doesn't report context_length and no
      ARCHYTAS_CONTEXT_WINDOW_OVERRIDE is set.
    severity: "warning"
    detection:
      # COMPOUND LOGIC:
      #   1. context_metrics.context_window is null for any turn
      #   2. context_metrics.summarization_threshold is null
      log_keywords: []
      log_regex: []
      trace_keywords: []
      trace_regex: []
    example:
      source: "trace"
      snippet: |
        "context_metrics": {
          "token_estimate": 45000,
          "context_window": null,
          "summarization_threshold": null,
          "fill_pct": null
        }
    remediation:
      - "Set context_window_override in experiment YAML under context_management.archytas"
      - "Set ARCHYTAS_CONTEXT_WINDOW_OVERRIDE env var"
      - "Update Archytas Ollama model to query the Ollama API for context length"

  - id: "6B"
    category: "context_management"
    name: "High Context Fill Without Summarization"
    description: |
      Context fill percentage exceeded 80% but summarization never
      triggered during the experiment. Either the summarization
      threshold is set too high, or summarization is silently disabled
      (see 6A).
    severity: "warning"
    detection:
      # COMPOUND LOGIC:
      #   1. Any turn has context_metrics.fill_pct > 80
      #   2. No turn has summary_token_count > 0
      #   3. Experiment did not end due to context_window_exhaustion (3E)
      log_keywords: []
      log_regex: []
      trace_keywords: []
      trace_regex: []
    example:
      source: "trace"
      snippet: |
        Turn 5: fill_pct=82.3, summary_token_count=0
        Turn 6: fill_pct=91.7, summary_token_count=0
        Turn 7: response_type=timeout (context exhaustion imminent)
    remediation:
      - "Lower summarization_threshold_pct in experiment YAML"
      - "Verify context_window is correctly detected (see 6A)"
      - "Check if summarization model is configured and accessible"

  - id: "6C"
    category: "context_management"
    name: "Context Fill Growing Monotonically"
    description: |
      Context fill percentage increases every turn without any decrease,
      indicating that summarization is not compressing the conversation
      history even though it should be triggering. May indicate a bug in
      the summarization pipeline.
    severity: "info"
    detection:
      # COMPOUND LOGIC:
      #   1. context_metrics.fill_pct is present for ≥4 turns
      #   2. fill_pct strictly increases across all turns
      #   3. Final fill_pct > 50%
      log_keywords: []
      log_regex: []
      trace_keywords: []
      trace_regex: []
    example:
      source: "trace"
      snippet: |
        Turn 1: fill_pct=3.3
        Turn 2: fill_pct=8.1
        Turn 3: fill_pct=15.7
        Turn 4: fill_pct=28.4
        Turn 5: fill_pct=45.2
    remediation:
      - "Review summarization threshold — may be set too high"
      - "Check if model.contextsize() returns a value"
      - "Look at SLURM logs for summarization errors"

  - id: "6D"
    category: "context_management"
    name: "Experiment Config Missing from Results"
    description: |
      The results directory does not contain .experiment_config.yaml.
      This makes it impossible to determine what settings were active
      during the experiment. Typically means the experiment was run
      before H3 was implemented.
    severity: "info"
    detection:
      # COMPOUND LOGIC:
      #   1. Results directory exists
      #   2. No .experiment_config.yaml in results directory
      log_keywords: []
      log_regex: []
      trace_keywords: []
      trace_regex: []
    example:
      source: "both"
      snippet: |
        Results directory contains:
          trace.json
          conversation.md
        Missing:
          .experiment_config.yaml
    remediation:
      - "Re-run experiment after implementing H3"
      - "Manually identify which config YAML was used by matching experiment name"
```

#### Step M4.2: Implement detection functions

**File:** `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`

Add detection methods following the existing pattern (e.g., `_detect_beaker_server_hung()`):

```python
def _detect_context_window_unknown(self, trace_data: dict) -> Optional[ProblemDetection]:
    """Detect 6A: context_window is null in any turn's context_metrics."""
    for turn in trace_data.get("turns", []):
        cm = turn.get("context_metrics")
        if cm and cm.get("context_window") is None and cm.get("token_estimate") is not None:
            return ProblemDetection(
                problem_id="6A",
                evidence=f"Turn {turn['turn']}: context_window=null, token_estimate={cm['token_estimate']}",
                affected_turns=[turn["turn"]],
            )
    return None


def _detect_high_fill_no_summarization(self, trace_data: dict) -> Optional[ProblemDetection]:
    """Detect 6B: fill_pct > 80% but summary_token_count always 0."""
    max_fill = 0
    any_summarization = False
    high_fill_turns = []

    for turn in trace_data.get("turns", []):
        cm = turn.get("context_metrics")
        if cm:
            fill = cm.get("fill_pct")
            if fill is not None and fill > max_fill:
                max_fill = fill
            if fill is not None and fill > 80:
                high_fill_turns.append(turn["turn"])
            if cm.get("summary_token_count", 0) > 0:
                any_summarization = True

    if high_fill_turns and not any_summarization:
        return ProblemDetection(
            problem_id="6B",
            evidence=f"Max fill {max_fill:.1f}%, no summarization. Turns >80%: {high_fill_turns}",
            affected_turns=high_fill_turns,
        )
    return None


def _detect_monotonic_context_growth(self, trace_data: dict) -> Optional[ProblemDetection]:
    """Detect 6C: fill_pct strictly increasing across all turns."""
    fills = []
    for turn in trace_data.get("turns", []):
        cm = turn.get("context_metrics")
        if cm and cm.get("fill_pct") is not None:
            fills.append((turn["turn"], cm["fill_pct"]))

    if len(fills) < 4:
        return None

    is_monotonic = all(fills[i][1] < fills[i+1][1] for i in range(len(fills)-1))
    final_fill = fills[-1][1]

    if is_monotonic and final_fill > 50:
        return ProblemDetection(
            problem_id="6C",
            evidence=f"Fill monotonically increasing: {fills[0][1]:.1f}% → {final_fill:.1f}% across {len(fills)} turns",
            affected_turns=[t for t, _ in fills],
        )
    return None


def _detect_missing_experiment_config(self, results_dir: Path) -> Optional[ProblemDetection]:
    """Detect 6D: .experiment_config.yaml missing from results."""
    config_path = results_dir / ".experiment_config.yaml"
    if not config_path.exists():
        return ProblemDetection(
            problem_id="6D",
            evidence=f"No .experiment_config.yaml in {results_dir.name}",
            affected_turns=[],
        )
    return None
```

Register these detectors in the analysis pipeline's main detection loop.

#### Step M4.3: Update the YAML schema version

Bump `schema_version` from `"1.1"` to `"1.2"` in the YAML file header and add a datestamp comment.

---

## 6. Implementation Order

The recommended implementation sequence, with dependencies:

```
Phase 1 — Harmonia-only fixes (can be done immediately):
  ┌─── H2: Fix tool_calls msg_type bug         (15 min, no dependencies)
  ├─── H3: Save experiment config in results    (20 min, no dependencies)
  └─── H1: Capture chat_history messages        (45 min, no dependencies)

Phase 2 — Trace schema extension:
  └─── M1: Add context_metrics to trace.json    (30 min, depends on H1)

Phase 3 — Analysis tool extension:
  └─── M4: New failure categories in analysis   (60 min, depends on M1)

Phase 4 — Archytas instrumentation (coordinate with context management plan):
  ├─── M2: Structured summarization logging     (30 min, Archytas changes)
  └─── M3: Event hooks + Beaker relay           (45 min, Archytas + Beaker)
```

**Phase 1 is independent** and can be implemented without any Archytas or Beaker changes. Do this first.

**Phase 4 should be done as part of the context management plan implementation**, not separately.

---

## 7. Verification Checklist

After each phase, verify:

### Phase 1 (H1, H2, H3)
- [ ] Run an automated experiment with an Ollama model
- [ ] Check trace.json: `tool_calls` should be non-empty for turns where the agent used tools
- [ ] Check that `.experiment_config.yaml` exists in results directory
- [ ] Check that `chat_history` messages appear in `raw_messages` (they already do — verify H1's `_receive_until_complete` changes don't break the existing flow)
- [ ] If H1 Option A is implemented: verify that AgentResponse.context_snapshot is populated

### Phase 2 (M1)
- [ ] Check trace.json: each turn should have a `context_metrics` field (or null if chat_history wasn't available)
- [ ] Check trace.json top-level: `context_management_config` should be present
- [ ] Verify `fill_pct` is a reasonable number (0-100)
- [ ] Verify `tokens_until_summarization` decreases as conversation progresses

### Phase 3 (M4)
- [ ] Run the log analysis tool on a results directory with context_metrics
- [ ] Verify that 6A is detected for experiments where context_window is null
- [ ] Verify that 6D is detected for old experiments without `.experiment_config.yaml`
- [ ] Verify that existing detections (1A-5A) still work correctly

### Phase 4 (M2, M3)
- [ ] Run an experiment that triggers summarization (use a small context_window_override like 4000 to force it)
- [ ] Check SLURM logs for structured SUMMARIZATION_EVENT log lines
- [ ] If M3: check trace.json raw_messages for `debug_event` with `archytas_summarization_complete`
- [ ] Verify the log analysis tool can detect summarization events in the trace

---

## Appendix A: OutboundChatHistory Schema

Full schema of the `chat_history` WebSocket message as sent by Beaker (kernel.py:293-326):

```
Source: Archytas chat_history.py, lines 107-123

@dataclass
class OutboundModel:
    provider: str                 # e.g. "OllamaModel"
    model_name: str               # e.g. "devstral:latest"
    context_window: Optional[int] # from model.contextsize()

@dataclass
class OutboundChatHistory:
    records: list[RecordType]          # per-message records
    system_message: Optional[str]      # system prompt text
    tool_token_usage_estimate: Optional[int]  # tool schema overhead
    model: OutboundModel               # model info
    token_estimate: Optional[int]      # total estimated tokens
    message_token_count: Optional[int] # sum of message tokens
    summary_token_count: Optional[int] # sum of summary tokens
    overhead_token_count: Optional[int]# system message overhead
    summarization_threshold: Optional[int]  # from model.summarization_threshold
```

Beaker constructs this at kernel.py:300-324:
```python
output = OutboundChatHistory(
    records=[{
        "message": { "text": record.message.text, "raw_content": record.message.content, ...},
        "uuid": record.uuid,
        "token_count": record.token_count,       # ← per-message tokens
        "metadata": record.metadata,
        "react_loop_id": record.react_loop_id,
    } for record in records],
    system_message=chat_history.system_message.message.text,
    tool_token_usage_estimate=chat_history.tool_token_estimate,
    model=OutboundModel(
        provider=model.__class__.__name__,
        model_name=model.model_name,
        context_window=model.contextsize()       # ← context window
    ),
    message_token_count=sum(...),
    summary_token_count=sum(...),
    overhead_token_count=chat_history.token_overhead,
    summarization_threshold=model.summarization_threshold,  # ← threshold
    token_estimate=chat_history._token_estimate or await chat_history.token_estimate(model),
)
```

---

## Appendix B: Current msg_type Handling Matrix

Comprehensive matrix of all WebSocket msg_types, where they originate, and where they're handled:

| msg_type | Emitter | client.py handles | manual_runner.py handles | In raw_messages | Should handle |
|---|---|---|---|---|---|
| `status` | kernel.py | ✅ (completion) | ✅ (via raw_msgs) | ✅ | ✅ (no change) |
| `llm_response` | kernel.py:622 | ✅ | ✅ | ✅ | ✅ (no change) |
| `code_cell` | kernel.py:614 | ✅ | ✅ | ✅ | ✅ (no change) |
| `stream` | kernel.py:583 | ✅ | ❌ | ✅ | ✅ (no change) |
| `error` | kernel.py:594 | ✅ | ✅ | ✅ | ✅ (no change) |
| `llm_thought` | kernel.py:248 | ❌ (bug: "thought") | ❌ (bug: "thought") | ✅ | **FIX (H2)** |
| `chat_history` | kernel.py:639 | ❌ | ❌ | ❌ (arrives too late) | **ADD (H1)** |
| `debug_event` | kernel.py:503 | ❌ | ❌ | ✅ | ADD (M3, optional) |
| `llm_observation` | agent.py:123 | ❌ | ❌ | ✅ | Optional (low priority) |
| `beaker__execute_input` | context.py | ❌ | ❌ | ✅ | No (in raw_messages) |
| `beaker__execute_reply` | context.py | ❌ | ❌ | ✅ | No (in raw_messages) |
| `kernel_state_info` | kernel.py:286 | ❌ | ❌ | ❌ | Optional (low priority) |
| `preview` | kernel.py:279 | ❌ | ❌ | ❌ | No (UI only) |
| `llm_reply` | kernel.py | ❌ | ❌ | ✅ | No (completion signal) |
