# Brainstorm: Classify and Separate Code Executions in Traces

**Date:** 2026-03-12
**Status:** Ready for planning

## Problem

Beaker's kernel runs internal housekeeping code (state introspection, checkpointing) around every agent code execution. Our trace capture (`extract_code_executions()`) treats all `execute_input` messages identically, so a turn where the agent runs 1 code cell shows up as "Code Executions (5)" — 4 of which are Beaker internals.

This creates noise in:
- trace.json (`code_executions` list)
- Dashboard turn accordion ("Code Executions (5)")
- OTel/Phoenix TOOL spans
- Any downstream analysis that counts or inspects code executions

### The Beaker Internal Patterns

Per-agent-code-execution, Beaker runs this sequence:

```
FETCH_STATE → CHECKPOINT_SAVE → [AGENT CODE] → FETCH_STATE → [FETCH_STATE]
```

**FETCH_STATE_CODE** (introspection): Builds `{"modules": {}, "variables": {}, "functions": {}, "classes": {}}` JSON summary. Defined in `beaker_kernel/subkernels/python.py:28-125`. Triggered before/after code execution to feed LLM context.

**SAVE_STATE_CODE** (checkpoint): Uses `_dill.dump()` to serialize all variables to `.pkl` files. Defined in `beaker_kernel/subkernels/python.py:134-166`. Triggered before code execution for rollback support.

## What We're Building

Classification of code executions at the `extract_code_executions()` layer in `src/automation/tracing.py`, splitting them into two separate trace fields and propagating the separation through the full pipeline.

### Scope

1. **Classification** in `extract_code_executions()` — pattern-match Beaker internal code and tag each execution with a category
2. **Trace format** — two fields: `agent_code_executions` and `internal_code_executions`
3. **Dashboard** — show agent code only by default; collapsible "Internal Executions" section for debugging
4. **OTel spans** — only create TOOL spans for agent code executions
5. **conversation.md** — add agent code executions (code + stdout/stderr) to the markdown log
6. **Migration CLI** — standalone script to enrich/correct existing trace.json and conversation.md files to the new format

## Why This Approach

Filtering at the extraction layer means all downstream consumers (trace.json, dashboard, OTel, conversation.md, log analysis CLI) automatically get clean data. The internal executions are preserved in a separate field rather than discarded, so they're available for deep debugging when Beaker itself misbehaves.

## Key Decisions

1. **Two separate trace fields** — `agent_code_executions` (what the agent did) and `internal_code_executions` (Beaker housekeeping). Not a single list with type tags.

2. **Three internal categories** — `fetch_state` (introspection with modules/variables/functions/classes dict), `checkpoint_save` (dill.dump serialization), `unknown_internal` (catch-all for other underscore-prefixed internal code).

3. **Detection by code pattern matching** — identify internal code by recognizable signatures in the code string (e.g. `_SubkernelStateEncoder`, `_dill.dump`, `_result = {"modules"`, `import dill as _dill`). Anything that doesn't match = agent code.

4. **Dashboard: agent-only by default** — "Code Executions (N)" shows only agent code. Collapsible "Internal Executions (M)" section below for debugging.

5. **OTel spans: agent-only** — only create TOOL spans for `agent_code_executions`. Internal executions don't pollute Phoenix traces.

6. **conversation.md: add agent code** — render agent_code_executions with code blocks and stdout/stderr. Makes the markdown log self-contained for reviewing what the agent did.

7. **Migration CLI: in-place with backup** — `enrich_traces.py` modifies trace.json and conversation.md in-place, creating `.bak` files first. Accepts a path (directory or file) and recursively finds all trace.json files.

8. **Migration CLI: path-based targeting** — `enrich_traces.py results/` processes all trace.json files found recursively. Also accepts a single trace.json path or a specific results directory.

## Migration CLI Tool

A standalone script to bring existing experiment traces up to the new format. This re-runs the classification logic on the `code_executions` field (or `raw_messages` if available) in each turn of an existing trace.json, splits into `agent_code_executions` and `internal_code_executions`, removes the old `code_executions` field, and regenerates conversation.md with agent code executions included.

### Behavior

- **Input:** Path to a results directory or specific trace.json file. Recursive glob for `**/trace.json`.
- **Backup:** Creates `trace.json.bak` and `conversation.md.bak` before overwriting.
- **Classification source:** Prefers `raw_messages` (re-extract from scratch) if present in the turn. Falls back to classifying the existing `code_executions` list by pattern matching on the `code` field.
- **Idempotent:** If a trace already has `agent_code_executions` and `internal_code_executions`, skip it (or re-process with `--force`).
- **Dry-run mode:** `--dry-run` shows what would change without writing.
- **Summary output:** Print per-file stats (e.g. "trace.json: 12 turns, 34 code_executions → 12 agent + 22 internal").

### Location

`code_development_tools_agents/monitoring_and_evaluation/enrich_traces.py` — alongside the existing log analysis CLI tool.

## Resolved Questions

- **Where to filter?** At the `extract_code_executions()` layer — single point of truth.
- **Discard or keep internals?** Keep in `internal_code_executions` field for debugging.
- **How to detect internal code?** Pattern matching on code strings (signatures unique to Beaker templates).
- **Dashboard behavior?** Agent-only default, collapsible internal section.
- **OTel spans?** Agent-only.
- **conversation.md?** Add agent code executions.

## Affected Files

| File | Change |
|------|--------|
| `src/automation/tracing.py` | `extract_code_executions()` → returns classified dict with two lists |
| `src/automation/logger.py` | `TurnRecord`: replace `code_executions` with `agent_code_executions` + `internal_code_executions` |
| `src/automation/logger.py` | `ConversationLogger.log_turn()`: render agent code executions in markdown |
| `src/automation/runner.py` | Update callers to use new field names |
| `src/automation/manual_runner.py` | Update callers to use new field names |
| `src/dashboard/components/turn_accordion.py` | Split rendering: agent default, internal collapsible |
| OTel span creation (runner.py, manual_runner.py) | Only create TOOL spans for agent executions |
| `code_development_tools_agents/monitoring_and_evaluation/enrich_traces.py` | New CLI tool: migrate existing traces to new format |
