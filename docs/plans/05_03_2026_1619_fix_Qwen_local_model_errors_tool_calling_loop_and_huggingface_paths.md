# Fix Qwen Local Model Errors: Tool Calling Loop & HuggingFace Paths

**Date:** 2026-03-05
**Trigger:** Failed experiment run `e829293e` (qwen3.5:9b via Ollama, SLURM job 47473183)
**Status:** Implemented and committed

---

## Problem Analysis

Log analysis of the failed run revealed a chain of errors:

1. BDI-Kit's Magneto schema matcher tries to download `sentence-transformers/all-mpnet-base-v2`
2. HuggingFace model cache defaults to `~/.cache/huggingface`, which resolves to `/hpc/compgen/users/dstoker/.cache/huggingface` -- read-only inside the Apptainer container
3. `match_schema()` tool fails with `OSError: [Errno 30] Read-only file system`
4. The LLM retries the exact same `match_schema()` call repeatedly (no guardrail)
5. All 30 ReAct steps are burned retrying the same failing tool, producing no output

Secondary issues: `ollama_launcher.py` was invoked with bare `python3` (system Python lacking dependencies), and several pre-existing shellcheck warnings in `exec_apptainer_harmonia.sh`.

## Error Priority Table

| Priority | Error | Impact | Root Cause |
|----------|-------|--------|------------|
| **P0** | `OSError: Read-only file system` on HF cache write | Fatal -- blocks all schema matching | `HF_HOME` not set; defaults to read-only bind mount |
| **P1** | 30 identical `match_schema()` retries | Burns all steps; no useful output | No consecutive tool error limit in Archytas ReAct loop |
| **P2** | `python3: command not found` for ollama_launcher | Ollama management fails on some nodes | Bare `python3` instead of `.venv/bin/python` |
| P3 | Ollama `unexpected EOF` / `connection reset` | Transient; self-recovers | Network-level timeout between Ollama client and server |

## Plan

### Fix 1 (P0): Redirect HuggingFace cache to writable location

**File:** `exec_apptainer_harmonia.sh`

Set `HF_HOME` and `TRANSFORMERS_CACHE` environment variables inside the Apptainer container to point at `/workspace/results/.cache/huggingface` (writable bind mount). This ensures the sentence-transformers model downloads succeed.

### Fix 2 (P1): Add consecutive tool error guardrail to Archytas

This requires changes across two repositories and the full configuration pipeline.

#### 2a. Archytas ReAct loop (`/hpc/compgen/projects/llm_GEO_project/archytas/archytas/react.py`)

- Add `max_consecutive_tool_errors` attribute to `ReActAgent.__init__` (default: `inf` for backwards compatibility)
- Add tracking variables: `_consecutive_tool_errors` counter and `_last_failed_tool` name
- Reset counters at the start of each task (`react_async`)
- Reset counters after successful tool execution
- In the tool exception handler: increment counter if same tool fails again, reset if different tool. When counter >= `max_consecutive_tool_errors`, raise `FailedTaskError`

#### 2b. Harmonia config dataclass (`src/automation/config.py`)

- Add `max_consecutive_tool_errors: Optional[int] = 3` to `ArchytasContextConfig`
- Parse it in `ExperimentConfig.from_dict()`

#### 2c. Environment generation (`generate_env.py`)

- Add `'max_consecutive_tool_errors': ('ARCHYTAS_MAX_CONSECUTIVE_TOOL_ERRORS', None)` to the `arch_vars` dict so it gets written to the `.env` file

#### 2d. Context initialization (`src/bdikit_context/context.py`, `src/code_context/context.py`)

- Read `ARCHYTAS_MAX_CONSECUTIVE_TOOL_ERRORS` from environment and patch `self.agent.max_consecutive_tool_errors` after construction (same pattern as `max_react_steps` and `max_errors`)

#### 2e. Existing experiment configs (38 YAML files in `experiments/.../configs/automated/`)

- Add `max_consecutive_tool_errors: 3` to the `context_management.archytas` section of all configs

### Fix 3 (P2): Use correct Python interpreter for ollama_launcher.py

**File:** `exec_apptainer_harmonia.sh`

Change bare `python3` to `"${SCRIPT_DIR}/.venv/bin/python"` at both invocation sites (lines 37 and 669) to use the venv that has all required dependencies.

### Fix 4 (housekeeping): Shellcheck warnings

Fix pre-existing shellcheck warnings in `exec_apptainer_harmonia.sh` (SC2155, SC2086, SC2034) that block the pre-commit hook.

---

## Implementation Summary

All changes implemented and committed on 2026-03-05.

### Commits

| Repo | Commit | Description |
|------|--------|-------------|
| `/hpc/compgen/projects/llm_GEO_project/archytas` | `39fbcef` | Add consecutive tool error guardrail to ReAct loop |
| Harmonia (this repo) | `d2a2bf9` | Fix HF cache crash, add consecutive tool error guardrail, fix Python interpreter |

### Files Changed (Harmonia commit: 44 files)

| File | Change |
|------|--------|
| `exec_apptainer_harmonia.sh` | P0: Added `HF_HOME`/`TRANSFORMERS_CACHE` env vars. P2: Changed `python3` to `.venv/bin/python`. Shellcheck fixes. |
| `generate_env.py` | Added `ARCHYTAS_MAX_CONSECUTIVE_TOOL_ERRORS` env var mapping |
| `src/automation/config.py` | Added `max_consecutive_tool_errors` field to `ArchytasContextConfig` dataclass + parser |
| `src/bdikit_context/context.py` | Wired `ARCHYTAS_MAX_CONSECUTIVE_TOOL_ERRORS` env var to agent attribute |
| `src/code_context/context.py` | Same as above |
| 38 YAML configs in `experiments/.../configs/automated/` | Added `max_consecutive_tool_errors: 3` |
| `docs/codebase_descriptions/how_this_codebase_works_05_03_2026.md` | New codebase description reflecting changes |

### Files Changed (Archytas commit: 1 file)

| File | Change |
|------|--------|
| `archytas/react.py` | Added `max_consecutive_tool_errors` attribute, tracking variables, counter logic in exception handler, `FailedTaskError` on threshold breach |

### Deployment Note

The Archytas changes require an **Apptainer image rebuild** to take effect. The archytas package is installed from `/hpc/compgen/projects/llm_GEO_project/archytas` into the container at build time. Until the image is rebuilt, the `.venv` copy (synced manually) can be used for local testing outside the container.
