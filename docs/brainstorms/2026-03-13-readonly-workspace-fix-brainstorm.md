# Brainstorm: Fix Read-Only Workspace Preventing LLM File Output

**Date:** 2026-03-13
**Status:** Complete — proceeding to planning

## What We're Building

A two-part fix to ensure LLM agents can write output files during Harmonia experiments:

1. **Infrastructure:** Bind-mount `/workspace` as writable inside the Apptainer container, while keeping `/workspace/data/` read-only via overlay.
2. **Prompts:** Update all system prompts and config YAML messages to explicitly direct the LLM to save output to `results/`.
3. **Observability:** Log when the LLM writes files to `/workspace` (outside `results/`) so we can detect misplaced output.

## Why This Approach

### Problem Evidence

Multiple recent experiments fail silently — the LLM cannot persist any output:

| Experiment | Errors | Behavior |
|---|---|---|
| bdikit-tools_qwen3.5-9b (48213672) | 24 read-only errors | Tried `/workspace/data/`, then cwd |
| code-context_qwen3.5-4b (48333911) | 9 read-only errors | Fell back to StringIO (no disk output) |
| codeact_deepseek-v3.2 (48222429) | 12 read-only errors | Acknowledged error, stayed in-memory |

### Root Cause

Two interacting problems:
1. `/workspace` (cwd) is inside the Apptainer squashfs image — **read-only by default**. No `--writable-tmpfs` flag is set.
2. System prompts and config messages never tell the LLM that `results/` exists or is writable. The LLM tries to write to `data/` (read-only) or cwd (also read-only), then gives up.

### Why Belt-and-Suspenders

- **Bind alone** would fix writes but scatter output across `/workspace` instead of `results/`
- **Prompts alone** would fix explicit saves but break intermediate/scratch files (LLMs write temp files unpredictably)
- **Both together:** intermediate writes succeed anywhere in `/workspace`, final artifacts land in `results/` via prompt guidance

## Key Decisions

1. **Bind `workspace_mount/` to `/workspace`** — already created at line 977-978 of exec script but never actually bound. Data `:ro` overlay remains.
2. **Update all three system prompt families** — codeact_context, code_context, bdikit_context — to describe the workspace structure and direct output to `results/`.
3. **Update config YAML messages** — change bare filenames like `"dou_harmonized.csv"` to `"results/dou_harmonized.csv"`.
4. **Add logging** — report in experiment logs when files are written outside `results/` in the workspace.

## Open Questions

None — all resolved during brainstorming.
