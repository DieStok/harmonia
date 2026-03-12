# Harmonia Codebase Fixes — Parallel Implementation Plan
**Date:** 03-03-2026 12:53
**Scope:** 27 issues identified in analysis document `docs/miscellaneous/03_03_2026_1050_codebase_analysis_architecture_critique_and_tooling.md`

---

## ORCHESTRATOR INSTRUCTIONS (read this first)

You are the main Claude orchestrator. Your job is to launch 7 subagents in parallel, each tackling one self-contained work package, then monitor their progress and report to the user.

### Step 1 — Preparation

Before launching subagents, read these files for shared context:
- `docs/miscellaneous/03_03_2026_1050_codebase_analysis_architecture_critique_and_tooling.md` (full analysis)
- `src/automation/config.py` (ExperimentConfig, ArchytasContextConfig)
- `pyproject.toml`

### Step 2 — Launch all 7 subagents simultaneously

Send **one message** with 7 Agent tool calls (subagent_type: `general-purpose`), using the detailed instructions for each work package in Sections WP-A through WP-G below.

**Key instructions to embed in every subagent prompt:**

> You are implementing a specific work package of a codebase improvement plan.
> Working directory: `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia`
> Python environment: `.venv/bin/python` (never use conda or system python)
> On completion, make a single atomic git commit covering all your changes. Include a full commit message describing what was done and why.
> Write your progress (what you did, decisions made, any issues encountered) to: `docs/parallel_codebase_upgrade_outputs/03_03_2026_1253_<WORKPACKAGE_NAME>_implementation_progress.md`

### Step 3 — Monitor

After launching, periodically read each subagent's `implementation_progress.md` file to track progress. Report to the user when each package completes or if any is blocked.

### Step 4 — Post-merge validation

After all packages complete:
1. Run `cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia && .venv/bin/pytest tests/test_config_loading.py -v` — all configs must load
2. Run `grep -rn "litellm_direct\|_set_context_ws\|use_anyllm\|anyllm:" src/` — must return 0 results in production files
3. Run `python manage_configs.py list --dir experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/` — must list all configs
4. Run `python generate_jobs.py --config experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_claude-sonnet-4.6.yaml --time 02:00:00 --memory 20G` — must produce script referencing associated.env

### Launch order note

WP-C (provider prefix + generate_jobs) has a soft dependency on WP-A (anyllm cleanup in configs). Launch both simultaneously, but WP-C should check the config files' anyllm: status before regenerating job scripts. If WP-A is not yet done, WP-C can skip the job script regeneration step and note it in its progress file.

All other packages are fully independent.

---

## Work Package A — Dead Code Deletion & anyllm Migration

**Subagent name:** `WP-A_dead_code_and_anyllm_cleanup`
**Progress file:** `docs/parallel_codebase_upgrade_outputs/03_03_2026_1253_WP-A_dead_code_and_anyllm_cleanup_implementation_progress.md`

