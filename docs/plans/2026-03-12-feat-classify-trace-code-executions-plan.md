---
title: "feat: Classify and separate Beaker internal vs agent code executions in traces"
type: feat
status: completed
date: 2026-03-12
origin: docs/brainstorms/2026-03-12-trace-code-execution-classification-brainstorm.md
---

# Classify and Separate Code Executions in Traces

## Overview

Beaker's kernel injects internal housekeeping code (state introspection, checkpointing) around every agent code execution. Our trace pipeline captures these indiscriminately, making a single agent code cell appear as 5 executions. This plan classifies code executions by pattern-matching Beaker's internal templates, splits them into two trace fields (`agent_code_executions` and `internal_code_executions`), and propagates the separation through the dashboard, OTel spans, conversation.md, and a migration CLI for existing traces.

## Problem Statement

When the agent runs 1 code cell, Beaker internally executes this sequence:

```
FETCH_STATE → CHECKPOINT_SAVE → [AGENT CODE] → FETCH_STATE → [FETCH_STATE]
```

The current `extract_code_executions()` in `src/automation/tracing.py:281-344` treats every `execute_input` message identically. This inflates code execution counts in trace.json, the dashboard, and OTel spans, making trace analysis unreliable.

(See brainstorm: `docs/brainstorms/2026-03-12-trace-code-execution-classification-brainstorm.md`)

## Proposed Solution

### Detection Signatures

Two Beaker internal code templates need detection, based on stable strings from `beaker_kernel/subkernels/python.py`:

**FETCH_STATE_CODE** (lines 28-125) — state introspection:
```
Unique signature: '_result = {\n    "modules": {},\n    "variables": {},\n    "functions": {},\n    "classes": {}\n}'
Also contains: '_SubkernelStateEncoder', 'import dill as _dill', '_inspect.getdoc'
```

**SAVE_STATE_CODE** (lines 134-166) — checkpoint serialization:
```
Unique signature: '_dill.dump(_value, _f)' combined with '/{_name}.pkl'
Also contains: '_SubkernelStateEncoder', 'import dill as _dill'
Distinguishing: does NOT contain '"modules": {}'
```

**Classification function** — a pure function `classify_code_execution(code: str) -> str` that returns one of:
- `"fetch_state"` — matches FETCH_STATE_CODE signature
- `"checkpoint_save"` — matches SAVE_STATE_CODE signature
- `"unknown_internal"` — contains `_SubkernelStateEncoder` but doesn't match either known pattern (catches future Beaker template variants)
- `"agent"` — everything else

(See brainstorm for decision rationale on three internal categories)

### Architecture

```
extract_code_executions(raw_messages)
    │
    ├── parse messages (unchanged logic)
    │
    ├── for each execution:
    │     classify_code_execution(code) → category
    │
    └── return {
          "agent_code_executions": [...],      # category == "agent"
          "internal_code_executions": [...]     # all others, with "category" field added
        }
```

## Implementation Phases

### Phase 1: Classification Core (`src/automation/tracing.py`)

**File:** `src/automation/tracing.py`

**1a. Add `classify_code_execution()` function** (new, ~30 lines)

```python
def classify_code_execution(code: str) -> str:
    """Classify a code execution as agent code or Beaker internal.

    Returns: "fetch_state", "checkpoint_save", "unknown_internal", or "agent".
    """
    # FETCH_STATE_CODE: introspects kernel state into modules/variables/functions/classes
    if '"modules": {}' in code and '"variables": {}' in code and '_SubkernelStateEncoder' in code:
        return "fetch_state"

    # SAVE_STATE_CODE: serializes variables to .pkl via dill
    if '_dill.dump(_value, _f)' in code and '.pkl' in code and '_SubkernelStateEncoder' in code:
        return "checkpoint_save"

    # Catch-all for other Beaker internals: uses _SubkernelStateEncoder but didn't
    # match either known pattern above (guards against future Beaker template variants)
    if '_SubkernelStateEncoder' in code:
        return "unknown_internal"

    return "agent"
```

**1b. Modify `extract_code_executions()` return type** (lines 281-344)

Change from `list[dict]` to `dict[str, list[dict]]`:

