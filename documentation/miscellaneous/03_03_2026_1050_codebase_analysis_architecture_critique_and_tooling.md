# Harmonia Codebase Analysis, Architecture Critique & Tooling Recommendations

**Date:** 03-03-2026
**Author:** Claude Sonnet 4.6 (comprehensive analysis)
**Scope:** Full codebase review, architecture critique, liteLLM/anyLLM migration state, dead code survey, missing functionality, and top-10 tooling recommendations.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Codebase Inventory & Functionality Map](#2-codebase-inventory--functionality-map)
3. [Recent Commit History Analysis (last 10 commits)](#3-recent-commit-history-analysis)
4. [liteLLM vs anyLLM: Migration State Audit](#4-litellm-vs-anyllm-migration-state-audit)
5. [Dead Code, Orphan Scripts & Stale Artifacts](#5-dead-code-orphan-scripts--stale-artifacts)
6. [Architecture Critique: Bloat, Complexity & Inconsistency](#6-architecture-critique-bloat-complexity--inconsistency)
7. [Missing Functionality & Gaps](#7-missing-functionality--gaps)
8. [Top-10 Tooling Recommendations for Code Quality](#8-top-10-tooling-recommendations-for-code-quality)
9. [Actionable Paths Forward](#9-actionable-paths-forward)
10. [Architecture Critique Addendum (from detailed analysis)](#10-architecture-critique-addendum-from-detailed-analysis)

---

## 1. Executive Summary

The Harmonia codebase is a well-intentioned but rapidly-evolved research automation system. The core experiment loop (`run_experiment.py` → `BeakerClient` → `ExperimentRunner`) is solid and well-tested in practice. The three-context architecture (bdikit_context, code_context, codeact_context) provides meaningful experimental variation. The evaluation and visualization pipeline is useful and growing.

However, several categories of technical debt have accumulated through fast agentic-coding cycles:

- **Provider string inconsistency**: `anyllm:` prefix survives in all manual configs and ~83 job script occurrences despite `any-llm` being fully replaced by `litellm`.
- **Orphan files**: at least 6 root-level diagnostic/test scripts and 3 job scripts that have no corresponding current configs.
- **Config explosion**: 30 automated YAML files with ~90% structural duplication; no parametric config matrix.
- **Dead module**: `src/bdikit_context/llm/litellm_direct.py` is never imported outside its own file.
- **Dead method**: `BeakerClient._set_context_ws()` (client.py lines 207–249) is superseded by `_set_context_magic()` and never called.
- **Misaligned module**: `src/bdikit_context/config/__init__.py` still carries `use_anyllm` flag and "any-llm" docstrings despite that package being retired.
- **Giant shell script**: `exec_apptainer_harmonia.sh` is 1192 lines — a monolith that embeds LLM provider logic, Ollama orchestration, VRAM estimation, path management, and container launching.
- **Experiments 2 and 3**: Complete placeholders — no configs, no job scripts, no automation.
- **No tests** beyond one unit test file for `kernel_state_budget.py` and several broken legacy test scripts.

---

## 2. Codebase Inventory & Functionality Map

### 2.1 Python Modules (`src/`)

```
src/
├── automation/              # Core experiment automation framework
│   ├── client.py            # BeakerClient (WebSocket/Jupyter protocol) — ~577 lines
│   ├── config.py            # ExperimentConfig dataclasses + YAML loader — ~271 lines
│   ├── runner.py            # ExperimentRunner (scripted turns + retries) — ~401 lines
│   ├── manual_runner.py     # ManualExperimentRunner (passive monitoring) — ~403 lines
│   └── logger.py            # TraceLogger + ConversationLogger
│
├── bdikit_context/          # BDI-Kit Beaker context (ReAct + domain tools)
│   ├── context.py           # BDIKitContext (prompt loading, tool overrides)
│   ├── agent.py             # BDIKitAgent (5 tools: match_schema, match_values,
│   │                        #   materialize_mapping, rank_schema_matches,
│   │                        #   get_gdc_acceptable_values) — 402 lines
│   ├── config/__init__.py   # LLMConfig, HarmoniaConfig — contains use_anyllm dead code
│   ├── llm/__init__.py      # PROVIDER_IMPORT_MAP + configure_llm_environment()
│   ├── llm/litellm_model.py # ChatLiteLLM + LiteLLMModel (used by all contexts)
│   ├── llm/litellm_direct.py# DirectLiteLLMRunner — ORPHANED (never imported)
│   ├── prompts/             # Jinja2 prompt template system (PromptLoader)
│   └── procedures/python3/  # Code templates for BDI-Kit functions (injected at runtime)
│
├── code_context/            # ReAct + run_code only context (minimal)
│   ├── context.py           # CodeContext
│   └── agent.py             # CodeAgent
│
├── codeact_context/         # True CodeAct (no Archytas, direct LLM loop)
│   ├── context.py           # CodeActContext
│   └── agent.py             # CodeActAgent + CodeActAgentLoop (~400 lines, clean)
│
├── context_management/      # Kernel state budget enforcement
│   ├── kernel_state_budget.py  # BudgetConfig + apply_budget() — canonical reference
│   └── test_kernel_state_budget.py  # Unit tests (the ONLY working test file)
│
├── evaluation/              # Metrics calculation + visualization
│   ├── metrics.py           # calculate_all_metrics(), calculate_column_*()
│   ├── schemas.py           # Pydantic MetricsResult schema (v1.1)
│   ├── visualize_metrics_cli.py  # CLI: summarize, bars, heatmap, confusion, errors, compare
│   └── visualization/       # Modular viz library (6 modules: io, enrich, normalize,
│                            #   aggregate, plots, report)
│
├── openrouter_hardening.py  # Monkey-patch for OpenRouter AIMessage null-thought bug
└── prompt_logging.py        # Prompt composition logging (stdout + JSON)
```

### 2.2 Root-Level Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `run_experiment.py` | Main CLI for automated experiments | **Active** |
| `run_manual_experiment.py` | CLI for manual experiment logging | **Active** |
| `calculate_metrics.py` | Standalone metrics CLI | **Active** |
| `generate_jobs.py` | SBATCH job script generator | **Active** |
| `generate_env.py` | .env file generator from YAML configs | **Active** |
| `check_archytas.py` | Inspect Archytas version/params | **Orphan diagnostic** |
| `diagnose_llm.py` | Debug LLM provider env vars | **Orphan diagnostic** |
| `diagnose_interactive_beaker_session.py` | Debug Beaker session | **Orphan diagnostic** |
| `quick_test.py` | Quick LLM config verification | **Orphan diagnostic** |
| `test_anyllm_adapter.py` | Tests for old any-llm adapter | **Broken/orphan** |
| `test_anyllm_basic.py` | Tests for old any-llm library | **Broken/orphan** |

### 2.3 Infrastructure

| File | Purpose | Size |
|------|---------|------|
| `exec_apptainer_harmonia.sh` | Container launcher + Ollama orchestration | 1192 lines |
| `sbatch_template.sh` | CPU job template | ~160 lines |
| `sbatch_template_gpu.sh` | GPU job template | ~165 lines |
| `build_harmonia_apptainer.sh` | Container build script | ~50 lines |
| `harmonia_beaker_LLM_agent_environment_apptainer.def` | Container definition | — |

### 2.4 Experiment Configs (Experiment 1 only)

```
experiments/experiment_1_harmonia_dou2020_gdc/configs/
├── automated/   30 YAML files × 3 contexts + legacy
└── manual/      13 YAML files (1 per model)
```

- **Experiment 2** (`two_metadata_tables_harmonize`): No configs, no automation.
- **Experiment 3** (`ten_metadata_tables_harmonize`): No configs, no automation.

### 2.5 What the System Does (Functional Summary)

The system runs **biomedical metadata harmonization agents** through the following pipeline:

1. **Configuration**: YAML config → `ExperimentConfig` dataclass (provider, model, messages, prompts, evaluation, retries)
2. **Launch**: `exec_apptainer_harmonia.sh` starts Beaker server inside Apptainer; for Ollama, starts an isolated Ollama instance on a per-job port.
3. **Automation**: `run_experiment.py` connects via WebSocket (`BeakerClient`), sends scripted messages, receives responses, handles decisions, retries on transient failures.
4. **Context types**:
   - `bdikit_context`: ReAct with 5 structured BDI-Kit tool calls
   - `code_context`: ReAct with a single `run_code` tool
   - `codeact_context`: Pure code generation loop (no tool schema)
5. **Logging**: `TraceLogger` + `ConversationLogger` → `trace.json`, `conversation.md`, `.experiment_id`
6. **Evaluation**: `calculate_all_metrics()` → `metrics.json` (column mapping + value accuracy + confusion matrices)
7. **Visualization**: `visualize_metrics_cli.py` → heatmaps, bar charts, confusion matrices (seaborn/plotly)
8. **Diagnostics**: `read_and_analyze_logs_and_traces_cli.py` → 16-class failure taxonomy

---

## 3. Recent Commit History Analysis

### Last 10 commits (newest first)

| Hash | Message | Assessment |
|------|---------|------------|
| `78bdf85` | Finalize analysis artifacts, rerun diagnostics, comparison plots | Analysis/data artifacts; mostly CSV/plot commits |
| `e1e018d` | Harden experiment reliability: retries, OpenRouter guards, retry policy | +2539 lines. Solid feature work but 30+ config files touched mechanically |
| `0f3be13` | Frontier runs, visualization CLI, diagnostics hardening | +8400 lines. Major feature batch — visualization CLI is the most significant addition |
| `c7f529d` | Fix VRAM estimation bug; RTX 6000 GPU request | Small focused fix |
| `92c6b41` | Remove orphaned pony-alpha job script; add step-3.5-flash | Housekeeping — good |
| `9bd3ee4` | Fix Ollama pre-load timeouts; remove broken codeact_devstral config | Good housekeeping |
| `3be8d45` | Reorder all automated configs: parameters first, messages last | Mechanical churn — 30 YAML files touched for style-only ordering |
| `1e32d1f` | Fix FETCH_STATE_CODE patch: scope regex to string body | Small fix |
| `407536a` | Add context management pipeline | Large feature addition |
| `5806404` | Fix context management: VRAM estimation, kernel budget | Bug fixes |

**Key observations from commit history:**

- Commits `e1e018d` and `0f3be13` together changed **145 files and +10,939 lines** in a single day. This is the hallmark of agentic coding: large batch changes that are hard to review and may hide subtle regressions.
- Commit `3be8d45` touched 30 YAML config files for a pure style change (ordering). This is unnecessary churn that bloats git history and makes it harder to track actual semantic changes.
- The `jobs/` directory has accumulated 31 SLURM scripts, many generated, some manually edited after generation (noted: they differ from what `generate_jobs.py` would produce today — they contain `anyllm` references in env var settings from when that was the convention).
- No commits add tests for new features. The only test file (`test_kernel_state_budget.py`) predates the visualization CLI, retry policy, OpenRouter hardening, and CodeAct context.

---

## 4. liteLLM vs anyLLM: Migration State Audit

### 4.1 Background

The original LLM abstraction used the `any-llm` Python package (`anyllm.py` module). Around commit `5806404`/`407536a`, this was replaced by `litellm`. The migration plan is documented in `documentation/plans/25_02_2026_1530_change_LLM_backend_to_liteLLM.md`.

### 4.2 Current State: What Is Complete

| Component | Status |
|-----------|--------|
| `pyproject.toml` dependencies | ✅ Only `litellm`; `any-llm` removed |
| `src/bdikit_context/llm/litellm_model.py` | ✅ Fully litellm-based, handles `anyllm:` prefix |
| `src/bdikit_context/llm/__init__.py` PROVIDER_IMPORT_MAP | ✅ All entries point to `LiteLLMModel` |
| `src/codeact_context/agent.py` | ✅ Uses `litellm.acompletion()` directly |
| New automated configs (frontier models) | ✅ Use `openrouter` / `ollama` directly |
| Container image | ✅ litellm installed in new `.sif` |

### 4.3 Current State: What Is Incomplete (anyllm ghost)

**4.3.1 Manual experiment configs — all use `anyllm:` prefix**

Every single manual config (13 files) still uses `anyllm:openrouter` or `anyllm:ollama`:
```
experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/
  dou_harmonization_manual_*.yaml → provider: anyllm:openrouter  (×7)
  dou_harmonization_manual_*.yaml → provider: anyllm:ollama       (×6)
```
The **template** (`dou_harmonization_manual_config.template`) also defaults to `anyllm:PROVIDER_HERE`.

**4.3.2 3–4 automated configs still use `anyllm:`**

```
dou_harmonization_anyllm_devstral.yaml         → provider: anyllm:ollama
dou_harmonization_bdikit-tools_gemini-3-flash-preview.yaml → anyllm:openrouter
dou_harmonization_code-context_gemini-3-flash-preview.yaml → anyllm:openrouter
dou_harmonization_codeact_gemini-3-flash-preview.yaml      → anyllm:openrouter
```

**4.3.3 Job scripts: 83 occurrences of `anyllm`**

All older Ollama job scripts (`dou_harmonization_devstral.sh`, etc.) set:
```bash
--env LLM_SERVICE_PROVIDER=anyllm:ollama
```
The newer frontier job scripts use `openrouter` directly. This inconsistency means the 16 Ollama-based job scripts use a different convention than the 18 frontier job scripts.

**4.3.4 `src/bdikit_context/config/__init__.py` — dead `use_anyllm` flag**

```python
# Line 43–53 in config/__init__.py
use_anyllm: bool = False  # Convenience flag to auto-prefix provider with "anyllm:"
...
if self.use_anyllm and not self.provider.lower().startswith("anyllm"):
    return f"anyllm:{self.provider}"
```
This flag is: (a) never set to `True` in any active config, (b) causes the code to emit the backwards-compat prefix that is then stripped again by `litellm_model.py`. It is circular dead code.

The docstring at the top of `config/__init__.py` still reads:
> "Supports: 1. Native Archytas providers... 2. any-llm unified providers: 'anyllm:openai'..."

**4.3.5 `src/bdikit_context/llm/litellm_direct.py` — completely orphaned**

`DirectLiteLLMRunner`, `quick_complete`, and `quick_complete_sync` are defined here but **never imported anywhere** in the production codebase. The only references are in:
- `test_anyllm_adapter.py` (itself broken, imports from non-existent `bdikit_context.llm.direct`)
- The file's own docstring examples

**4.3.6 `test_anyllm_adapter.py` and `test_anyllm_basic.py` — broken legacy tests**

Both files import from paths that no longer exist:
```python
from bdikit_context.llm.direct import DirectLLMRunner, quick_complete  # ❌ no such path
```
These tests would fail on import. They test the old `any-llm` adapter and should be either updated for litellm or deleted.

**4.3.7 `PROVIDER_IMPORT_MAP` redundancy**

The map has 14 `litellm:*` entries and 14 `anyllm:*` entries, all pointing to the same class. This is 14 redundant lines. A simpler design would be:
```python
if provider.startswith("litellm:") or provider.startswith("anyllm:"):
    return "bdikit_context.llm.litellm_model.LiteLLMModel"
```

### 4.4 Why This Matters

The `anyllm:` prefix is **functionally harmless** — it routes to litellm correctly. But it creates:
- Cognitive confusion: "Is there still an any-llm package? Should I use litellm or anyllm?"
- Config inconsistency: manual configs vs automated configs use different conventions
- Onboarding friction: new contributors or AI agents may not understand the layering

**Recommendation:** Complete the migration by migrating manual configs and older job scripts to use `openrouter`/`ollama` directly, delete `use_anyllm` from `config/__init__.py`, and retire `litellm_direct.py`.

---

## 5. Dead Code, Orphan Scripts & Stale Artifacts

### 5.1 Orphan Python Scripts at Repo Root

These scripts are **not imported** by any other module and have no associated tests:

| File | Original Purpose | Stale Indicator |
|------|-----------------|----------------|
| `check_archytas.py` | Inspect Archytas version | References old ReActAgent params; no invocation path |
| `diagnose_llm.py` | Debug LLM env vars | References legacy `jupyter.sif` paths |
| `diagnose_interactive_beaker_session.py` | Debug Beaker session | One-off diagnostic |
| `quick_test.py` | Quick env/config check | Hardcoded to old Beaker config path |
| `test_anyllm_adapter.py` | Test old any-llm adapter | Broken imports: `from bdikit_context.llm.direct import...` |
| `test_anyllm_basic.py` | Test any-llm library | Imports `any_llm` directly — package no longer installed |

**Action**: Move to a `scripts/legacy/` or `archive/` directory, or delete. They may occasionally be useful to run interactively, but they clutter the root and confuse automated tooling.

### 5.2 Orphan/Stale Job Scripts

| Script | Issue |
|--------|-------|
| `jobs/dou_harmonization.sh` | Uses hardcoded model `xiaomi/mimo-v2-flash:free`; not generated from any current config; appears to be a very early manual script |
| `jobs/dou_harmonization_anyllm_openrouter.sh` | Still uses `anyllm:openrouter`; corresponding config is `dou_harmonization_anyllm_devstral.yaml` which uses ollama, not openrouter |
| `jobs/dou_harmonization_kimi-k2.sh` | Uses model `kimi-k2` but the current config is `kimi-k2.5`; mismatched |

### 5.3 Dead Code in Source Files

**`client.py:207–249` — `_set_context_ws()` method (never called)**

```python
async def _set_context_ws(self, context_slug: str) -> None:
    """Set the Beaker context via WebSocket message."""
    # This approach is superseded by _set_context_magic()
```
This method is defined but never referenced. The working method is `_set_context_magic()` (lines 151–205). This represents a failed earlier approach that was left in place.

**`src/bdikit_context/llm/litellm_direct.py` — entire file orphaned**

~280 lines with `DirectLiteLLMRunner`, `quick_complete`, `quick_complete_sync`. Not imported anywhere in production. The codeact_context does LLM calls directly via `litellm.acompletion()` without needing this abstraction.

**`src/bdikit_context/config/__init__.py` — `use_anyllm` flag**

```python
use_anyllm: bool = False  # Lines 43, 52–53, 94–95, 105, 138–151
```
This flag and all associated conditional logic (8 lines) is dead. No config sets `use_anyllm: True`.

**`PROVIDER_IMPORT_MAP` in `llm/__init__.py` — 14 redundant `anyllm:*` entries**

All map to the same class. Could be replaced with prefix-based logic.

### 5.4 `context_management/` — Partially Decoupled Module

`src/context_management/kernel_state_budget.py` is the Python-side reference implementation of the budget logic that is **actually injected as a patch into Beaker's Python subkernel via the Apptainer `.def` file** at build time. This module:
- Is NOT imported by any of the three contexts at runtime (they read env vars; the logic runs inside the container)
- Has its own test file (`test_kernel_state_budget.py`) — the only working tests in the repo
- Is a "canonical reference" for documentation purposes

This is slightly confusing: a module in `src/` that does not participate in the Python import graph of the runtime system. It should be more clearly marked as a reference/test artifact, or moved to a `scripts/` or `tools/` directory.

### 5.5 `.runtime_contexts/` — Committed Configuration State

The directory `.runtime_contexts/` contains three JSON files:
```
bdikit_context.json
code_context.json
codeact_context.json
```
These appear to be context configuration snapshots committed to the repo. Whether these are stale or active depends on how Beaker uses them, but committing runtime state files is generally a smell — they can drift from the actual runtime config.

---

## 6. Architecture Critique: Bloat, Complexity & Inconsistency

### 6.1 The Config File Explosion

The most visible architectural problem: **30 nearly-identical YAML files** for automated experiments.

Typical file differences between two configs for the same context with different models:
- Lines 5–8: `provider`, `model`, `base_url` (3–4 lines unique)
- Lines 10–14: `bdikit_models` section (same pattern, different model names)
- Lines 17–22: `context_management` (identical in all)
- Lines 25–100: `messages` section (identical within a context type)
- Lines 102–112: `evaluation` (identical across all)
- Lines 114–120: `retry_policy` (identical across all)

**Estimated uniqueness**: ~10% of each YAML file is unique to that model; 90% is boilerplate duplication.

**A better design** would use a matrix/parametric config approach:
```yaml
# experiment_matrix.yaml
base_config: dou_harmonization_base.yaml
matrix:
  llm:
    - {provider: openrouter, model: mistralai/devstral-small-2505}
    - {provider: openrouter, model: google/gemini-flash-1.5}
    - {provider: ollama, model: devstral:latest}
  context:
    - bdikit_context
    - code_context
    - codeact_context
```
This would replace ~30 files with 1 base config + 1 matrix spec. The `run_experiment.py` and `generate_jobs.py` would need to expand the matrix, but this is a ~100-line addition.

The current approach also means **changes to the base prompt require touching 30 files**, which is exactly what happened in commit `3be8d45` (30 files touched for reordering) and commits `e1e018d`/`0f3be13` (30+ files touched for retry_policy addition). The `scripts/update_config_yamls.py` was written to automate this mass-update, which is a band-aid on the underlying problem.

### 6.2 `exec_apptainer_harmonia.sh` — The 1192-Line Monolith

This is the most structurally problematic file. It implements:
- Argument parsing (–port, –env, –config, –monitor, –image, –run-id, –job-name)
- Image auto-detection (priority logic)
- `.env` file generation (calling `generate_env.py`)
- Per-job Ollama port assignment (`11434 + 1 + (SLURM_JOB_ID % 200)`)
- Ollama server startup, model pre-loading, GPU verification
- VRAM estimation and reporting (`estimate_vram_usage()`)
- Runtime directory creation and env var overriding (JUPYTER_RUNTIME_DIR, XDG_RUNTIME_DIR, etc.)
- Context window budget calculation
- Apptainer invocation with bind mounts
- Monitor process launch (`run_manual_experiment.py`)
- Run ID generation and `.experiment_id` file creation

**Problems**:
1. **Untestable**: Shell scripts of this size have no unit testing equivalent. Logic errors (like the VRAM estimation bug in `c7f529d`) are only found in production.
2. **Duplicated concern**: `generate_env.py` and the shell script both handle env var generation from config. There's bidirectional coupling.
3. **Hard to maintain**: Adding a new provider or new runtime variable requires finding the right section in 1192 lines.
4. **Configuration coupling**: `exec_apptainer_harmonia.sh` reads and re-emits config values that are already in the `.env` — it doesn't fully trust its own generated env files.

**Recommendation**: Split into a Python launcher script (`launch_experiment.py`) that handles all the logic, with `exec_apptainer_harmonia.sh` reduced to a thin wrapper that calls the Python script and invokes `apptainer exec`. This makes the orchestration logic testable.

### 6.3 Three Parallel Context Implementations With Different Coverage

The three Beaker contexts have different levels of polish:

| Feature | bdikit_context | code_context | codeact_context |
|---------|---------------|--------------|-----------------|
| Prompt overrides via env vars | ✅ Full | ✅ Via `HARMONIA_CODE_CONTEXT_PROMPT` | ✅ Via `HARMONIA_CODEACT_PROMPT` |
| Context window management | ✅ Via Archytas | ✅ Via Archytas | ✅ Custom `CodeActAgentLoop` |
| OpenRouter hardening applied | ✅ `apply_openrouter_hardening()` called in `__init__` | ✅ | ✅ |
| Prompt composition logging | ✅ `register_prompt_json_logger()` | ✅ | ❌ CodeAct context bypasses Archytas; prompt logger may not fire |
| bdikit_models config | ✅ | ❌ Not applicable | ❌ Not applicable |
| `ArchytasContextConfig` respected | ✅ | ✅ | ❌ Uses own `CODEACT_MAX_TURNS` env var instead |
| Retry policy | ✅ Runner-level | ✅ | ✅ |

Key inconsistency: **`codeact_context` does not respect `context_management.archytas` config** — it has its own env var system (`CODEACT_MAX_TURNS`, `CODEACT_CONTEXT_STRATEGY`). This is architecturally correct (it doesn't use Archytas) but creates a two-tier configuration system where the same YAML has different effects depending on which context is selected.

Another inconsistency: the **prompt composition logger** (`register_prompt_json_logger()` in `prompt_logging.py`) monkey-patches `agent.execute()` — this is Archytas-specific. The `codeact_context` bypasses Archytas, so `full_prompt_composition.json` may not be written for codeact runs, making cross-context prompt comparison unreliable.

### 6.4 `LLMConfig` Duplication Across Modules

There are **two `LLMConfig` dataclasses** in the codebase:

1. `src/automation/config.py:LLMConfig` — used by `ExperimentConfig`, has: `provider, model, temperature, context_length`
2. `src/bdikit_context/config/__init__.py:LLMConfig` — used by `HarmoniaConfig`, has: `provider, model, api_key, base_url, temperature, max_tokens, extra, use_anyllm`

These serve different purposes but the naming collision is confusing. The `bdikit_context.config.LLMConfig` is effectively only used inside the Beaker container (loaded from env vars). The `automation.config.LLMConfig` is used by the experiment runner outside the container. They should either be merged or distinctly named (e.g., `ContainerLLMConfig` vs `ExperimentLLMConfig`).

### 6.5 The `bdikit_context/config/` Module Is Misplaced

`src/bdikit_context/config/__init__.py` contains `LLMConfig`, `HarmoniaConfig`, `get_config()`, `reset_config()` — a full configuration system that runs **inside the Beaker container**. It loads from env vars at runtime.

But `src/automation/config.py` is the configuration system for the **outside-container automation layer**. These two config systems are parallel and confusingly named, but they serve completely different roles (one is for the LLM agent inside the container; the other is for the experiment script outside).

This is a consequence of the original design where `bdikit_context` was a self-contained package. The naming makes it look like they should be merged, but functionally they should stay separate — they just need clearer naming and documentation.

### 6.6 `generate_jobs.py` vs Hand-Maintained Job Scripts

`generate_jobs.py` was designed to generate job scripts from config + template. But:
1. The actual job scripts in `jobs/` have been manually edited after generation (e.g., RTX 6000 GPU request in `c7f529d` was patched in both `sbatch_template_gpu.sh` and individual scripts).
2. The generated vs hand-maintained scripts are indistinguishable from each other — there's no header marking a script as "auto-generated; do not edit."
3. `generate_jobs.py` doesn't support the GPU template's Ollama-specific features (port assignment, model preload timeout).

**Result**: The job scripts in `jobs/` are the source of truth, not `generate_jobs.py`. The tool has become vestigial. Any new mass change (like the RTX 6000 fix) either requires touching all 31 scripts individually, or a one-off sed script.

### 6.7 The `_setup_kernel_working_directory` Hardcoding

In `runner.py:_setup_kernel_working_directory()` (lines 325–381), the code copies a hardcoded list of data files:
```python
data_files = ["dou.csv", "data.csv", "input.csv"]
```
This is experiment-1 specific. When experiments 2 and 3 are implemented, this method will need to be made configurable (likely adding `input_files` to `OutputConfig` or `EvaluationConfig`).

### 6.8 `visualize_metrics_cli.py` — Missing Subparser Arguments

The `cmd_bars` subcommand accesses `args.metric` and `args.hue` but these are only added to the `bars` subparser — the code structure is correct. However, the `compare` subcommand hardcodes `default_metrics` as a list rather than accepting them as CLI arguments. This limits flexibility when you want to run `compare` with a custom metric set.

### 6.9 Missing Error Handling in `ExperimentRunner`

In `runner.py`, if `_setup_kernel_working_directory()` fails, the experiment continues silently (wrapped in try/except with only a warning print). This can cause the experiment to run but save artifacts to the wrong location (the container's working directory rather than the results directory). This silent failure mode is hard to diagnose without reading the SLURM log carefully — which is exactly the type of issue `read_and_analyze_logs_and_traces_cli.py` is meant to catch.

---

## 7. Missing Functionality & Gaps

### 7.1 Experiments 2 and 3 (High Priority for Research)

- **Experiment 2** (two-table harmonization of Dou 2020 + Dou 2023): No configs, no evaluation config, no gold standard integration.
- **Experiment 3** (ten-table pan-cancer harmonization): No configs. The gold standard file exists at `raw/datasets_harmonia/ten_metadata_tables_harmonize/data/ground_truth/li_2023_harmonized_metadata_metadata_table.csv`.

Until these are implemented, the system can only benchmark Experiment 1.

### 7.2 Parametric/Matrix Config System

As described in §6.1, there is no way to define an experiment matrix. Every model × context combination requires a separate file. With 10 models × 3 contexts = 30 files, and growing.

### 7.3 Systematic Statistical Comparison

The `visualize_metrics_cli.py` can show heatmaps and bar charts, but:
- No confidence intervals or error bars for repeated runs
- No statistical significance testing (Wilcoxon, bootstrap CIs)
- No per-column variance analysis across runs of the same model

### 7.4 Mount Visibility Diagnostic ("mount-visibility-cli")

Explicitly flagged as **pending** in the `02_03_2026_1838_code_changes_today_and_pending_fixes.md`:
> "`mount-visibility-cli` todo remains pending (implement + run minimal validation against one pass and one fail run)"

This tool would validate that the bind mounts inside the Apptainer container are correctly resolving data paths — a common source of `4A: FileNotFoundError` failures.

### 7.5 No Automated Test Suite

The only working tests are in `src/context_management/test_kernel_state_budget.py`. There are no tests for:
- `automation/config.py` YAML loading
- `automation/runner.py` turn execution, retry logic, decision handling
- `evaluation/metrics.py` metric calculations
- `evaluation/visualization/normalize.py` data normalization
- `visualize_metrics_cli.py` CLI subcommands

The visualization CLI was specifically noted as needing smoke tests in the `0f3be13` commit message TODOs. This is a significant gap given the system's complexity.

### 7.6 No Job Submission Status Tracking

There is no automated way to track which experiments have been submitted, which are running, which succeeded or failed, and which need to be retried. The `documentation/processes/02_03_2026_priority_run_ledger.csv` and `analysis/errors_02_03_2026_run_matrix.csv` are manually maintained spreadsheets. A simple DB or structured ledger tool that integrates with SLURM `squeue`/`sacct` outputs would dramatically reduce the manual triage burden.

### 7.7 Prompt Composition Logging Missing for codeact_context

As noted in §6.3, the `full_prompt_composition.json` artifact may not be written for `codeact_context` runs because `prompt_logging.py` monkey-patches Archytas. This means cross-context prompt comparison is unreliable.

### 7.8 Interactive Trace Timeline Views

Mentioned in the `0f3be13` TODO list:
> "Add dedicated trace timeline parsing utilities and interactive trace views (turn timeline, code-only view, error-only view)"

These would significantly improve experiment debugging and analysis.

### 7.9 Confusion Matrix Handling for High-Cardinality Columns

Also in `0f3be13` TODOs:
> "Improve confusion-matrix handling for high-cardinality columns (top-k + OTHER + normalized modes)"

Currently the confusion command selects a single column for a single run; no aggregate confusion views exist.

### 7.10 Visualization CLI: No `--group-by` or Repeated-Run Aggregation

The visualization CLI has no way to aggregate metrics across repeated runs of the same model, and no `--group-by` or `--facet-by` options. With a growing result set, you may want to see "mean ± std across 3 runs of model X" rather than individual run lines.

---

## 8. Top-10 Tooling Recommendations for Code Quality

These tools address the specific risks of agentic-coding workflows: orphan code, duplication, configuration drift, and undetected regressions.

### #1 — [Vulture](https://github.com/jendrikseipp/vulture): Dead Python Code Detection

**What it does**: Static analysis that finds unused functions, classes, variables, and imports. Assigns confidence scores (60%–100%) to reduce false positives. Supports whitelist files for intentional unused code (e.g., API callbacks, Beaker entry points).

**Why you need it**: The codebase has confirmed dead code (`litellm_direct.py`, `_set_context_ws()`, `use_anyllm` flag) that was introduced by agentic coding and never cleaned up. Vulture would have caught these.

**How to use**:
```bash
.venv/bin/pip install vulture
.venv/bin/vulture src/ *.py --min-confidence 80
# Create whitelist for intentional unused code (Beaker entry points, etc.)
.venv/bin/vulture src/ --make-whitelist > vulture_whitelist.py
```

**Caveats**: Vulture struggles with dynamic patterns (monkey-patching in `openrouter_hardening.py`, entry points). Use the whitelist to suppress false positives.

---

### #2 — [Ruff](https://github.com/astral-sh/ruff): Fast Linter + Formatter

**What it does**: Replaces flake8, pylint, isort, autoflake in a single Rust-based tool. Detects unused imports, undefined names, style violations, and many code quality issues at >100x the speed of flake8.

**Why you need it**: No linter is currently configured. Agentic coding often introduces unused imports and style inconsistencies. The codebase has no `pyproject.toml` ruff configuration section.

**How to use**:
```bash
.venv/bin/pip install ruff
.venv/bin/ruff check src/ *.py --select F,E,W,I  # Pyflakes + pycodestyle + isort
.venv/bin/ruff check src/ --fix  # Auto-fix safe issues
```

**Add to `pyproject.toml`**:
```toml
[tool.ruff]
line-length = 100
[tool.ruff.lint]
select = ["F", "E", "W", "I", "UP"]
ignore = ["E501"]  # Long lines OK in some places
```

---

### #3 — [deadcode](https://github.com/albertas/deadcode): Stricter Dead Code Detection

**What it does**: Complements Vulture. Tracks scopes and namespaces more accurately, finds dead code that Vulture misses (e.g., code behind always-false conditions). TOML-based configuration and dry-run mode.

**Why you need it**: Vulture has known false positive issues with dynamic Python patterns. Running both gives broader coverage. `deadcode` is particularly good at finding unreachable code blocks.

**How to use**:
```bash
.venv/bin/pip install deadcode
.venv/bin/deadcode src/ --exclude src/context_management/test_*
```

---

### #4 — [pytest](https://docs.pytest.org/) + [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio): Test Suite

**What it does**: Python's de-facto test framework. `pytest-asyncio` is essential for testing the async `BeakerClient` and `ExperimentRunner`.

**Why you need it**: There is effectively no automated test suite. The most critical regression risks are in `automation/runner.py` (retry logic, decision handling), `evaluation/metrics.py` (metric calculations), and `evaluation/visualization/normalize.py` (data normalization for plots).

**Immediate high-value tests to write**:
1. `test_config_loading.py`: Verify all 30 automated YAMLs parse without error
2. `test_metrics.py`: Property-based tests for column mapping and value metrics
3. `test_normalize.py`: Round-trip tests for `build_tables()` with sample metrics.json fixtures
4. `test_runner_retries.py`: Mock `BeakerClient.send_message()` to simulate transient errors; verify retry logic

**How to use**:
```bash
.venv/bin/pytest src/ tests/ -v --tb=short
```

---

### #5 — [CodeScene](https://codescene.com): Behavioral Code Analysis

**What it does**: Goes beyond static analysis — measures code churn, coupling hotspots, and complexity trends over time. Identifies "temporal coupling" (files that always change together) and "complexity trends" (files getting more complex over time).

**Why you need it**: The agentic-coding pattern in this repo (large batch commits touching many files) is exactly what CodeScene is designed to detect. It would show that `exec_apptainer_harmonia.sh`, `experiments/configs/automated/*.yaml`, and `jobs/*.sh` are abnormally high-churn files that warrant refactoring.

**Note**: CodeScene is a paid SaaS but has a free tier. For HPC environments without internet access to CI/CD, the open-source [code-maat](https://github.com/adamtornhill/code-maat) provides the same temporal coupling analysis locally.

---

### #6 — [mypy](https://mypy.readthedocs.io/): Static Type Checking

**What it does**: Type-checks Python code against type annotations. Catches type mismatches, missing Optional handling, and incorrect return types before runtime.

**Why you need it**: The codebase has type annotations but no type checker enforces them. The `normalize.py` visualization code and `metrics.py` are complex enough that type errors are plausible. For example, `Optional[Path]` returns from `_find_experiment_id_file()` are used without None checks in several places.

**How to use**:
```bash
.venv/bin/pip install mypy
.venv/bin/mypy src/ --ignore-missing-imports --no-strict-optional
```

---

### #7 — [Skylos](https://github.com/duriantaco/skylos): Hybrid AST + LLM Dead Code Detection

**What it does**: Combines AST analysis with an optional local/cloud LLM to distinguish truly dead code from dynamically-called code (framework magic, monkey-patching). More accurate than Vulture for dynamic Python patterns. Has an MCP server for SAST integration.

**Why you need it**: The Harmonia codebase uses dynamic patterns (Beaker entry points registered via `pyproject.toml`, monkey-patching in `openrouter_hardening.py`, dynamic imports via `PROVIDER_IMPORT_MAP`). These cause Vulture false positives. Skylos can distinguish them.

**How to use**:
```bash
pip install skylos
skylos src/ --output report.json
```

---

### #8 — [shellcheck](https://www.shellcheck.net/): Shell Script Static Analysis

**What it does**: Finds bugs and style issues in bash/sh scripts. Catches unquoted variables, missing error handling, deprecated syntax, and portability issues.

**Why you need it**: `exec_apptainer_harmonia.sh` (1192 lines), `sbatch_template.sh`, `sbatch_template_gpu.sh`, and 31 job scripts are entirely untested. `shellcheck` would find issues like unquoted variable expansions, missing `set -u`, and common subprocess management bugs.

**How to use**:
```bash
shellcheck exec_apptainer_harmonia.sh jobs/*.sh sbatch_template*.sh
# Or via pre-commit hook
```

**Expected findings**: The VRAM estimation bug (`c7f529d`) — reading `OLLAMA_CONTEXT_LENGTH` too late — is exactly the class of issue shellcheck can flag when combined with careful variable-scope analysis.

---

### #9 — [coverage.py](https://coverage.readthedocs.io/): Test Coverage Measurement

**What it does**: Measures which lines of code are executed during tests. Identifies untested code paths. Works with pytest via `pytest-cov`.

**Why you need it**: Right now you have ~0% test coverage on most modules. Running coverage on the existing `test_kernel_state_budget.py` would at least measure how much of `kernel_state_budget.py` is covered, and set a baseline to improve from.

**How to use**:
```bash
.venv/bin/pip install pytest-cov
.venv/bin/pytest src/context_management/ --cov=src/context_management --cov-report=term-missing
```

---

### #10 — [pre-commit](https://pre-commit.com/): Git Hook Automation

**What it does**: Runs a configurable set of checks (ruff, mypy, shellcheck, vulture, etc.) automatically before every git commit. Prevents dead code and style regressions from ever entering the repo.

**Why you need it**: The 3be8d45 commit (30 YAML files for style reordering) and the accumulation of orphan scripts are exactly what pre-commit hooks prevent. A `yaml-lint` hook would also have caught config formatting drift.

**Configuration (`.pre-commit-config.yaml`)**:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
  - repo: https://github.com/jendrikseipp/vulture
    rev: v2.11
    hooks:
      - id: vulture
        args: [src/, --min-confidence, "80"]
  - repo: https://github.com/shellcheck-py/shellcheck-py
    rev: v0.10.0.1
    hooks:
      - id: shellcheck
        files: \.(sh)$
  - repo: https://github.com/adrienverge/yamllint
    rev: v1.35.1
    hooks:
      - id: yamllint
        args: [-d, relaxed]
```

---

## 9. Actionable Paths Forward

Organized by priority and effort:

### 9.1 High Priority / Low Effort (clean up now)

**A. Complete the liteLLM migration:**
- Update all 13 manual configs: replace `anyllm:openrouter` → `openrouter`, `anyllm:ollama` → `ollama`
- Update the 3–4 remaining automated gemini configs
- Update the manual config template
- Delete `use_anyllm` flag and associated logic from `src/bdikit_context/config/__init__.py`
- Update config docstrings to remove `any-llm` references
- Use `scripts/update_config_yamls.py` or a sed one-liner for bulk migration

**B. Delete/archive orphan scripts:**
- Move to `scripts/legacy/`: `check_archytas.py`, `diagnose_llm.py`, `diagnose_interactive_beaker_session.py`, `quick_test.py`, `test_anyllm_adapter.py`, `test_anyllm_basic.py`
- Delete `jobs/dou_harmonization.sh` (stale hardcoded job), `jobs/dou_harmonization_anyllm_openrouter.sh` (mismatched config)

**C. Remove dead methods:**
- Delete `client.py:_set_context_ws()` (lines 207–249) — superseded by `_set_context_magic()`
- Delete `src/bdikit_context/llm/litellm_direct.py` — orphaned module
- Simplify `PROVIDER_IMPORT_MAP` to use prefix-matching logic instead of 14 redundant entries

### 9.2 Medium Priority / Medium Effort (next sprint)

**D. Install Ruff + pre-commit:**
- Add `[tool.ruff]` section to `pyproject.toml`
- Create `.pre-commit-config.yaml` with ruff, yamllint, shellcheck
- Run `ruff check src/ --fix` as a one-time cleanup pass

**E. Add smoke tests for new code:**
- `tests/test_config_loading.py`: Load all 30 automated YAMLs and verify no parse errors
- `tests/test_metrics_smoke.py`: Round-trip metrics calculation on a synthetic fixture
- `tests/test_visualization_smoke.py`: `build_tables()` on a sample metrics.json

**F. Fix the prompt composition logger for codeact_context:**
- The `register_prompt_json_logger()` monkey-patch fires on `agent.execute()` (Archytas). For `codeact_context`, add an equivalent hook in `CodeActAgentLoop.run()` to write `full_prompt_composition.json` with the system prompt used.

**G. Mark `.runtime_contexts/` as generated:**
- Add a `README` to `.runtime_contexts/` explaining what these files are and when they're updated
- Consider adding to `.gitignore` if they're fully runtime-generated

### 9.3 Medium Priority / High Effort (planned work)

**H. Implement parametric config matrix:**
- Add `ExperimentMatrix` class to `automation/config.py` that expands a matrix spec
- Update `generate_jobs.py` to consume matrices
- Migrate existing 30 configs into a base config + matrix file (reduce to ~3 YAML files)
- This is the single most impactful refactor for maintainability

**I. Refactor `exec_apptainer_harmonia.sh`:**
- Move Ollama orchestration, VRAM estimation, and run ID logic into `launch_experiment.py` (Python)
- Reduce shell script to: parse args → call Python launcher → invoke `apptainer exec`
- Add unit tests for the Python launcher logic

**J. Implement the mount-visibility-cli:**
- Pending fix noted in `02_03_2026_1838_code_changes_today_and_pending_fixes.md`
- Validate that bind mounts work correctly before experiment starts
- Integrate as a pre-flight check in `exec_apptainer_harmonia.sh`

### 9.4 Lower Priority / Future Work

**K. Experiments 2 and 3:**
- Create configs for two-table and ten-table harmonization
- Define gold standards for evaluation
- Requires significant prompt engineering work

**L. Statistical analysis layer:**
- Add confidence intervals to the visualization CLI
- Add repeated-run aggregation (`--group-by model --aggregate mean`)
- Add Wilcoxon significance testing for model comparisons

**M. Job tracking ledger:**
- Build a lightweight tool that reads SLURM `sacct` + `results/` dir to show job → run_id → result → metrics → status
- Replace the manually maintained CSV spreadsheets

**N. Interactive trace views:**
- Plotly-based timeline viewer for trace.json
- Code-only view filtering out non-code turns
- Error-only view for quick failure diagnosis

---

---

## 10. Architecture Critique Addendum (from detailed analysis)

*This section captures additional findings from a deeper architectural review completed after the initial analysis above was written.*

### 10.1 `codeact_context` Missing from `pyproject.toml` Entry Points — Probable Bug

The `pyproject.toml` entry-point section registers only two Beaker contexts:

```toml
[project.entry-points."beaker.contexts"]
bdikit_context = "bdikit_context.context:BDIKitContext"
code_context = "code_context.context:CodeContext"
```

`codeact_context` is **absent**. The experiment runner calls `_set_context_magic("codeact_context")` as a fallback (sending a `%set_context` magic command), which bypasses Beaker's standard autodiscovery. If Beaker cannot discover `codeact_context` via entry points, it may silently fall back to a default context or fail.

**Action (9.1-O):** Register `codeact_context` in `pyproject.toml`:
```toml
codeact_context = "codeact_context.context:CodeActContext"
```
Then rebuild the Apptainer image. Verify that `codeact_context` experiments actually run the `CodeActAgentLoop` and not a silently substituted context.

### 10.2 `ArchytasContextConfig` Fields Are Parsed and Dropped — Silent Dead Config

The `ArchytasContextConfig` dataclass (`automation/config.py`) fields (`max_react_steps`, `context_window_override`, `tool_output_summarization_threshold`, `tool_output_snippet_size`, `max_errors`) are:

1. Parsed from YAML by `ExperimentConfig.from_dict()`
2. Stored in `ExperimentConfig.context_management.archytas`
3. Written to the `.env` file by `generate_env.py` as `ARCHYTAS_*` env vars
4. **Never read by any Python code in the source tree.** Archytas reads its own config through its own mechanism.

The result: every `context_management.archytas` value in every YAML config is **silently inert** — the agent uses Archytas defaults regardless of what is specified.

This is particularly impactful for `max_react_steps` (default 30 in config, but actual Archytas default is different) and `max_errors`. If a researcher changes these values expecting different behavior, nothing changes.

**Action (9.2-P):** Either:
- Wire these settings by applying them to the Archytas agent object at construction time in `bdikit_context/context.py` and `code_context/context.py`; OR
- Add a `# NOTE: This config section is informational only` warning to the YAML template and update the codebase documentation to clearly state these fields have no effect

### 10.3 Duplicate Provider-Prefix Table in `codeact_context/context.py`

`codeact_context/context.py` (lines ~41–53) reimplements the litellm provider-prefix logic with its own hardcoded dict:

```python
provider_prefixes = {
    "openrouter": "openrouter/",
    "ollama": "ollama/",
    "openai": "",
    "anthropic": "",
    ...
}
```

This table is **incomplete relative to `litellm_model.py`'s `LITELLM_PROVIDER_PREFIX`** — it lacks `mistral`, `together`, `perplexity`, `bedrock`, `azure`, `cohere`, `deepseek`, `fireworks`, and others. If any of those providers is used with `codeact_context`, model strings will be incorrectly prefixed and the LLM call will fail with a provider routing error.

There are now **three separate provider-prefix tables** in the codebase:
- `src/bdikit_context/llm/litellm_model.py`: `LITELLM_PROVIDER_PREFIX` (canonical, complete)
- `src/codeact_context/context.py`: inline dict (incomplete)
- `src/bdikit_context/agent.py`: `_build_litellm_model()` helper (partial)

**Action (9.2-Q):** Extract `LITELLM_PROVIDER_PREFIX` from `litellm_model.py` into a shared module (e.g., `src/bdikit_context/llm/provider_prefixes.py`) and import it in both `codeact_context/context.py` and `bdikit_context/agent.py`. Delete the local reimplementations.

### 10.4 `_associated.env` Files Are Inert — Job Scripts Ignore Per-Config LLM Settings

For each automated YAML config there is a `*_associated.env` file (e.g., `dou_harmonization_bdikit-tools_claude-sonnet-4.6_associated.env`) containing per-experiment LLM credentials and settings. However, the job scripts in `jobs/` are generated to use `--env-file .env` (the global `.env` at the repo root), not the config-specific associated env file.

**Effect**: All experiments submitted via job scripts will use whatever LLM provider/API key is in the root `.env`, regardless of what is in their per-config `_associated.env`. If `.env` is set to one provider and the config is for a different provider, the experiment will silently run with the wrong LLM configuration.

The associated env files exist and are generated correctly by `generate_env.py`, but `generate_jobs.py` does not reference them — it always writes `--env-file .env`.

**Action (9.2-R):** Update `generate_jobs.py` to reference the config-specific associated env file in the generated job script's `--env-file` argument. Update the SLURM `TOKEN=...` extraction line to read from the correct env file. Regenerate all job scripts.

### 10.5 Two Generations of Configs in One Directory — Path Inconsistencies

The `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/` directory contains two generations of configs, identifiable by:

- **Generation 1 (older)**: `provider: ollama` or `provider: openrouter` (native Archytas path), `save_artifacts: ["dou_harmonized.csv"]` (bare filename)
- **Generation 2 (newer)**: `context:` field present, `provider: openrouter` via litellm, `save_artifacts: ["results/dou_harmonized.csv"]` (results-prefixed path)

The artifact path inconsistency (`"dou_harmonized.csv"` vs `"results/dou_harmonized.csv"`) means evaluation configs referencing these artifacts may look in the wrong place for some experiments.

Files affected: `dou_harmonization_devstral.yaml`, `dou_harmonization_nemotron-3-nano.yaml` (and possibly others using native Archytas providers).

**Action (9.1-S):** Audit all configs for `save_artifacts` path consistency. Either standardize on `results/dou_harmonized.csv` (newer convention) or update the evaluation code to check both paths.

### 10.6 Native Archytas Providers: Dead-Reachable Code with Silent Monkey-Patch Mismatch

The `PROVIDER_IMPORT_MAP` still lists 8 native Archytas providers (`openai`, `ollama`, `openrouter`, etc.). The two legacy configs that use `provider: ollama` or `provider: openrouter` (without `litellm:` or `anyllm:` prefix) route through these native Archytas models.

The monkey-patch in `openrouter_hardening.py` targets `OpenRouterModel` (the native Archytas provider). All three contexts call `apply_openrouter_hardening()` at startup. For `litellm:openrouter` configs, this monkey-patch is applied but has **no effect** (the litellm path never calls `OpenRouterModel`). This is misleading: a developer reading `context.py` sees the hardening applied and might assume it protects all OpenRouter calls, when in fact it only protects the legacy native-Archytas path.

**Action (9.1-T):** Add a comment to `apply_openrouter_hardening()` clarifying that it only applies to native Archytas `OpenRouterModel` (the `provider: openrouter` path), not to `litellm:openrouter`. When/if the legacy native-Archytas configs are retired, this whole module can be deleted.

### 10.7 `diagnose_interactive_beaker_session.py` — Misplaced but Not Dead

Unlike the other orphan diagnostic scripts, `diagnose_interactive_beaker_session.py` is **legitimately useful** operational tooling — it checks entry points, tool registration, Ollama connectivity, and model loading. These are things that still fail in practice.

However, it belongs in `code_development_tools_agents/` alongside the log analysis CLI, not at the repo root alongside production scripts. Its presence at root makes `ls` output confusing and it will be included in any `vulture src/ *.py` scan as orphan code.

**Action (9.1-U):** Move to `code_development_tools_agents/monitoring_and_evaluation/diagnose_interactive_beaker_session.py`. Update any references or documentation.

---

## References for Tooling

- [Vulture — Find dead Python code](https://github.com/jendrikseipp/vulture)
- [Ruff — Fast Python linter](https://github.com/astral-sh/ruff)
- [deadcode — Find unused Python code](https://github.com/albertas/deadcode)
- [Skylos — Hybrid SAST + LLM dead code](https://github.com/duriantaco/skylos)
- [CodeScene — Behavioral code analysis](https://codescene.com)
- [code-maat — Temporal coupling analysis (open source)](https://github.com/adamtornhill/code-maat)
- [shellcheck — Shell script analysis](https://www.shellcheck.net/)
- [pre-commit — Git hook automation](https://pre-commit.com/)
- [mypy — Python type checking](https://mypy.readthedocs.io/)
- [coverage.py — Test coverage](https://coverage.readthedocs.io/)
- [Agentic AI Coding: Best Practice Patterns — CodeScene Blog](https://codescene.com/blog/agentic-ai-coding-best-practice-patterns-for-speed-with-quality)
- [How AI-Generated Code Accelerates Technical Debt — LeadDev](https://leaddev.com/software-quality/how-ai-generated-code-accelerates-technical-debt)