### Context files to read first
- `src/automation/client.py` (find `_set_context_ws` at lines 207–249)
- `src/bdikit_context/config/__init__.py` (find `use_anyllm` flag)
- `src/bdikit_context/llm/__init__.py` (find `anyllm:*` entries in `PROVIDER_IMPORT_MAP`)
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/` (all 13 YAMLs)
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_gemini-3-flash-preview.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_gemini-3-flash-preview.yaml`
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_gemini-3-flash-preview.yaml`

### Changes to make

**A1 — Delete orphan Python files**

Delete these files entirely (git rm):
- `src/bdikit_context/llm/litellm_direct.py` — never imported anywhere
- `check_archytas.py` — stale one-off introspection script
- `diagnose_llm.py` — bug it diagnosed was fixed; now stale
- `quick_test.py` — 28-line duplicate of diagnose_llm.py
- `test_anyllm_adapter.py` — broken imports to non-existent `bdikit_context.llm.direct`
- `test_anyllm_basic.py` — imports `any_llm` package which is no longer installed

Verify no imports exist first: `grep -rn "litellm_direct\|from check_archytas\|from diagnose_llm\|from quick_test" src/`

**A2 — Move `diagnose_interactive_beaker_session.py`**

```bash
git mv diagnose_interactive_beaker_session.py code_development_tools_agents/monitoring_and_evaluation/diagnose_interactive_beaker_session.py
```

**A3 — Delete dead `_set_context_ws()` from `src/automation/client.py`**

Delete lines 207–249 (the entire `_set_context_ws` method including its docstring).

Add this one-line comment immediately above `_set_context_magic()` (the method that superseded it):
```python
# Supersedes a WebSocket-based set_context approach that Beaker does not support via Jupyter protocol.
```

**A4 — Remove `use_anyllm` dead flag from `src/bdikit_context/config/__init__.py`**

Make the following changes:
1. Update the `LLMConfig` docstring: remove the "any-llm" section, replace with:
   ```
   Supports litellm unified providers: "openrouter", "ollama", "litellm:openrouter", etc.
   ```
2. Remove field `use_anyllm: bool = False` from the `LLMConfig` dataclass
3. Remove the entire `get_effective_provider()` method (it only served `use_anyllm`)
4. In `from_env()`: remove `use_anyllm = os.getenv("USE_ANYLLM", "").lower() in ("true", "1", "yes")` and `use_anyllm=use_anyllm,` from the `LLMConfig(...)` constructor
5. In `from_yaml()`: remove `use_anyllm` from `LLMConfig(...)` constructor and remove all `use_anyllm` variable assignments (lines 139–140, 151)
6. Update any inline comments referring to "any-llm"

**A5 — Simplify `PROVIDER_IMPORT_MAP` in `src/bdikit_context/llm/__init__.py`**

Remove the 14 `anyllm:*` entries (lines 51–64 approximately — the block starting with `"anyllm": ...` through `"anyllm:fireworks": ...`).

Update the module docstring at the top to remove "3. any-llm prefix (backwards compatible)" section.

In `configure_llm_environment()` (the function): the existing code already handles `anyllm:` prefix via `provider_key.startswith("anyllm:")` on line 99 — keep that logic so any stray config using `anyllm:` still works at runtime, but the explicit per-provider map entries are gone. Verify the function still returns a valid `import_path` for `anyllm:` prefixed providers by tracing through: `provider_key.startswith("anyllm:")` → `actual_provider = provider_key.split(":", 1)[1]` → `import_path = PROVIDER_IMPORT_MAP.get(provider_key) or PROVIDER_IMPORT_MAP.get("litellm")`. Since per-provider entries are gone but `"litellm"` entry remains, this falls back correctly via `.get("litellm")`.

**A6 — Migrate `anyllm:` prefix in YAML configs**

For all 13 manual configs in `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/`:
```bash
sed -i 's/provider: anyllm:openrouter/provider: openrouter/g' experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/*.yaml
sed -i 's/provider: anyllm:ollama/provider: ollama/g' experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/*.yaml
```

For the manual config template:
```bash
sed -i 's/provider: anyllm:PROVIDER_HERE/provider: PROVIDER_HERE/g' experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_config.template
```

For the 4 automated stragglers:
```bash
sed -i 's/provider: anyllm:openrouter/provider: openrouter/g' experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_gemini-3-flash-preview.yaml experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_gemini-3-flash-preview.yaml experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_gemini-3-flash-preview.yaml
sed -i 's/provider: anyllm:ollama/provider: ollama/g' experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml
```

**A7 — Migrate `anyllm:` prefix in job scripts**

```bash
sed -i 's/LLM_SERVICE_PROVIDER=anyllm:ollama/LLM_SERVICE_PROVIDER=ollama/g' jobs/*.sh
sed -i 's/LLM_SERVICE_PROVIDER=anyllm:openrouter/LLM_SERVICE_PROVIDER=openrouter/g' jobs/*.sh
sed -i 's/anyllm:ollama/ollama/g' jobs/*.sh
sed -i 's/anyllm:openrouter/openrouter/g' jobs/*.sh
```

**A8 — Delete stale job scripts**

```bash
git rm jobs/dou_harmonization.sh  # Hardcoded mimo-v2-flash:free, no current config
git rm jobs/dou_harmonization_anyllm_openrouter.sh  # Mismatched: config uses ollama, script uses openrouter
```

For `jobs/dou_harmonization_kimi-k2.sh`: check if it references `kimi-k2` model but config is now `kimi-k2.5`. If yes, update the model reference inside the script (or regenerate via `generate_jobs.py` once WP-C updates it).

**A9 — Add clarifying comment to openrouter_hardening.py calls**

In `src/bdikit_context/context.py`, `src/code_context/context.py`, `src/codeact_context/context.py` — wherever `apply_openrouter_hardening()` is called, add the comment immediately before it:
```python
# NOTE: This patch only applies to native Archytas OpenRouterModel (provider: openrouter
# without litellm: prefix). Has no effect on the litellm:openrouter code path.
apply_openrouter_hardening()
```

**A10 — Add header comment to `context_management/kernel_state_budget.py`**

At the top of `src/context_management/kernel_state_budget.py`, add after the existing docstring:
```python
# REFERENCE ONLY: This module is NOT imported at runtime by any Beaker context.
# The budget enforcement logic is injected into the Beaker Python subkernel via
# the FETCH_STATE_CODE patch in harmonia_beaker_LLM_agent_environment_apptainer.def.
# This file exists as a canonical reference and test target only.
```

### Commit message to use
```
Clean up dead code and complete liteLLM migration

- Delete orphaned files: litellm_direct.py, check_archytas.py, diagnose_llm.py,
  quick_test.py, test_anyllm_adapter.py, test_anyllm_basic.py
- Move diagnose_interactive_beaker_session.py to code_development_tools_agents/
- Remove dead _set_context_ws() method from client.py (superseded by _set_context_magic)
- Remove use_anyllm flag and get_effective_provider() from bdikit_context/config/__init__.py
- Remove 14 redundant anyllm:* entries from PROVIDER_IMPORT_MAP
- Migrate all manual configs (13) and automated stragglers (4) from anyllm: to direct providers
- Migrate job scripts from anyllm: to direct providers
- Delete stale job scripts (dou_harmonization.sh, dou_harmonization_anyllm_openrouter.sh)
- Add clarifying comment on openrouter_hardening.py scope
- Add REFERENCE ONLY note to kernel_state_budget.py
```

---

## Work Package B — Wire ArchytasContextConfig + `codeact_context` Entry Point

**Subagent name:** `WP-B_wire_archytas_config_and_entrypoint`
**Progress file:** `docs/parallel_codebase_upgrade_outputs/03_03_2026_1253_WP-B_wire_archytas_config_and_entrypoint_implementation_progress.md`

### Context files to read first
- `.venv/lib/python3.11/site-packages/archytas/react.py` (lines 174–236: ReActAgent constructor, note `max_errors`, `max_react_steps`)
- `.venv/lib/python3.11/site-packages/beaker_kernel/lib/agent.py` (BeakerAgent constructor — passes **kwargs to ReActAgent)
- `.venv/lib/python3.11/site-packages/beaker_kernel/lib/context.py` (how `agent_cls(context=self, tools=...)` is called — no kwargs forwarded)
- `src/bdikit_context/context.py`
- `src/code_context/context.py`
- `src/automation/config.py` (ArchytasContextConfig dataclass, lines 95–106)
- `generate_env.py` (check if it writes ARCHYTAS_MAX_REACT_STEPS and ARCHYTAS_MAX_ERRORS)
- `pyproject.toml` (entry-points section)

### Key findings (already researched — use this)

**Archytas API:** `ReActAgent.__init__` accepts `max_errors: int` and `max_react_steps: int` as keyword arguments. `BeakerAgent` accepts `**kwargs` and forwards to `ReActAgent`. However, `BeakerContext.__init__` (beaker's base class) instantiates the agent as `agent_cls(context=self, tools=self.subkernel.tools)` — no kwargs passed.

**Solution:** After `super().__init__()` sets `self.agent`, read values from env vars (which `generate_env.py` already writes) and patch the agent's instance attributes directly. `ReActAgent` stores `max_errors` and `max_react_steps` as plain instance attributes (lines 234–235 in react.py) which are checked during the react loop — patching them post-construction works correctly.

### Changes to make

**B1 — Register `codeact_context` in `pyproject.toml`**

In the `[project.entry-points."beaker.contexts"]` section, add:
```toml
codeact_context = "codeact_context.context:CodeActContext"
```

Also add a comment noting the image must be rebuilt for this to take effect:
```toml
# NOTE: Changing entry points requires rebuilding the Apptainer image (build_harmonia_apptainer.sh)
```

**B2 — Wire `max_react_steps` and `max_errors` in `src/bdikit_context/context.py`**

After the `super().__init__(beaker_kernel, BDIKitAgent, config)` call, add:

```python
# Wire ArchytasContextConfig → Archytas agent (max_react_steps, max_errors)
# BeakerContext creates the agent internally without forwarding kwargs, so we patch
# the instance attributes directly after construction. These are plain int attributes
# on ReActAgent (react.py lines 234-235) checked per-task in the react loop.
_max_react_steps = os.environ.get("ARCHYTAS_MAX_REACT_STEPS")
_max_errors = os.environ.get("ARCHYTAS_MAX_ERRORS")
if _max_react_steps:
    self.agent.max_react_steps = int(_max_react_steps)
    print(f"  [HarmoniaConfig] max_react_steps = {self.agent.max_react_steps}")
if _max_errors:
    self.agent.max_errors = int(_max_errors)
    print(f"  [HarmoniaConfig] max_errors = {self.agent.max_errors}")
# NOTE: context_window_override, tool_output_summarization_threshold,
# tool_output_snippet_size, summarization_model are not exposed in the
# installed Archytas ReActAgent API and remain informational in the YAML config.
```

Also check: does `generate_env.py` write `ARCHYTAS_MAX_REACT_STEPS` and `ARCHYTAS_MAX_ERRORS`?
- Read `generate_env.py` and verify. If missing, add them.
- The env var names to look for/add: `ARCHYTAS_MAX_REACT_STEPS` and `ARCHYTAS_MAX_ERRORS`

**B3 — Wire `max_react_steps` and `max_errors` in `src/code_context/context.py`**

Same pattern as B2. After `super().__init__(beaker_kernel, CodeAgent, config)`, add the identical wiring block.

**B4 — Update `src/automation/config.py` — add wired/informational comments**

In the `ArchytasContextConfig` dataclass, add inline comments on each field:
```python
@dataclass
class ArchytasContextConfig:
    """Configuration for Archytas agent/model context management."""
    summarization_threshold_pct: int = 50          # informational — not currently wired
    context_window_override: Optional[int] = None  # informational — not in Archytas API
    max_tokens: Optional[int] = None               # informational — not in Archytas API
    tool_output_summarization_threshold: int = 1000  # informational — not in Archytas API
    tool_output_snippet_size: int = 1000           # informational — not in Archytas API
    max_react_steps: Optional[int] = 30            # WIRED — sets agent.max_react_steps via ARCHYTAS_MAX_REACT_STEPS env var
    max_errors: int = 3                            # WIRED — sets agent.max_errors via ARCHYTAS_MAX_ERRORS env var
    summarization_model: Optional[str] = None      # informational — not in Archytas API
    summarization_model_provider: Optional[str] = None  # informational — not in Archytas API
```

### Commit message to use
```
Wire ArchytasContextConfig to agent and register codeact_context entry point

- Register codeact_context in pyproject.toml entry points (was missing, caused
  reliance on %set_context magic fallback instead of proper autodiscovery)
- Wire max_react_steps and max_errors from YAML config → Archytas agent instance
  in bdikit_context/context.py and code_context/context.py
- Verify generate_env.py writes ARCHYTAS_MAX_REACT_STEPS and ARCHYTAS_MAX_ERRORS
- Add wired/informational comments to ArchytasContextConfig fields in config.py
- Note: Apptainer image must be rebuilt for entry point change to take effect
```

---

## Work Package C — Provider Prefix Consolidation & `generate_jobs.py` Overhaul

**Subagent name:** `WP-C_provider_prefix_and_generate_jobs`
**Progress file:** `docs/parallel_codebase_upgrade_outputs/03_03_2026_1253_WP-C_provider_prefix_and_generate_jobs_implementation_progress.md`

### Context files to read first
- `src/bdikit_context/llm/litellm_model.py` (lines 55–74: `LITELLM_PROVIDER_PREFIX` dict)
- `src/bdikit_context/agent.py` (lines 26–71: `_build_litellm_model()` with local `provider_prefixes` dict)
- `src/codeact_context/context.py` (lines 41–52: local `provider_prefixes` dict)
- `generate_jobs.py` (full file — 270 lines)
- `sbatch_template.sh` (full file)
- `sbatch_template_gpu.sh` (full file)
- One of the `_associated.env` files: `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_claude-sonnet-4.6_associated.env`

### Changes to make

**C1 — Create shared `src/bdikit_context/llm/provider_prefixes.py`**

Create this new file with the following content — copy the dict from `litellm_model.py` exactly:

```python
"""
Shared litellm provider prefix mapping for all Harmonia contexts.

Maps Harmonia provider names to litellm model string prefixes.
See: https://docs.litellm.ai/docs/providers

Import this from any context or agent module that needs to build litellm model strings.
"""

LITELLM_PROVIDER_PREFIX = {
    "ollama": "ollama_chat",    # ollama_chat/ for chat completions
    "openai": None,             # No prefix needed for OpenAI
    "openrouter": "openrouter",
    "anthropic": "anthropic",
    "azure": "azure",
    "azureopenai": "azure",
    "bedrock": "bedrock",
    "gemini": "gemini",
    "groq": "groq",
    "mistral": "mistral",
    "together": "together_ai",
    "perplexity": "perplexity",
    "cohere": "cohere_chat",
    "deepseek": "deepseek",
    "fireworks": "fireworks_ai",
}
```

**C2 — Update `src/bdikit_context/llm/litellm_model.py`**

Replace the `LITELLM_PROVIDER_PREFIX` dict literal with an import:
```python
from .provider_prefixes import LITELLM_PROVIDER_PREFIX
```
(The rest of the file is unchanged.)

**C3 — Update `src/bdikit_context/agent.py`**

In `_build_litellm_model()` (lines 26–71):
1. Add import at top of file: `from bdikit_context.llm.provider_prefixes import LITELLM_PROVIDER_PREFIX`
2. Replace the `provider_prefixes = { ... }` local dict (lines 54–69) with a lookup against `LITELLM_PROVIDER_PREFIX`
3. Note the format difference: `agent.py` uses `"openrouter/"` (with slash) while `LITELLM_PROVIDER_PREFIX` uses `"openrouter"` (without slash). The slash is added at the call site in `litellm_model.py` as `f"{prefix}/{model}"`. Reconcile this:
   - In `_build_litellm_model()`, use: `prefix = LITELLM_PROVIDER_PREFIX.get(base_provider, base_provider)` then `return f"{prefix}/{model}" if prefix else model`
   - This matches how `litellm_model.py` does it

**C4 — Update `src/codeact_context/context.py`**

Replace the local `provider_prefixes` dict (lines 41–48) with:
```python
from bdikit_context.llm.provider_prefixes import LITELLM_PROVIDER_PREFIX
```
Then update the model-string construction to use `LITELLM_PROVIDER_PREFIX.get(base_provider, base_provider)` with the same format pattern.

Note the codeact code currently builds `f"{prefix}{model}"` (no slash between prefix and model). The canonical format in `litellm_model.py` is `f"{prefix}/{model}"` — reconcile to use a slash. Also note: for `openai` (prefix=None), codeact should return just `model` (no prefix at all).

After this change, codeact correctly handles deepseek, mistral, cohere, together, perplexity, fireworks, and azure providers that the old local dict was missing.

**C5 — Overhaul `generate_jobs.py`**

Make the following changes to `generate_jobs.py`:

1. **Update defaults** to match current hand-maintained scripts:
   ```python
   DEFAULTS = {
       "time_limit": "02:00:00",   # was "01:00:00"
       "memory": "20G",            # was "8G"
       "cpus": "2",
       "timeout": "600",           # was "300" — experiments take longer
       "tmpspace": "50",           # was "1" — need space for model weights
   }
   ```

2. **Add `--use-associated-env` logic** (default: auto-detect):
   In `generate_job_script()`, before building replacements dict, detect the associated env file:
   ```python
   # Use config-specific associated env file if it exists (preferred over global .env)
   associated_env = config_path.parent / f"{config_path.stem}_associated.env"
   if associated_env.exists():
       effective_env_file = associated_env
       print(f"  Using associated env: {associated_env.name}")
   else:
       effective_env_file = env_file
   ```
   Then use `effective_env_file` in the `{{env_file}}` replacement.

3. **Add `--auto-gpu` / `--no-gpu` flags**:
   ```python
   parser.add_argument("--auto-gpu", action="store_true", default=True,
       help="Automatically use GPU template for ollama providers (default: True)")
   parser.add_argument("--no-gpu", dest="auto_gpu", action="store_false",
       help="Disable auto-GPU selection (always use CPU template)")
   ```
   In `main()`, select GPU template if `args.auto_gpu` and `config.llm.provider` in `("ollama", "anyllm:ollama", "litellm:ollama")`.

4. **Add generation header** to generated scripts. In `generate_job_script()`, after building `script`, prepend:
   ```python
   from datetime import datetime
   header = (
       f"# AUTO-GENERATED by generate_jobs.py — do not edit manually.\n"
       f"# To regenerate: python generate_jobs.py --config {config_path}\n"
       f"# Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
       f"#\n"
   )
   script = header + script
   ```

5. **Remove the `--env-file` CLI argument default** from `.env` — change its `help` to say the tool will auto-detect associated env files. Keep the flag for backwards compatibility but note its lower priority.

6. **Update the `generate_job_script` function signature** to receive `auto_gpu=True` and handle template selection internally.

**C6 — Update `sbatch_template.sh` and `sbatch_template_gpu.sh`**

In both templates:
- Update the top comment: replace "any-llm support" with "litellm support"
- The `{{env_file}}` template variable is already correct — no other changes needed

### Commit message to use
```
Consolidate provider prefix tables and overhaul generate_jobs.py

- Extract LITELLM_PROVIDER_PREFIX into shared src/bdikit_context/llm/provider_prefixes.py
- Import shared prefix table in litellm_model.py and agent.py (remove local copies)
- Update codeact_context/context.py to use shared prefix table (fixes missing providers:
  deepseek, mistral, cohere, together, perplexity, fireworks, azure, bedrock)
- generate_jobs.py: update defaults (time 02:00:00, mem 20G, tmpspace 50G, timeout 600)
- generate_jobs.py: auto-detect and use _associated.env files over global .env
- generate_jobs.py: auto-select GPU template for ollama providers (--no-gpu to disable)
- generate_jobs.py: add AUTO-GENERATED header to output scripts
- Update sbatch template comments (any-llm → litellm)
```

---

## Work Package D — `manage_configs.py` CLI Tool

**Subagent name:** `WP-D_manage_configs_cli`
**Progress file:** `docs/parallel_codebase_upgrade_outputs/03_03_2026_1253_WP-D_manage_configs_cli_implementation_progress.md`

### Context files to read first
- `src/automation/config.py` (ExperimentConfig, LLMConfig, OutputConfig — understand the YAML schema)
- One example config: `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_claude-sonnet-4.6.yaml`
- One manual config: `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_claude-sonnet-4.6.yaml`
- `generate_env.py` (to understand how associated.env is generated — `regenerate` subcommand calls this logic)

### Create `manage_configs.py` in the repo root

This is a new standalone CLI script (~350 lines). Use only stdlib + pyyaml (already in .venv). Do NOT use ruamel.yaml.

**Interface:**

```
manage_configs.py list [--dir DIR] [--format table|json]
manage_configs.py get --field DOTTED.PATH [--config FILE | --dir DIR] [--filter SUBSTR]
manage_configs.py set --field DOTTED.PATH --value VALUE [--config FILE | --dir DIR] [--filter SUBSTR] [--dry-run]
manage_configs.py clone --base BASE_CONFIG --output-dir DIR [--model MODEL] [--provider PROVIDER] [--context CONTEXT] [--name NAME]
manage_configs.py regenerate --config FILE  (re-runs generate_env.py for that config)
manage_configs.py validate [--dir DIR]
```

**Implementation details:**

`list` subcommand:
- Glob `*.yaml` in dir (default: `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/`)
- For each: load YAML with `yaml.safe_load`, extract: name, context, provider, model, context_window_override
- Table format: print aligned columns. JSON format: print JSON array.

`get` subcommand:
- `--field` uses dotted path: `llm.model`, `context_management.archytas.max_react_steps`, etc.
- Navigate the YAML dict with path segments
- Print `filename: value` for each matching file

`set` subcommand:
- Navigate to field using dotted path, update value
- `--filter` does `SUBSTR in config_filename` to limit which files are updated
- `--dry-run`: print what would change without writing
- After writing: print `filename: OLD → NEW` for each changed file
- Write back with `yaml.dump(..., allow_unicode=True, sort_keys=False)`

`clone` subcommand:
- Read base config with `yaml.safe_load`
- Override fields: if `--model` given, set `llm.model` and also all `bdikit_models.*` fields to same value; set `llm.provider` if `--provider` given; set `experiment.context` if `--context` given
- Derive experiment name from `--name` if given, else construct as `{base_stem}_{model_slug}` where `model_slug` replaces `/` and `.` with `-`
- Write to `output_dir/dou_harmonization_{name}.yaml`
- Print the output path

`regenerate` subcommand:
- Call `subprocess.run(["python", "generate_env.py", "--config", str(config_path)])` (check if generate_env.py accepts --config; if not, adapt to however it works)
- Print result

`validate` subcommand:
- Attempt `load_config(path)` for each YAML in dir
- Report: OK, PARSE_ERROR, MISSING_FIELD, etc.
- Exit code 1 if any failures

**Error handling:** All subcommands should exit with code 0 on full success, 1 on partial failure (some files failed), 2 on complete failure.

### Commit message to use
```
Add manage_configs.py: CLI tool for experiment config management

Provides subcommands for agents and humans to manage YAML experiment configs:
- list: display all configs with key metadata
- get: read a field value from one or more configs
- set: update a field in one or more configs (supports --dry-run, --filter)
- clone: create a new config from a base with field overrides
- regenerate: rebuild the associated.env for a config
- validate: parse all configs and report errors

Designed for use by automated agents and humans maintaining the experiment matrix.
```

---

## Work Package E — runner.py + config.py: Configurable Input Files + LLMConfig Rename

**Subagent name:** `WP-E_runner_config_input_files`
**Progress file:** `docs/parallel_codebase_upgrade_outputs/03_03_2026_1253_WP-E_runner_config_input_files_implementation_progress.md`

### Context files to read first
- `src/automation/config.py` (full file — understand OutputConfig, ExperimentConfig.from_dict)
- `src/automation/runner.py` (lines 325–381: `_setup_kernel_working_directory`, line 337 hardcoded list)
- `src/bdikit_context/config/__init__.py` (the LLMConfig class there — to understand what to rename)
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_claude-sonnet-4.6.yaml` (example to confirm `output:` section format)
- `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml` (generation-1 config to check artifact paths)

### Changes to make

**E1 — Add `input_files` to `OutputConfig` in `src/automation/config.py`**

In the `OutputConfig` dataclass:
```python
@dataclass
class OutputConfig:
    """Output configuration for an experiment."""
    base_dir: str = "./results"
    save_artifacts: list[str] = field(default_factory=list)
    input_files: list[str] = field(default_factory=lambda: ["dou.csv", "data.csv", "input.csv"])
```

In `ExperimentConfig.from_dict()`, update the `output = OutputConfig(...)` construction:
```python
output = OutputConfig(
    base_dir=output_data.get("base_dir", "./results"),
    save_artifacts=output_data.get("save_artifacts", []),
    input_files=output_data.get("input_files", ["dou.csv", "data.csv", "input.csv"]),
)
```

**E2 — Use `input_files` in `src/automation/runner.py`**

In `_setup_kernel_working_directory()` (lines 337–338):
Replace:
```python
data_files = ["dou.csv", "data.csv", "input.csv"]
```
With:
```python
data_files = self.config.output.input_files
```

**E3 — Fix artifact path inconsistency in generation-1 configs**

Check `dou_harmonization_anyllm_devstral.yaml` and `dou_harmonization_nemotron-3-nano.yaml` (and any others lacking `context:` field — find them with `grep -rL "^context:" experiments/.../automated/*.yaml`).

For each generation-1 config:
- Check if `save_artifacts` contains bare `"dou_harmonized.csv"` vs `"results/dou_harmonized.csv"`
- Check what all generation-2 configs use (use `grep "dou_harmonized" experiments/.../automated/*.yaml`)
- Standardize to match generation-2 convention
- Also add `context: bdikit_context` (or appropriate context) if the `context:` field is missing

**E4 — Rename `LLMConfig` → `ContainerLLMConfig` in `src/bdikit_context/config/__init__.py`**

(Note: WP-A also touches this file to remove `use_anyllm` — coordinate: WP-A removes fields, WP-E renames the class. These are non-conflicting edits. If both run simultaneously, do both changes in the same edit pass to avoid conflicts.)

1. Rename class `LLMConfig` to `ContainerLLMConfig` throughout `src/bdikit_context/config/__init__.py`
2. Update `HarmoniaConfig` to reference `ContainerLLMConfig`:
   ```python
   @dataclass
   class HarmoniaConfig:
       llm: ContainerLLMConfig = field(default_factory=ContainerLLMConfig)
   ```
3. Search for any other references to `bdikit_context.config.LLMConfig` or `from bdikit_context.config import LLMConfig`:
   ```bash
   grep -rn "from.*bdikit_context.*config.*import.*LLMConfig\|bdikit_context.config.LLMConfig" src/
   ```
   Update any found references.

### Commit message to use
```
Make experiment input files configurable; fix config naming conflicts

- Add input_files field to OutputConfig (default: ["dou.csv", "data.csv", "input.csv"])
- Use config.output.input_files in runner._setup_kernel_working_directory() instead
  of hardcoded list; makes the runner reusable for experiments 2 and 3
- Fix artifact path inconsistency in generation-1 configs (standardize save_artifacts)
- Add context: field to generation-1 configs that were missing it
- Rename LLMConfig → ContainerLLMConfig in bdikit_context/config/__init__.py to
  eliminate naming collision with automation/config.py:LLMConfig
```

---

## Work Package F — Shell Monolith: Extract Ollama + VRAM into Python (Incremental)

**Subagent name:** `WP-F_ollama_python_launcher`
**Progress file:** `docs/parallel_codebase_upgrade_outputs/03_03_2026_1253_WP-F_ollama_python_launcher_implementation_progress.md`

### Context files to read first
- `exec_apptainer_harmonia.sh` (FULL FILE — 1192 lines. Key sections: `estimate_vram_usage()` bash function, Ollama port calculation, Ollama startup loop, model pre-load logic)
- `src/automation/config.py` (for type reference)

Find in `exec_apptainer_harmonia.sh`:
- The `estimate_vram_usage()` bash function (search for "estimate_vram")
- Port calculation: search for `OLLAMA_PORT=` or `11434`
- Ollama startup: search for `ollama serve`
- Model preload: search for `ollama pull` or `ollama run`

### Changes to make

**F1 — Create `src/automation/ollama_launcher.py`**

This is a new Python module (~200 lines) that:
1. Replicates the VRAM estimation logic from the bash function as `estimate_vram_usage(model_name, context_length)`
2. Provides `get_ollama_port(job_id=None)` — `11434 + 1 + (job_id % 200)` or random if no job_id
3. Can be run as a CLI for use from bash scripts

Read the bash `estimate_vram_usage()` function carefully and replicate its parameter lookup table and formula in Python. Common structure: lookup model parameters by name pattern → compute bytes needed → add context overhead.

```python
#!/usr/bin/env python3
"""
Ollama orchestration utilities — Python equivalents of exec_apptainer_harmonia.sh
bash functions, enabling testability and reuse across the codebase.
"""

import os
import sys
import argparse
import subprocess
import time


# Model parameter estimates (billions of params)
# Derived from exec_apptainer_harmonia.sh estimate_vram_usage()
MODEL_PARAM_ESTIMATES = {
    # ... copy the lookup table from the bash function ...
}


def estimate_vram_usage(model_name: str, context_length: int = 8192) -> dict:
    """
    Estimate VRAM requirements for a model+context combination.

    Returns dict with keys: vram_gb (float), recommendation (str), params_b (float)
    Replicates the estimate_vram_usage() bash function in exec_apptainer_harmonia.sh.
    """
    # ... implementation ...


def get_ollama_port(job_id: int | None = None) -> int:
    """
    Get deterministic Ollama port for this job.
    Port = 11434 + 1 + (job_id % 200), or random 11600-11800 if no job_id.
    """
    if job_id is not None:
        return 11434 + 1 + (job_id % 200)
    import random
    return random.randint(11600, 11800)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    vram_p = subparsers.add_parser("estimate-vram")
    vram_p.add_argument("--model", required=True)
    vram_p.add_argument("--context", type=int, default=8192)

    port_p = subparsers.add_parser("get-port")
    port_p.add_argument("--job-id", type=int, default=None)

    args = parser.parse_args()

    if args.command == "estimate-vram":
        result = estimate_vram_usage(args.model, args.context)
        print(f"VRAM estimate: {result['vram_gb']:.1f} GB")
        print(f"Recommendation: {result['recommendation']}")
    elif args.command == "get-port":
        print(get_ollama_port(args.job_id))


if __name__ == "__main__":
    main()
```

**F2 — Integrate into `exec_apptainer_harmonia.sh`**

Find where `exec_apptainer_harmonia.sh` calls the bash `estimate_vram_usage()` function and replace with:
```bash
# Python-backed VRAM estimation (see src/automation/ollama_launcher.py)
python3 "{{project_dir}}/src/automation/ollama_launcher.py" estimate-vram \
    --model "$OLLAMA_MODEL" --context "${OLLAMA_CONTEXT_LENGTH:-8192}" || true
```

Find where the Ollama port is calculated and replace with:
```bash
OLLAMA_PORT=$(python3 "{{project_dir}}/src/automation/ollama_launcher.py" get-port --job-id "${SLURM_JOB_ID:-}")
```

(Use absolute paths or `$( cd "$(dirname "$0")" && pwd )` to make the path robust.)

Keep the rest of the shell script unchanged for this incremental phase.

**F3 — Create `tests/test_ollama_launcher.py`**

```python
from automation.ollama_launcher import estimate_vram_usage, get_ollama_port

def test_get_port_deterministic():
    assert get_ollama_port(job_id=100) == 11535  # 11434 + 1 + 100
    assert get_ollama_port(job_id=0) == 11435

def test_get_port_no_job_id():
    port = get_ollama_port()
    assert 11600 <= port <= 11800

def test_vram_estimate_returns_dict():
    result = estimate_vram_usage("devstral:latest", 32768)
    assert "vram_gb" in result
    assert "recommendation" in result
    assert result["vram_gb"] > 0

def test_vram_estimate_context_scales():
    r1 = estimate_vram_usage("devstral:latest", 8192)
    r2 = estimate_vram_usage("devstral:latest", 65536)
    assert r2["vram_gb"] > r1["vram_gb"]
```

### Commit message to use
```
Extract Ollama port + VRAM estimation from shell script into Python (incremental)

Create src/automation/ollama_launcher.py with:
- estimate_vram_usage(model_name, context_length): Python equivalent of the bash
  estimate_vram_usage() function in exec_apptainer_harmonia.sh
- get_ollama_port(job_id): deterministic port calculation (11434 + 1 + job_id % 200)
- CLI interface for both functions, callable from bash scripts

Integrate into exec_apptainer_harmonia.sh:
- Replace bash estimate_vram_usage() call with python3 ollama_launcher.py estimate-vram
- Replace port calculation with python3 ollama_launcher.py get-port

Add tests/test_ollama_launcher.py with unit tests for both functions.
This is the first incremental step of the exec_apptainer_harmonia.sh refactor.
```

---

## Work Package G — Quality Tooling: pre-commit + Smoke Tests

**Subagent name:** `WP-G_quality_tooling`
**Progress file:** `docs/parallel_codebase_upgrade_outputs/03_03_2026_1253_WP-G_quality_tooling_implementation_progress.md`

### Context files to read first
- `pyproject.toml` (to understand existing [tool.*] sections and where to add ruff config)
- `src/context_management/test_kernel_state_budget.py` (the existing test file — use as a pattern)
- `src/evaluation/visualization/normalize.py` (to understand `build_tables()` signature for smoke test)
- `src/evaluation/metrics.py` (to understand what a minimal `metrics.json` looks like)

### Changes to make

**G1 — Add Ruff config to `pyproject.toml`**

Add at the end of `pyproject.toml`:
```toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["F", "E", "W", "I"]
ignore = ["E501"]
exclude = ["src/context_management/test_*", "src/bdikit_context/__about__.py"]
```

**G2 — Create `.pre-commit-config.yaml`** in repo root:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
  - repo: https://github.com/shellcheck-py/shellcheck-py
    rev: v0.10.0.1
    hooks:
      - id: shellcheck
        files: \.(sh)$
        exclude: "^jobs/"  # Generated scripts may have issues; focus on templates
  - repo: https://github.com/adrienverge/yamllint
    rev: v1.35.1
    hooks:
      - id: yamllint
        args: [-d, relaxed]
        exclude: "^experiments/"  # Config files are not standard YAML style
```

**G3 — Install pre-commit and run ruff one-time cleanup**

```bash
.venv/bin/pip install pre-commit ruff
.venv/bin/pre-commit install
.venv/bin/ruff check src/ --fix --select F,I  # Fix unused imports and isort only (safe fixes)
```

Note: only run safe auto-fixes (F = pyflakes unused imports, I = isort). Do NOT run E/W auto-fix as it may reformat code unexpectedly.

**G4 — Create `tests/` directory and `tests/test_config_loading.py`**

```python
"""
Smoke test: verify all automated experiment configs parse without errors.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from automation import load_config

CONFIG_DIR = Path(__file__).parent.parent / "experiments/experiment_1_harmonia_dou2020_gdc/configs/automated"

config_files = sorted(CONFIG_DIR.glob("*.yaml"))


@pytest.mark.parametrize("config_path", config_files, ids=[p.stem for p in config_files])
def test_config_loads_without_error(config_path):
    """Each config YAML must parse into a valid ExperimentConfig."""
    config = load_config(config_path)
    assert config.name, f"Config has no name: {config_path}"
    assert config.llm.provider, f"Config has no LLM provider: {config_path}"
    assert config.llm.model, f"Config has no LLM model: {config_path}"


def test_all_configs_found():
    """Sanity check: at least 25 automated configs expected."""
    assert len(config_files) >= 25, f"Expected ≥25 configs, found {len(config_files)}"
```

**G5 — Create `tests/fixtures/` and `tests/test_metrics_smoke.py`**

Create `tests/fixtures/sample_metrics.json` — a minimal but realistic metrics bundle (look at what `calculate_all_metrics()` actually produces by reading `src/evaluation/metrics.py` output format).

Then create `tests/test_metrics_smoke.py`:
```python
"""
Smoke test: verify normalize.build_tables() works on a sample metrics.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

FIXTURE = Path(__file__).parent / "fixtures" / "sample_metrics.json"


def test_fixture_loads():
    data = json.loads(FIXTURE.read_text())
    assert "column_mapping" in data or "results" in data  # basic sanity


def test_build_tables_returns_dataframes():
    from evaluation.visualization.normalize import build_tables
    data = json.loads(FIXTURE.read_text())
    tables = build_tables([data])
    # build_tables returns a dict of DataFrames; check at least one exists
    assert tables is not None
    assert len(tables) > 0
```

**G6 — Update `pyproject.toml` test configuration**

Add to the `[tool.hatch.envs.default.scripts]` section (or add a standalone pytest config):
```toml
[tool.pytest.ini_options]
testpaths = ["tests", "src/context_management"]
python_files = ["test_*.py"]
```

### Commit message to use
```
Add pre-commit hooks, ruff config, and smoke tests

- Add [tool.ruff] config to pyproject.toml (line-length=100, F+E+W+I rules)
- Create .pre-commit-config.yaml with ruff, shellcheck, yamllint hooks
- Install pre-commit in .venv and run initial ruff --fix for safe cleanup
- Create tests/test_config_loading.py: parametrized test loading all 30 automated configs
- Create tests/fixtures/sample_metrics.json: minimal metrics.json fixture
- Create tests/test_metrics_smoke.py: smoke test for normalize.build_tables()
- Add [tool.pytest.ini_options] to pyproject.toml
```

---

## Summary Table

| WP | Name | Key Output Files | Parallelizable |
|----|------|-----------------|----------------|
| A | Dead code + anyllm cleanup | Many config YAMLs, client.py, bdikit_context/config/__init__.py, bdikit_context/llm/__init__.py | Yes |
| B | Wire ArchytasContextConfig + entry point | pyproject.toml, bdikit_context/context.py, code_context/context.py, generate_env.py | Yes |
| C | Provider prefix + generate_jobs.py | NEW provider_prefixes.py, litellm_model.py, agent.py, codeact_context/context.py, generate_jobs.py, templates | After A (soft dep) |
| D | manage_configs.py CLI | NEW manage_configs.py | Yes |
| E | runner.py + config.py + LLMConfig rename | automation/config.py, automation/runner.py, bdikit_context/config/__init__.py, generation-1 configs | Yes* |
| F | Ollama launcher Python module | NEW ollama_launcher.py, exec_apptainer_harmonia.sh, tests/test_ollama_launcher.py | Yes |
| G | Quality tooling | pyproject.toml, NEW .pre-commit-config.yaml, tests/test_config_loading.py, tests/test_metrics_smoke.py | After A (soft dep for ruff) |

*Note: WP-E also touches `src/bdikit_context/config/__init__.py` (to rename LLMConfig). WP-A also touches this file (to remove use_anyllm). If running simultaneously, coordinate: the subagent that finishes second must re-read the file and make only its own changes on top of the other's.