```python
def extract_code_executions(raw_messages: list[dict]) -> dict[str, list[dict]]:
    """
    Parse raw WebSocket messages to extract structured code executions,
    classified into agent vs Beaker-internal.

    Returns dict with keys:
      - "agent_code_executions": list of agent code execution dicts
      - "internal_code_executions": list of Beaker-internal execution dicts
        (each has extra "category" field: fetch_state|checkpoint_save|unknown_internal)
    """
    # ... existing parsing logic unchanged ...

    # After building `executions` list, classify:
    agent_execs = []
    internal_execs = []
    for exc in executions:
        category = classify_code_execution(exc["code"])
        if category == "agent":
            agent_execs.append(exc)
        else:
            exc_with_cat = {**exc, "category": category}
            internal_execs.append(exc_with_cat)

    return {
        "agent_code_executions": agent_execs,
        "internal_code_executions": internal_execs,
    }
```

- [x] Add `classify_code_execution()` function
- [x] Change `extract_code_executions()` return type to `dict[str, list[dict]]`
- [x] Add classification step after existing parse loop
- [x] Update docstring and type hints
- [x] Add unit tests for classification (see Phase 5)

### Phase 2: Trace Format (`src/automation/logger.py`)

**File:** `src/automation/logger.py`

**2a. Update `TurnRecord` dataclass** (line 26)

Replace:
```python
code_executions: list[dict] = field(default_factory=list)
```
With:
```python
agent_code_executions: list[dict] = field(default_factory=list)
internal_code_executions: list[dict] = field(default_factory=list)
```

**2b. Update `TraceLogger.log_turn()` signature** (lines 102-135)

Replace `code_executions` parameter with `agent_code_executions` and `internal_code_executions`:

```python
def log_turn(
    self,
    ...
    agent_code_executions: list[dict] = None,
    internal_code_executions: list[dict] = None,
    ...
) -> None:
```

**2c. Update `ConversationLogger.log_turn()`** (lines 249-268)

Add optional `agent_code_executions` parameter. When present, render code blocks after the agent response:

```python
def log_turn(
    self,
    turn: int,
    user_message: str,
    agent_response: str,
    response_type: str = "llm_response",
    agent_code_executions: list[dict] = None,
) -> None:
    self.lines.extend([
        f"## Turn {turn}",
        "",
        f"**User**: {user_message}",
        "",
        f"**Agent** ({response_type}):",
        "",
        agent_response,
        "",
    ])

    # Render agent code executions
    if agent_code_executions:
        self.lines.append(f"**Code Executions ({len(agent_code_executions)})**")
        self.lines.append("")
        for i, ce in enumerate(agent_code_executions):
            status = ce.get("status", "?")
            self.lines.extend([
                f"*Execution {i + 1}* [{status}]",
                "",
                "```python",
                ce.get("code", "").rstrip(),
                "```",
                "",
            ])
            if ce.get("stdout"):
                self.lines.extend([
                    "Output:",
                    "```",
                    ce["stdout"].rstrip(),
                    "```",
                    "",
                ])
            if ce.get("stderr"):
                self.lines.extend([
                    "Stderr:",
                    "```",
                    ce["stderr"].rstrip(),
                    "```",
                    "",
                ])

    self.lines.extend(["---", ""])
```

- [x] Update `TurnRecord` fields: `agent_code_executions`, `internal_code_executions`
- [x] Update `TraceLogger.log_turn()` signature and body
- [x] Update `ConversationLogger.log_turn()` to accept and render agent code executions

### Phase 3: Update Callers (`runner.py`, `manual_runner.py`)

Both runners call `extract_code_executions()` and pass results to `trace_logger.log_turn()` and `conversation_logger.log_turn()`. Update both to unpack the new return dict.

**File:** `src/automation/runner.py` (lines 257, 273-299, 317-335)

```python
# Before:
code_execs = extract_code_executions(response.raw_messages)

# After:
classified_execs = extract_code_executions(response.raw_messages)
agent_execs = classified_execs["agent_code_executions"]
internal_execs = classified_execs["internal_code_executions"]
```

Update OTel spans — only create TOOL spans for agent executions (see brainstorm decision #5):

```python
# Before:
for exec_data in code_execs:
    with tool_span(...):

# After:
for exec_data in agent_execs:
    with tool_span(...):
```

Update `trace_logger.log_turn()` call:
```python
self.trace_logger.log_turn(
    ...
    agent_code_executions=agent_execs,
    internal_code_executions=internal_execs,
    ...
)
```

Update `conversation_logger.log_turn()` call:
```python
self.conversation_logger.log_turn(
    ...
    agent_code_executions=agent_execs,
)
```

**File:** `src/automation/manual_runner.py` (lines 305, 318-340, 364, 382-395)

Same pattern — update both the `llm_response` handler (line 297+) and the `code_cell` handler (line 356+).

- [x] Update `runner.py`: unpack classified result, agent-only OTel spans, pass both fields to trace_logger, pass agent to conversation_logger
- [x] Update `runner.py`: same for decision turn block (lines 316-335)
- [x] Update `manual_runner.py`: same for llm_response handler
- [x] Update `manual_runner.py`: same for code_cell handler

### Phase 4: Dashboard (`src/dashboard/components/turn_accordion.py`)

**File:** `src/dashboard/components/turn_accordion.py` (lines 84-116)

Replace current rendering with:

```python
# Agent code executions (shown by default)
agent_execs = turn.get("agent_code_executions", turn.get("code_executions", []))
if agent_execs:
    children.append(
        html.H6(f"Code Executions ({len(agent_execs)})", className="text-muted mt-2")
    )
    for j, ce in enumerate(agent_execs[:5]):
        # ... existing rendering logic ...

# Internal executions (collapsible, hidden by default)
internal_execs = turn.get("internal_code_executions", [])
if internal_execs:
    internal_children = []
    for j, ce in enumerate(internal_execs[:5]):
        category = ce.get("category", "unknown")
        internal_children.append(html.Strong(f"{category} [{ce.get('status', '?')}]"))
        if ce.get("code"):
            internal_children.append(_format_code_block(ce["code"][:500]))

    children.append(
        html.Details([
            html.Summary(
                f"Internal Executions ({len(internal_execs)})",
                style={"fontSize": "0.85em", "color": "#999", "cursor": "pointer"}
            ),
            html.Div(internal_children)
        ], style={"marginTop": "8px"})
    )
```

Note: the fallback `turn.get("agent_code_executions", turn.get("code_executions", []))` ensures backward compatibility with old traces that haven't been migrated yet.

- [x] Render `agent_code_executions` as main "Code Executions" section
- [x] Render `internal_code_executions` in collapsible `<details>` element
- [x] Add backward-compatibility fallback to old `code_executions` field

### Phase 5: Migration CLI (`code_development_tools_agents/monitoring_and_evaluation/enrich_traces.py`)

**New file.** Standalone script to migrate existing trace.json and conversation.md files.

**CLI Interface:**
```
usage: enrich_traces.py [-h] [--dry-run] [--force] path

Enrich existing trace.json files with classified code executions.

positional arguments:
  path        Path to results directory or specific trace.json file.
              Recursively finds all **/trace.json files.

options:
  --dry-run   Show what would change without writing
  --force     Re-process traces that already have new fields
```

**Core logic:**

```python
def enrich_trace(trace_path: Path, dry_run: bool, force: bool) -> dict:
    """Enrich a single trace.json. Returns stats dict."""
    trace = json.loads(trace_path.read_text())
    turns = trace.get("turns", [])

    stats = {"turns": len(turns), "total_old": 0, "agent": 0, "internal": 0, "skipped": False}

    for turn in turns:
        # Skip if already migrated (unless --force)
        if "agent_code_executions" in turn and not force:
            stats["skipped"] = True
            continue

        # Prefer re-extraction from raw_messages
        if turn.get("raw_messages"):
            classified = extract_code_executions(turn["raw_messages"])
        elif turn.get("code_executions"):
            # Fallback: classify existing code_executions by code content
            classified = classify_existing_executions(turn["code_executions"])
        else:
            classified = {"agent_code_executions": [], "internal_code_executions": []}

        old_count = len(turn.get("code_executions", []))
        stats["total_old"] += old_count
        stats["agent"] += len(classified["agent_code_executions"])
        stats["internal"] += len(classified["internal_code_executions"])

        # Replace fields
        turn["agent_code_executions"] = classified["agent_code_executions"]
        turn["internal_code_executions"] = classified["internal_code_executions"]
        turn.pop("code_executions", None)

    if not dry_run:
        # Backup
        backup = trace_path.with_suffix(".json.bak")
        shutil.copy2(trace_path, backup)
        # Write enriched
        trace_path.write_text(json.dumps(trace, indent=2))

    return stats


def classify_existing_executions(code_executions: list[dict]) -> dict:
    """Classify an existing code_executions list (fallback when raw_messages unavailable)."""
    agent = []
    internal = []
    for ce in code_executions:
        category = classify_code_execution(ce.get("code", ""))
        if category == "agent":
            agent.append(ce)
        else:
            internal.append({**ce, "category": category})
    return {"agent_code_executions": agent, "internal_code_executions": internal}
```

**Conversation.md regeneration:**

After enriching trace.json, regenerate conversation.md from the enriched trace data. Create backup first.

```python
def regenerate_conversation_md(trace_path: Path, trace: dict, dry_run: bool):
    """Regenerate conversation.md from enriched trace data."""
    conv_path = trace_path.parent / "conversation.md"
    if not conv_path.exists():
        return

    if not dry_run:
        shutil.copy2(conv_path, conv_path.with_suffix(".md.bak"))

    # Use ConversationLogger to rebuild
    logger = ConversationLogger(trace_path.parent)
    logger.start_experiment(
        experiment_name=trace.get("experiment_name", ""),
        description=trace.get("description", ""),
        llm_provider=trace.get("llm_provider", ""),
        llm_model=trace.get("llm_model", ""),
    )
    for turn in trace.get("turns", []):
        logger.log_turn(
            turn=turn["turn"],
            user_message=turn["user_message"],
            agent_response=turn["agent_response"],
            response_type=turn["response_type"],
            agent_code_executions=turn.get("agent_code_executions"),
        )
    logger.log_summary(
        total_turns=len(trace.get("turns", [])),
        total_duration=trace.get("total_duration_seconds", 0),
        status=trace.get("status", "completed"),
    )
    if not dry_run:
        logger.save()
```

- [x] Create `enrich_traces.py` with argparse CLI
- [x] Implement `enrich_trace()` with backup and dry-run
- [x] Implement `classify_existing_executions()` fallback
- [x] Implement `regenerate_conversation_md()` from enriched trace
- [x] Import `classify_code_execution` and `extract_code_executions` from `src.automation.tracing` (add repo root to `sys.path` at top of script, matching the pattern used by `read_and_analyze_logs_and_traces_cli.py`)
- [x] Print per-file summary stats

### Phase 6: Tests

**File:** New test file or extend existing test suite.

Test `classify_code_execution()`:
- [x] Test with exact FETCH_STATE_CODE template from Beaker → returns `"fetch_state"`
- [x] Test with exact SAVE_STATE_CODE template from Beaker → returns `"checkpoint_save"`
- [x] Test with agent code (e.g. `from difflib import SequenceMatcher\n...`) → returns `"agent"`
- [x] Test with partial match / edge cases → correct fallback behavior

Test `extract_code_executions()` new return type:
- [x] Test with mixed raw_messages containing both internal and agent executions → correct split
- [x] Test with no internal executions → `internal_code_executions` is empty list
- [x] Test with no agent executions → `agent_code_executions` is empty list

Test migration CLI:
- [x] Test idempotency: running twice produces same result
- [x] Test `--dry-run`: no files modified
- [x] Test backward compatibility: old traces without `raw_messages` still get classified via fallback

## Acceptance Criteria

- [x] Traces from new experiments have `agent_code_executions` and `internal_code_executions` fields (no `code_executions`)
- [x] Dashboard shows only agent code by default; internal code available in collapsible section
- [x] OTel/Phoenix TOOL spans only created for agent code executions
- [x] conversation.md includes agent code executions with code blocks and output
- [x] Migration CLI correctly enriches existing traces (tested on run `b0e6e2a0`)
- [x] Migration CLI creates `.bak` backups and supports `--dry-run`
- [x] Dashboard backward-compatible with un-migrated traces (falls back to `code_executions`)
- [x] Classification correctly identifies both Beaker templates (zero false positives on agent code)

## System-Wide Impact

- **Trace format change:** `code_executions` field replaced by `agent_code_executions` + `internal_code_executions`. Dashboard has backward-compatibility fallback. Log analysis CLI tool scans turn JSON as serialized text, so field rename is transparent to it.
- **No Beaker changes:** All classification happens in Harmonia's trace pipeline, not in Beaker itself.
- **OTel span reduction:** ~60-80% fewer TOOL spans per turn (only agent code, not 5x internal overhead).

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-03-12-trace-code-execution-classification-brainstorm.md](docs/brainstorms/2026-03-12-trace-code-execution-classification-brainstorm.md) — Key decisions: two separate trace fields, three internal categories, pattern-matching detection, agent-only OTel spans, migration CLI with backup.

### Internal References

- Classification target: `src/automation/tracing.py:281-344` (`extract_code_executions`)
- Trace data model: `src/automation/logger.py:12-27` (`TurnRecord`)
- Dashboard rendering: `src/dashboard/components/turn_accordion.py:84-116`
- Automated runner caller: `src/automation/runner.py:257,273-299`
- Manual runner caller: `src/automation/manual_runner.py:305,318-340`
- Beaker FETCH_STATE template: `beaker_kernel/subkernels/python.py:28-125`
- Beaker SAVE_STATE template: `beaker_kernel/subkernels/python.py:134-166`
- Existing CLI tool pattern: `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`
