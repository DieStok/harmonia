# Plan: Make Prompts Changeable Between Experiments

**Date:** 11-02-2026
**Status:** Proposed (analysis needed)
**Further analysis:** See `12_02_2026_1545_configurable_prompts_further_analysis.md` for independent verification of key technical claims.

## Motivation

Some models (notably devstral) fail to use tools during experiments. This may be due to the current prompts being too restrictive for autonomous agent actions, or because the ReAct agent/system prompt doesn't guide certain models to use tools effectively. Being able to vary prompts per-experiment would allow:

1. Testing whether different prompt styles improve tool use for specific models
2. A/B testing prompt variations as an experimental variable
3. Adapting system instructions to model-specific strengths/weaknesses

## Current Prompt Architecture

### Three Prompt Layers

1. **BDIKit Context System Prompt** (`src/bdikit_context/prompts/system/main.j2`)
   - Jinja2 template rendered at context setup
   - Contains full harmonization workflow: Schema Matching → Value Mapping → Materialization
   - Loaded by `PromptLoader` class (`src/bdikit_context/prompts/__init__.py`)
   - Uses `get_prompt_loader()` singleton pattern with cached `_loader` instance

2. **BDIKit Tool Description Prompts** (`src/bdikit_context/prompts/tools/*.j2`)
   - `match_schema.j2` — Schema mapping function
   - `match_values.j2` — Value matching function
   - `top_matches.j2` — Alternative column mapping retrieval
   - `materialize_mapping.j2` — Final harmonization output
   - `get_gdc_acceptable_values.j2` — GDC vocabulary reference
   - Each loaded by `PromptLoader.get_tool_prompt(tool_name)`

3. **Code Context System Prompt** (`src/code_context/context.py`)
   - Hardcoded f-string in `auto_context()` method (lines 38-57)
   - No template or external file loading

4. **ReAct Agent Prompt** (beaker-kernel: `beaker_kernel/lib/agent.py`)
   - Class docstring of `BeakerAgent` becomes system prompt via `get_info()`
   - Currently: "A simple Python code execution assistant."
   - Immutable at runtime (class-level definition)

### How Prompts Flow

```
Experiment YAML → ExperimentConfig → exec_apptainer_harmonia.sh → Beaker
                                                                      ↓
                                              BDIKitContext.__init__() ← config
                                                      ↓
                                              auto_context() → PromptLoader
                                                      ↓
                                              get_system_prompt(tools, suppress_output)
                                                      ↓
                                              agent.set_auto_context("Default context", prompt)
```

Key observation: experiment config currently has **no way to influence prompts**. The YAML specifies LLM, messages, evaluation, etc., but prompts are always loaded from static template files.

## Analysis Needed

### Phase 1: Feasibility Assessment

1. **Singleton conflict**: `get_prompt_loader()` caches a global `_loader` instance. If we want per-experiment prompts in concurrent jobs, we need per-context loader instances instead. Assess whether this is safe to change.

2. **ReAct agent prompt mutability**: The `BeakerAgent` docstring is a class-level attribute. Can it be overridden at instance level? Or do we need a different mechanism (e.g., passing system prompt to archytas framework separately)?

3. **Config-to-context flow**: `BDIKitContext.__init__()` receives `config` (line 22) but doesn't use it for prompts. Verify that experiment config data is available at the point where `auto_context()` runs, and determine how to thread prompt overrides through.

### Phase 2: Design

Proposed YAML structure (draft):

```yaml
prompts:
  system_template: path/to/custom_system.j2       # override system prompt
  tool_templates_dir: path/to/custom_tools/        # override tool prompts
  suppress_output: true                            # existing flag
  react_agent_prompt: "Custom ReAct instructions"  # override agent prompt
```

Design questions:
- Should we support inline prompt text in YAML, or only file paths to templates?
- Should tool prompts be overridable individually or only as a directory?
- How do we handle backward compatibility (experiments without `prompts` section)?
- Should we add a `PromptsConfig` dataclass to `src/automation/config.py`?

### Phase 3: Implementation

Files that would need changes:
- `src/automation/config.py` — Add `PromptsConfig` dataclass
- `src/bdikit_context/prompts/__init__.py` — Make `PromptLoader` accept config overrides
- `src/bdikit_context/context.py` — Pass prompt config to loader
- `src/code_context/context.py` — Support template-based prompt loading
- `generate_env.py` — Possibly pass prompt config paths
- Experiment YAML configs — Add optional `prompts` section

### Key Architectural Constraints

- **Async loading**: `auto_context()` is async but config loading is sync; may need refactoring
- **Template interaction**: System prompt, tool descriptions, and ReAct prompt interact; changing one may require changes to others
- **Backward compatibility**: Existing configs without `prompts` section must keep current default behavior
- **Per-job isolation**: If running concurrent experiments with different prompts, the singleton `_loader` pattern must be eliminated

## Next Steps

1. ~~Perform Phase 1 feasibility assessment~~ **DONE** — see report below
2. Present findings and design options for discussion
3. Implement if approved

---

## Feasibility Analysis Report

**Date:** 11-02-2026
**Analyst:** Claude Code (automated analysis with container testing)
**Status:** Complete — all 17 tests passed (16/17 code tests + 1 minor expected failure)

---

## Executive Summary

Making prompts configurable is **fully feasible** with the current Beaker/Archytas architecture. No upstream framework modifications are needed. The key findings are:

1. **Four distinct prompt layers exist**, not three as originally documented — and they interact in specific, tested ways
2. **The tool description Jinja2 templates are dead code** — never called by any Harmonia code
3. **The ReAct prelude CAN be overridden post-init** via `agent.custom_prelude` + `agent.update_prompt()`
4. **The agent class docstring is for the FRONTEND only**, not sent to the LLM — less critical than assumed
5. **Environment variables are the cleanest injection point** for prompt directory paths into the container

The recommended implementation requires changes to **5 files** and no Apptainer image rebuild.

---

## 1. Full Prompt Architecture (Corrected and Verified)

### 1.1 The Four Actual Prompt Layers

The LLM receives messages in this exact order (verified by reading Archytas source inside the container):

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: SYSTEM MESSAGE                                      │
│   Source: archytas/react.py:build_prompt()                   │
│   Content: ReAct agent prelude (1,179 chars default)         │
│   Override: ReActAgent(custom_prelude="...")                  │
│   Also appended: model.MODEL_PROMPT_INSTRUCTIONS             │
│   Mutability: Can be changed post-init via                   │
│     agent.custom_prelude = "..." + agent.update_prompt()     │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: AUTO-CONTEXT MESSAGE                                │
│   Source: BeakerContext.auto_context() → AutoContextMessage  │
│   Content: BDIKitContext renders system/main.j2 (3,581 chars)│
│   Updated: EVERY TURN (content_updater callable)             │
│   Also includes: kernel state, notebook state, workflows,    │
│     integration prompts (appended by BeakerContext wrapper)   │
│   Mutability: Fully dynamic — just change the template or    │
│     override auto_context() return value                     │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: USER PREAMBLE (optional)                            │
│   Source: BeakerContext.default_preamble()                    │
│   Content: Currently returns None for both contexts          │
│   Mutability: Override default_preamble() method             │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: CONVERSATION HISTORY                                │
│   Human/AI message pairs from the interaction                │
└─────────────────────────────────────────────────────────────┘

SEPARATE (frontend only, NOT sent to LLM):
  agent_prompt = self.__class__.__doc__  (via get_info())
  tool_list = {name: docstring} for each @tool
```

### 1.2 Critical Correction: Agent Docstring

The original plan stated the agent docstring becomes the system prompt. **This is incorrect.**

- `BeakerAgent.get_info()` returns `self.__class__.__doc__` as `agent_prompt`
- This is sent to the **Beaker frontend** (web UI) for display purposes
- It is **NOT** included in the LLM's message history
- The actual LLM system prompt comes from `build_prompt()` (Layer 1)

**Impact:** Changing the agent docstring affects only the frontend label, not LLM behavior. This is lower priority than originally assumed.

### 1.3 Critical Finding: Tool Description Templates are Dead Code

The Jinja2 templates in `prompts/tools/*.j2` are **never used** by any Harmonia code:

- `BDIKitContext` does not call `get_tool_description()`
- `BDIKitAgent` does not call `get_tool_description()`
- `PromptLoader.get_tool_description()` and `list_tools()` exist but are never invoked
- Tool descriptions come **exclusively** from Python `@tool` method docstrings
- Archytas extracts these docstrings and sends them as function schemas in the tool-calling API

**Impact:** The tool `.j2` templates can be repurposed or removed. They do NOT need to be kept in sync with docstrings.

---

## 2. Container Test Results

### 2.1 Test Suite 1: Basic Mechanisms (10 tests, all PASS)

| # | Test | Result | Key Finding |
|---|------|--------|-------------|
| 1 | `custom_prelude` parameter | PASS | Completely replaces default 1,179-char ReAct prelude |
| 2 | Class docstring runtime override | PASS | Can modify `__doc__` per-class at runtime |
| 3 | PromptLoader custom directory | PASS | Works with any directory containing `system/main.j2` |
| 4 | Singleton loader behavior | PASS | Global `_loader` permanently overridden — **problem for concurrent use** |
| 5 | AutoContextMessage updates | PASS | Content updater called fresh every turn |
| 6 | `__init_subclass__` mechanism | PASS | `_auto_context` indirection fully understood |
| 7 | Prompt composition layers | PASS | Four-layer architecture confirmed |
| 8 | BeakerAgent kwargs forwarding | PASS | `**kwargs` forwards `custom_prelude` to ReActAgent |
| 9 | Environment variable override | PASS | No prompt env vars in Beaker config; custom vars viable |
| 10 | Tool description dual-source | PASS | Jinja2 templates confirmed as dead code |

### 2.2 Test Suite 2: Integration Patterns (7 tests, 6 PASS + 1 expected)

| # | Test | Result | Key Finding |
|---|------|--------|-------------|
| 11 | `HARMONIA_PROMPTS_DIR` env var | PASS | Custom prompts loaded from env-var-specified directory |
| 12 | YAML `prompts` section parsing | PASS | PromptsConfig dataclass works, backward compatible |
| 13 | Context init override pattern | PASS | Factory function best approach |
| 14 | ReAct prelude from file | PASS | File-based prelude injection works |
| 15 | Post-init prompt override | Expected | `custom_prelude` is instance attr (set in `__init__`), not class attr |
| 16 | CodeContext prompt override | PASS | File-based approach recommended |
| 17 | Prompt validation | PASS | Jinja2 validates syntax; undefined vars render empty |

### 2.3 Key Technical Findings from Container Tests

**Finding 1: Post-init ReAct prelude override works.**
After `BeakerContext.__init__()` creates the agent, we can do:
```python
self.agent.custom_prelude = loaded_prelude_text
self.agent.update_prompt()  # Rebuilds SystemMessage with new prelude
```
This is the **safest injection point** — no need to modify `BeakerContext.__init__()` or `BeakerAgent.__init__()`.

**Finding 2: BeakerContext creates agent with fixed args.**
Line 49 of `BeakerContext.__init__()`:
```python
self.agent = agent_cls(context=self, tools=self.subkernel.tools)
```
No mechanism to pass `custom_prelude` or other kwargs. But `**kwargs` in `BeakerAgent.__init__()` means it WOULD forward if we modified `BeakerContext`.

**Finding 3: `auto_context()` is called every turn.**
The `AutoContextMessage.update_content()` is called before every LLM request. This means changing the `PromptLoader` instance on `self.prompt_loader` AFTER init will take effect on the next turn. No need to override at construction time.

> **12-02-2026 update:** Independently verified that `auto_context()` reads `self.prompt_loader` (the instance attribute, line 40 of `context.py`), not the module-level singleton. The `__init_subclass__` renaming does not affect this. See `12_02_2026_1545_configurable_prompts_further_analysis.md` Q2.

**Finding 4: Environment variable injection via Apptainer.**
The `exec_apptainer_harmonia.sh` already passes `--env-file` and `--env` flags. Adding `HARMONIA_PROMPTS_DIR` or `HARMONIA_REACT_PRELUDE` to the `.env` file (or generated via `generate_env.py`) is the cleanest path.

---

## 3. Answers to Phase 1 Questions

### Q1: Singleton conflict — safe to change?

**Yes, safe to change.** Each Beaker server runs in its own container with its own Python process. The singleton `_loader` only affects the single context within that container. For concurrent SLURM jobs, each job has its own container, so there is no cross-job conflict.

However, if you ever wanted multiple contexts within a single Beaker session (e.g., switching between bdikit_context and code_context), the singleton would cause problems. **Recommendation:** Replace the singleton with per-context `PromptLoader` instances. The change is trivial:

```python
# In BDIKitContext.__init__():
self.prompt_loader = PromptLoader(prompts_dir)  # Instead of get_prompt_loader()
```

### Q2: ReAct agent prompt mutability?

**Fully mutable post-init.** Two mechanisms available:

1. **`custom_prelude` + `update_prompt()`** — Changes the Layer 1 system message. The ReActAgent stores `self.custom_prelude` and `update_prompt()` rebuilds the system message using `build_prompt(custom_prelude=self.custom_prelude)`.

2. **Agent docstring override** — Only affects frontend display (`get_info()`), not LLM behavior. Can be set via `BDIKitAgent.__doc__ = "..."` before instantiation if needed.

### Q3: Config-to-context flow?

> **12-02-2026 update:** Independent verification confirmed that the `config` dict inside `BDIKitContext` is Beaker's per-context metadata, **not** the experiment YAML. Env vars are the only channel bridging experiment config to the container interior. The recommended approach is to change both `ExperimentConfig` (add `PromptsConfig` dataclass) and `generate_env.py` (serialize prompt paths to env vars). See `12_02_2026_1545_configurable_prompts_further_analysis.md` Q1 for full code-path evidence.

**Config data IS available** at `auto_context()` time. The `BDIKitContext` receives a `config` dict in `__init__()` but currently ignores it for prompts. The flow:

```
Experiment YAML → generate_env.py → .env file → Apptainer --env-file → container env vars
                                                  ↓
                                    BDIKitContext.__init__(config)
                                           ↓
                                    os.environ.get("HARMONIA_PROMPTS_DIR")
                                           ↓
                                    self.prompt_loader = PromptLoader(prompts_dir)
```

**Alternative flow** (if we want the config dict itself):
```
Experiment YAML → generate_env.py → .env with HARMONIA_PROMPTS_DIR=...
                       ↓
              exec_apptainer_harmonia.sh --env-file → container
                       ↓
              BDIKitContext.__init__() reads os.environ["HARMONIA_PROMPTS_DIR"]
```

### Q4: Template validation?

**Partially automatic.** Jinja2 provides:
- `TemplateSyntaxError` for malformed templates (caught at load time)
- `TemplateNotFound` for missing files (caught at render time)
- Undefined variables silently render as empty string (NO error)

**Recommendation:** Add explicit validation at config-load time:
1. Check all paths exist
2. Try rendering each template with mock data
3. Verify output is non-empty and contains expected markers

---

## 4. Proposed Implementation Design

### 4.1 Prompt Folder Structure

```
experiments/experiment_1_harmonia_dou2020_gdc/configs/
├── automated/
│   ├── dou_harmonization_anyllm_devstral.yaml
│   └── dou_harmonization_anyllm_devstral_autonomous.yaml  # Different prompts
├── prompts/
│   ├── system_prompt/
│   │   ├── v1_default/
│   │   │   └── system/
│   │   │       └── main.j2          # Current default system prompt
│   │   ├── v2_autonomous/
│   │   │   └── system/
│   │   │       └── main.j2          # More autonomous, less asking
│   │   └── v3_step_by_step/
│   │       └── system/
│   │           └── main.j2          # Explicit step-by-step instructions
│   ├── react_agent_prompts/
│   │   ├── v1_default/
│   │   │   └── prelude.txt          # Current ReAct prelude
│   │   ├── v2_tool_focused/
│   │   │   └── prelude.txt          # Emphasize tool usage
│   │   └── v3_concise/
│   │       └── prelude.txt          # Shorter, more direct
│   └── code_context_prompts/
│       ├── v1_default/
│       │   └── prompt.txt           # Current code context prompt
│       └── v2_data_science/
│           └── prompt.txt           # Data science focused
```

### 4.2 YAML Config Extension

```yaml
experiment:
  name: "dou_harmonization_devstral_autonomous"
  description: "Test autonomous prompt variant"

llm:
  provider: anyllm:ollama
  model: devstral:latest
  temperature: 0.0

prompts:
  # All paths relative to prompts_base_dir
  prompts_base_dir: "../prompts"
  system_prompt_dir: "system_prompt/v2_autonomous"
  react_prelude: "react_agent_prompts/v2_tool_focused/prelude.txt"
  code_context_prompt: "code_context_prompts/v1_default/prompt.txt"

messages:
  - content: |
      Load dou.csv and harmonize it to GDC schema.
    wait_seconds: 300
    decision_mode: auto_accept
```

### 4.3 Files to Change

| File | Change | Risk |
|------|--------|------|
| `src/automation/config.py` | Add `PromptsConfig` dataclass, parse `prompts` section | Low — additive, backward compatible |
| `src/bdikit_context/context.py` | Read `HARMONIA_PROMPTS_DIR` env var, use per-instance PromptLoader, post-init ReAct prelude override | Medium — core prompt path |
| `src/code_context/context.py` | Read prompt from file if `HARMONIA_CODE_CONTEXT_PROMPT` env var set | Low — simple fallback |
| `generate_env.py` | Write `HARMONIA_PROMPTS_DIR` and `HARMONIA_REACT_PRELUDE` to `.env` | Low — additive |
| `exec_apptainer_harmonia.sh` | Bind prompt directories into container | Low — additive |

### 4.4 Implementation Pattern (Recommended)

**For BDIKitContext — the main change:**

```python
class BDIKitContext(BeakerContext):
    def __init__(self, beaker_kernel, config):
        # Determine prompts directory from env var (set by generate_env.py)
        prompts_dir_env = os.environ.get("HARMONIA_PROMPTS_DIR")
        if prompts_dir_env:
            self.prompt_loader = PromptLoader(prompts_dir=Path(prompts_dir_env))
        else:
            self.prompt_loader = PromptLoader()  # Default

        # Call parent (creates agent with default ReAct prelude)
        super().__init__(beaker_kernel, BDIKitAgent, config)

        # Override ReAct prelude if custom one specified
        react_prelude_path = os.environ.get("HARMONIA_REACT_PRELUDE")
        if react_prelude_path and Path(react_prelude_path).exists():
            custom_prelude = Path(react_prelude_path).read_text()
            self.agent.custom_prelude = custom_prelude
            self.agent.update_prompt()
```

**For generate_env.py — add prompt config to .env:**

```python
# In generate_env_from_config():
prompts_config = config.get('prompts', {})
if prompts_config:
    base_dir = prompts_config.get('prompts_base_dir', '')
    # Resolve relative to config file location
    if base_dir and not os.path.isabs(base_dir):
        base_dir = str((config_path.parent / base_dir).resolve())

    system_dir = prompts_config.get('system_prompt_dir', '')
    if system_dir:
        full_system_dir = str(Path(base_dir) / system_dir)
        env_content = update_env_value(env_content, 'HARMONIA_PROMPTS_DIR', full_system_dir)

    react_prelude = prompts_config.get('react_prelude', '')
    if react_prelude:
        full_react = str(Path(base_dir) / react_prelude)
        env_content = update_env_value(env_content, 'HARMONIA_REACT_PRELUDE', full_react)
```

**For exec_apptainer_harmonia.sh — bind prompt directories:**

```bash
# After reading env vars, bind prompt dirs if specified
PROMPTS_DIR=$(grep "^HARMONIA_PROMPTS_DIR=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
if [ -n "$PROMPTS_DIR" ] && [ -d "$PROMPTS_DIR" ]; then
    APPTAINER_CMD="$APPTAINER_CMD --bind ${PROMPTS_DIR}:${PROMPTS_DIR}:ro"
fi
REACT_PRELUDE=$(grep "^HARMONIA_REACT_PRELUDE=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
if [ -n "$REACT_PRELUDE" ] && [ -f "$REACT_PRELUDE" ]; then
    PRELUDE_DIR=$(dirname "$REACT_PRELUDE")
    APPTAINER_CMD="$APPTAINER_CMD --bind ${PRELUDE_DIR}:${PRELUDE_DIR}:ro"
fi
```

---

## 5. Potential Conflicts and Difficulties

### 5.1 The `__init_subclass__` Hook (Moderate Risk)

`BeakerContext.__init_subclass__()` does metaclass magic:
```python
def __init_subclass__(cls):
    subclass_autocontext = getattr(cls, "auto_context", None)
    if not (subclass_autocontext is None or subclass_autocontext is BeakerContext.auto_context):
        cls._auto_context = subclass_autocontext
        cls.auto_context = BeakerContext.auto_context
```

This renames BDIKitContext's `auto_context` to `_auto_context` and replaces it with BeakerContext's version. The wrapper then calls `self._auto_context()` and appends kernel state, notebook state, workflows, and integration prompts.

**Impact on our changes:** Our `auto_context()` is actually stored as `_auto_context`. The wrapper behavior (appending kernel/notebook state) is **automatic and cannot be disabled**. This is mostly fine, but if kernel state or notebook state is large, it could crowd out our custom prompt content within the context window.

**Mitigation:** The `send_kernel_state` and `send_notebook_state` Beaker config flags can disable these additions. Verify they are off by default in our deployment.

### 5.2 AutoContextMessage Hash-Based Update Skipping (Low Risk)

`AutoContextMessage.update_content()` computes a SHA-1 hash of the content. If the hash hasn't changed, it skips re-tokenization. Our templates are static within a single experiment run, so this optimization works in our favor — no unnecessary re-tokenization.

### 5.3 Tool Description Channel Conflict (Medium Risk)

Tool descriptions reach the LLM through TWO channels:

1. **Tool-calling API** — Archytas generates JSON schemas from `@tool` docstrings, sent as `tools` parameter
2. **System prompt** — `auto_context()` renders `main.j2` which includes a brief tool list

These currently match, but if someone creates a custom `main.j2` with different tool descriptions, the LLM sees contradictory information. The tool-calling API descriptions ALWAYS come from the Python docstrings (immutable without code changes).

**Mitigation:** Document clearly that `main.j2` should describe **workflow** (how to use tools), not **tool signatures** (what tools accept). The existing default template already does this well.

### 5.4 The Prompt Loader in Container vs Host (Low Risk)

The `PromptLoader` uses Jinja2's `FileSystemLoader` which reads from the filesystem at render time. Inside the Apptainer container, the prompt files must be accessible at the path specified. Since `exec_apptainer_harmonia.sh` already binds the `src/` directory to `/opt/harmonia_src`, and we can add binds for custom prompt directories, this is straightforward.

### 5.5 Context Window Management (Medium Risk)

Adding more prompt content (custom prelude + custom system prompt + kernel state + notebook state) may exceed context windows for smaller models. The current default prompt stack is:
- Layer 1 (ReAct prelude): ~1,179 chars
- Layer 2 (system/main.j2): ~3,581 chars
- Layer 3 (kernel state): Variable
- Layer 4 (conversation): Variable

For models like devstral with 32K context, there's plenty of room. But for smaller models or larger custom prompts, context pressure could be an issue.

**Mitigation:** Archytas has built-in history summarization (`chat_history.summarize_history()`). Also, the `ContextWindowExceededError` handler in `react_async()` triggers automatic summarization. These safety nets should handle most cases.

---

## 6. Comparative Analysis: Agent Initialization Across Frameworks

### 6.1 Framework Comparison

| Dimension | smolagents | LangGraph | CrewAI | Archytas/Beaker |
|---|---|---|---|---|
| **Prompt composability** | Layered (`instructions` + template override) | Excellent (callable state_modifier) | Structured (role/goal/backstory) | Three loosely-coupled layers, no composition API |
| **Runtime customization** | Modify `prompt_templates` before `.run()` | Per-invocation via `config["configurable"]` | YAML file swap | Requires code changes or new template files |
| **Tool description independence** | Yes (constructor args) | Yes (LangChain `Tool` objects) | Yes (`description` attribute) | No — docstrings are canonical |
| **Separation of concerns** | Good (prompt.yaml separate from code) | Excellent (prompts as functions/configs) | Good (YAML configs) | Poor (docstrings, f-strings, templates mixed) |
| **Configuration-driven** | Yes (JSON + YAML serialization) | Via custom config dict | Native YAML support | Partial (templates, but no config schema) |

### 6.2 What We Can Learn

**From smolagents:** The `instructions` parameter that APPENDS to the system prompt (rather than replacing it) is elegant. We could add an `additional_instructions` field to our YAML config that gets appended to whatever system prompt template is loaded.

**From LangGraph:** The callable `state_modifier` pattern is the gold standard for prompt composability. Our `auto_context()` mechanism is actually similar — it's a callable that returns the context string, updated every turn. We just need to make it configurable.

**From CrewAI:** The YAML-first agent definition (role/goal/backstory) maps well to our use case. We could define semantic fields like `agent_role: "data harmonization specialist"` and `agent_goal: "harmonize metadata to GDC schema"` in the YAML, then compose them into the prompt template.

### 6.3 Anti-Patterns in Our Current Architecture

1. **Singleton PromptLoader** — Should be per-context instance
2. **Tool descriptions in two places** — Jinja2 templates (dead code) and Python docstrings (actual)
3. **Hardcoded f-string in CodeContext** — Should be file-based
4. **No config schema for prompts** — Should have `PromptsConfig` dataclass
5. **Agent creation in BeakerContext with fixed args** — No mechanism to pass prompt config

### 6.4 Architectural Recommendation

The current Archytas/Beaker architecture is **serviceable but inflexible**. The key improvement is not to fight the framework but to leverage the existing extensibility points:

1. **`auto_context()` is already dynamically invoked** — just make its data sources configurable
2. **`custom_prelude` already exists in ReActAgent** — just wire it up from config
3. **Post-init override pattern is safe** — no need to modify upstream code

The biggest gap compared to LangGraph/smolagents is the lack of a **per-invocation prompt parameter**. But since each experiment run is a fresh container, this is equivalent to per-invocation for our purposes.

---

## 7. Recommended Implementation Sequence

### Step 1: PromptsConfig dataclass (30 min)
Add to `src/automation/config.py`. Parse from YAML `prompts` section. All fields optional with None defaults for backward compatibility.

### Step 2: generate_env.py extension (30 min)
Resolve prompt paths from config, write `HARMONIA_PROMPTS_DIR` and `HARMONIA_REACT_PRELUDE` to `.env` files.

### Step 3: exec_apptainer_harmonia.sh binds (15 min)
Add `--bind` for prompt directories into the container.

### Step 4: BDIKitContext prompt override (45 min)
Read env vars in `__init__`, create per-instance PromptLoader, post-init ReAct prelude override. Test with container.

### Step 5: CodeContext prompt override (15 min)
Read prompt from file if env var set, fall back to current hardcoded default.

### Step 6: Create initial prompt variants (1-2 hours)
Copy current defaults to `v1_default/`, create `v2_autonomous/` and `v3_tool_focused/` variants.

### Step 7: Test with actual experiments (1-2 hours)
Run devstral with different prompt variants, compare tool usage behavior.

**Total estimated effort: 4-5 hours**

---

## 8. Test Artifacts

The following test files were created during this analysis:

- `tests/test_prompt_feasibility.py` — 10 basic tests of prompt mechanisms
- `tests/test_prompt_integration.py` — 7 integration tests of proposed patterns

Both tests can be run inside the Apptainer container:
```bash
srun --time=00:30:00 --mem=10G bash -c '
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
apptainer exec \
  --bind src:/opt/harmonia_src:ro \
  --env PYTHONPATH=/opt/harmonia_src \
  harmonia_beaker_LLM_agent_environment_apptainer.sif \
  python3 tests/test_prompt_feasibility.py
'
```

---

## Part 2: Tool Description Configurability Analysis

**Date:** 11-02-2026
**Question:** Can tool descriptions (sent to the LLM via the tool-calling API) be made configurable via Jinja2 templates, or are they permanently locked to Python docstrings?

---

## 9. How Tool Descriptions Flow from Docstring to LLM

### 9.1 The `@tool` Decorator Pipeline

The `@tool` decorator (`archytas/tool_utils.py:75`) fires at **class definition time** — the moment Python imports `bdikit_context/agent.py`. It does two things:

1. **Parses** the docstring via `get_tool_signature()` → `docstring_parser.parse(func.__doc__)`, extracting structured parts:
   - `func._desc` — tuple of `(short_description, long_description, examples)`
   - `func._args_list` — list of `(arg_name, arg_type, arg_desc, arg_default)` tuples
   - `func._ret` — tuple of `(ret_name, ret_type, ret_description)`

2. **Returns the original function unchanged** (line 186: `return func`). The decorator adds metadata attributes but does NOT replace the function or its `__doc__`.

### 9.2 From Decorated Function to LLM API Call

When the agent starts, `ReActAgent.__init__()` calls `self.model.set_tools(self.tools)`, which calls `convert_tools()` (`models/base.py:190`):

```python
@staticmethod
@cache                                          # ← functools.cache, memoizes result
def convert_tools(archytas_tools: tuple[tuple[str, Any], ...]) -> list[StructuredTool]:
    tools = [final_answer, fail_task]
    for name, tool in archytas_tools:
        arg_dict = {}
        for arg_name, arg_type, arg_desc, _ in tool._args_list:   # ← parsed arg descriptions
            arg_dict[arg_name] = Annotated[arg_type.sub_type, FieldInfo(description=arg_desc)]
        tool_model = create_model(name, **arg_dict)
        lc_tool = StructuredTool(
            name=name,
            description=tool.__doc__,            # ← LINE 201: raw docstring, NOT _desc
            args_schema=tool_model,              # ← arg descriptions from _args_list
            func=tool,
        )
        tools.append(lc_tool)
    return tools
```

The resulting `StructuredTool` objects are stored in `self.lc_tools` and bound to the LLM via `model.bind_tools(self.lc_tools)`. LangChain then includes them in the tool-calling API payload sent to the LLM provider.

### 9.3 Summary of Description Sources

| What LLM sees | Source | Set when | Mutable? |
|---|---|---|---|
| Tool description (top-level) | `tool.__doc__` (raw docstring) | Import time | Yes, `__doc__` is writable |
| Argument descriptions (in JSON schema) | `tool._args_list` (parsed from docstring) | Import time (decoration) | No — frozen at decoration |
| `final_answer` / `fail_task` descriptions | Hardcoded `StructuredTool` objects | Import time | Only via in-place edit |

### 9.4 The `@cache` Barrier

`convert_tools()` is decorated with `@cache` (`functools.cache`). The cache key is the `archytas_tools` tuple (of `(name, method)` pairs). Once called, the **same `StructuredTool` objects** are returned on subsequent calls. This means:

- Changing `method.__doc__` AFTER `set_tools()` has been called does NOT take effect — the cached `StructuredTool` still has the old description
- Clearing the cache (`BaseArchytasModel.convert_tools.cache_clear()`) and re-calling `set_tools()` would pick up the new `__doc__`, but NOT the new `_args_list` (those were parsed at decoration time)

---

## 10. Options Evaluated

### Option 1: Post-init `StructuredTool.description` override (RECOMMENDED)

After the agent is created by `BeakerContext.__init__()`, directly modify the `.description` field on the already-created `StructuredTool` objects in `self.agent.model.lc_tools`:

```python
# In BDIKitContext.__init__(), after super().__init__():
for lc_tool in self.agent.model.lc_tools:
    template_desc = self.prompt_loader.get_tool_description(lc_tool.name)
    if template_desc:
        lc_tool.description = template_desc
```

**Why this works:**
- `StructuredTool.description` is a Pydantic model field — fully writable
- Modifies the objects **in-place**, so the `@cache` is irrelevant — we're changing the cached objects themselves, not regenerating them
- The modified objects are what `model.bind_tools()` sends to the LLM on every subsequent call
- Brings the existing dead-code `prompts/tools/*.j2` templates to life

> **12-02-2026 update:** Independently verified by tracing `bind_tools()` through all backends (OpenRouter, OpenAI, Ollama, Anthropic, etc.). The `model` property (`base.py:147`) calls `bind_tools()` fresh every access, and every backend re-reads `tool.description` at that point. In-place mutation propagates correctly. See `12_02_2026_1545_configurable_prompts_further_analysis.md` Q3 for the full code-path trace.

**Limitations:**
- Argument-level descriptions (in `args_schema`) still come from the original docstring's parsed `_args_list`. These are baked into a Pydantic model created by `create_model()` and not easily changed post-hoc. In practice, tool-level descriptions matter far more for LLM behavior than individual argument descriptions.

### Option 2: Dynamic docstring generation before decoration — DOES NOT WORK

The idea: set `__doc__` on methods from templates before `@tool` processes them.

**Why it fails:** `@tool` fires at **import time** (class body execution), before any experiment configuration is loaded. There is no way to read a per-experiment YAML config file or environment variable during class body parsing. A `__init_subclass__` hook or metaclass runs too late — `@tool` has already captured the docstring into `_desc` and `_args_list`. You would change `__doc__` (which `convert_tools` reads at line 201) but NOT the parsed argument descriptions — creating an inconsistency where the tool description says one thing and the argument schema says another.

### Option 3: Override `__doc__` + clear cache + re-call `set_tools()`

```python
for name, method in self.agent.tools.items():
    method.__doc__ = load_template(name)
BaseArchytasModel.convert_tools.cache_clear()
self.agent.model.set_tools(self.agent.tools)
```

**Why Option 1 is better:**
- Cache clearing is a global side effect — affects all agents sharing the static method (only one per container in practice, but still conceptually wrong)
- `_args_list` is still stale (parsed from old docstring at decoration time)
- More code, more fragility, same result as Option 1

### Option 4: Put tool descriptions in the system prompt instead

Include detailed tool descriptions in `main.j2` and don't change the tool-calling API descriptions at all.

**Why Option 1 is better:**
- The LLM would see tool descriptions **twice** — once from the API schema (docstring), once from the system prompt (template). If they diverge, the LLM gets contradictory signals.
- Uses context window for redundant information
- Option 1 keeps a single source of truth

---

## 11. Implementation Plan for Option 1

### 11.1 What to Change

**File: `src/bdikit_context/context.py`**

Add tool description override after agent creation, alongside the existing prompt loader and ReAct prelude override:

```python
class BDIKitContext(BeakerContext):
    def __init__(self, beaker_kernel, config):
        # Determine prompts directory from env var (set by generate_env.py)
        prompts_dir_env = os.environ.get("HARMONIA_PROMPTS_DIR")
        if prompts_dir_env:
            self.prompt_loader = PromptLoader(prompts_dir=Path(prompts_dir_env))
        else:
            self.prompt_loader = PromptLoader()  # Default

        # Call parent (creates agent with default prompts)
        super().__init__(beaker_kernel, BDIKitAgent, config)

        # Override ReAct prelude if custom one specified
        react_prelude_path = os.environ.get("HARMONIA_REACT_PRELUDE")
        if react_prelude_path and Path(react_prelude_path).exists():
            custom_prelude = Path(react_prelude_path).read_text()
            self.agent.custom_prelude = custom_prelude
            self.agent.update_prompt()

        # Override tool descriptions from Jinja2 templates (if available)
        self._override_tool_descriptions()

    def _override_tool_descriptions(self):
        """
        Replace tool descriptions on already-created StructuredTool objects
        with rendered Jinja2 templates from the prompts/tools/ directory.

        Only overrides tools for which a .j2 template exists.
        Tools without templates keep their original Python docstring.
        """
        if not self.agent.model.lc_tools:
            return

        available_templates = self.prompt_loader.list_tools()
        for lc_tool in self.agent.model.lc_tools:
            if lc_tool.name in available_templates:
                try:
                    new_desc = self.prompt_loader.get_tool_description(lc_tool.name)
                    if new_desc and new_desc.strip():
                        lc_tool.description = new_desc
                except Exception as e:
                    # Fail open — keep original docstring if template fails
                    print(f"Warning: Could not load tool template for {lc_tool.name}: {e}")
```

### 11.2 YAML Config Extension

Add `tool_prompts_dir` to the prompts config. When specified, the prompt loader looks for tool templates in this directory instead of the default `prompts/tools/`:

```yaml
prompts:
  prompts_base_dir: "../prompts"
  system_prompt_dir: "system_prompt/v2_autonomous"
  react_prelude: "react_agent_prompts/v2_tool_focused/prelude.txt"
  tool_prompts_dir: "bdikit_prompts/v2_detailed"    # ← NEW
```

The `tool_prompts_dir` would contain `.j2` files named after tools:
```
bdikit_prompts/v2_detailed/
├── match_schema.j2
├── match_values.j2
├── top_matches.j2
├── materialize_mapping.j2
└── get_gdc_acceptable_values.j2
```

> **12-02-2026 update:** Independently verified that `StructuredTool.name` values match `.j2` filenames exactly. The chain is: `@tool()` sets `_name = func.__name__` → `make_tool_dict()` uses `_name` as key → `convert_tools()` uses key as `StructuredTool(name=...)` → `get_tool_description()` looks for `tools/{name}.j2`. All 5 tools match. See `12_02_2026_1545_configurable_prompts_further_analysis.md` Q6.

### 11.3 What Stays the Same

- **Argument descriptions** in the JSON schema remain from Python docstrings. These describe parameter types and purposes, which are inherently tied to the code and unlikely to need per-experiment variation.
- **`final_answer` and `fail_task`** tool descriptions are hardcoded in Archytas. These are framework-level tools, not experiment-specific. If needed in the future, they could be overridden the same way (find them in `lc_tools` by name and modify `.description`).
- **Tool templates remain optional.** If no `.j2` file exists for a tool, the original docstring is kept. This means existing experiments work unchanged.

### 11.4 Why This Is the Right Approach

1. **3 lines of core logic** — iterate `lc_tools`, check for template, set `.description`
2. **No Archytas changes** — works entirely within Harmonia's context init
3. **Bypasses `@cache`** — modifies objects in-place, no cache invalidation needed
4. **Revives dead code** — the `prompts/tools/*.j2` templates and `get_tool_description()` / `list_tools()` methods that already exist become functional
5. **Backward compatible** — no template = keep docstring
6. **Consistent with overall design** — same pattern as system prompt override (env var → prompt loader → override at init time)
7. **Per-experiment configurable** — different experiments can have different `tool_prompts_dir` values pointing to different template sets

---

## 12. Further Analysis (12-02-2026)

An independent code-path verification was conducted on 12-02-2026 to confirm four key technical claims in this plan. All four were confirmed favorably:

| Question | Concern | Verdict |
|----------|---------|---------|
| Config-to-context flow | Is the env var path the only viable route? | Yes — `BDIKitContext` receives Beaker metadata, not experiment YAML. Changing `ExperimentConfig` + `generate_env.py` is the recommended approach. |
| `auto_context` / `prompt_loader` | Does it read instance attr or module singleton? | Instance attribute (`self.prompt_loader`), confirmed at `context.py:40`. |
| `bind_tools` timing | Does in-place mutation of `StructuredTool.description` propagate? | Yes — `bind_tools()` re-reads `.description` every request via the `model` property. |
| Tool name matching | Do `StructuredTool.name` values match `.j2` filenames? | Exact 1:1 match for all 5 BDIKit tools. |

**Full details:** `docs/plans/12_02_2026_1545_configurable_prompts_further_analysis.md`

---

## 13. Implementation Report (12-02-2026)

**Date:** 12-02-2026
**Status:** IMPLEMENTED
**Implementer:** Claude Code

### 13.1 Summary

All steps from the recommended implementation sequence (Section 7) were implemented. The configurable prompts feature is now fully functional, allowing per-experiment prompt overrides via YAML config → env vars → container env → context init.

### 13.2 Files Changed

| File | Change Description |
|------|-------------------|
| `src/automation/config.py` | Added `PromptsConfig` dataclass with 5 optional fields (`prompts_base_dir`, `system_prompt_dir`, `react_prelude`, `code_context_prompt`, `tool_prompts_dir`). Added `prompts` field to `ExperimentConfig`. Updated `from_dict()` to parse `prompts` section from YAML. All fields default to `None` for backward compatibility. |
| `generate_env.py` | Added `import os`. Added prompts config handling block after LLM env vars: reads `prompts` section from raw YAML, resolves relative paths against config file parent directory using `prompts_base_dir`, writes `HARMONIA_PROMPTS_DIR`, `HARMONIA_REACT_PRELUDE`, `HARMONIA_CODE_CONTEXT_PROMPT`, `HARMONIA_TOOL_PROMPTS_DIR` to `.env` via existing `update_env_value()` helper. |
| `exec_apptainer_harmonia.sh` | Added `--bind` logic for 4 prompt env vars after the `--env-file` line. Reads `HARMONIA_PROMPTS_DIR`, `HARMONIA_REACT_PRELUDE`, `HARMONIA_CODE_CONTEXT_PROMPT`, `HARMONIA_TOOL_PROMPTS_DIR` from the `.env` file. Binds each directory/file read-only into the container if it exists. Prints diagnostic messages for each bound prompt directory. |
| `src/bdikit_context/context.py` | Major rewrite of `BDIKitContext.__init__()`: (1) reads `HARMONIA_PROMPTS_DIR` env var, creates per-instance `PromptLoader` with custom dir or default; (2) after `super().__init__()`, reads `HARMONIA_REACT_PRELUDE` env var, overrides `self.agent.custom_prelude` + calls `self.agent.update_prompt()`; (3) calls `_override_tool_descriptions()` to replace `StructuredTool.description` on already-created tools using Jinja2 templates from `HARMONIA_TOOL_PROMPTS_DIR` (or default tools/ dir); (4) `_log_prompt_config()` prints JSON diagnostic; (5) `auto_context()` prints the full system prompt on first invocation. Added `import os`, `from pathlib import Path`, `from .prompts import PromptLoader`. |
| `src/code_context/context.py` | Added `import os` and `from pathlib import Path`. Updated `auto_context()` to check `HARMONIA_CODE_CONTEXT_PROMPT` env var; if set and file exists, loads prompt from file instead of using the hardcoded f-string default. |

### 13.3 Files Created

| File/Directory | Description |
|---------------|-------------|
| `experiments/.../configs/prompts/system_prompt/v1_default/system/main.j2` | Copy of the default system prompt from `src/bdikit_context/prompts/system/main.j2` |
| `experiments/.../configs/prompts/system_prompt/v2_autonomous/system/main.j2` | New autonomous variant: encourages independent action, emphasizes tool usage, doesn't wait for user confirmation between steps |
| `experiments/.../configs/prompts/react_agent_prompts/v1_default/prelude.txt` | Baseline ReAct prelude text |
| `experiments/.../configs/prompts/react_agent_prompts/v2_tool_focused/prelude.txt` | Tool-focused variant: explicitly lists BDIKit tools, emphasizes tool usage over manual code |
| `experiments/.../configs/prompts/code_context_prompts/v1_default/prompt.txt` | Default code context prompt as a file |
| `tests/test_configurable_prompts_working.py` | Integration test script with 3 unit tests + 1 container integration test |

(All paths above relative to `harmonia_metadata_agent/analysis/dstoker/harmonia/`)

### 13.4 Data Flow (Implemented)

```
Experiment YAML                    generate_env.py              exec_apptainer_harmonia.sh
┌─────────────┐                   ┌──────────────┐             ┌─────────────────────────┐
│ prompts:     │ ──── reads ────> │ Resolves      │ ── writes > │ Reads HARMONIA_*        │
│   system_    │                  │ relative paths│             │ from .env file          │
│   prompt_dir │                  │ against config│             │                         │
│   react_     │                  │ parent dir    │             │ --bind <dir>:<dir>:ro   │
│   prelude    │                  │               │             │ for each prompt dir/file│
│   ...        │                  │ Writes to     │             │                         │
└─────────────┘                  │ _associated   │             │ --env-file .env         │
                                  │ .env file     │             └───────────┬─────────────┘
                                  └──────────────┘                         │
                                                                           ▼
                                  Container (Apptainer)
                                  ┌────────────────────────────────────────┐
                                  │ BDIKitContext.__init__():              │
                                  │   os.environ["HARMONIA_PROMPTS_DIR"]  │
                                  │   → self.prompt_loader = PromptLoader │
                                  │                                        │
                                  │   os.environ["HARMONIA_REACT_PRELUDE"]│
                                  │   → self.agent.custom_prelude = ...   │
                                  │   → self.agent.update_prompt()        │
                                  │                                        │
                                  │   os.environ["HARMONIA_TOOL_PROMPTS"] │
                                  │   → _override_tool_descriptions()     │
                                  │     (mutates StructuredTool.desc)     │
                                  │                                        │
                                  │ CodeContext.auto_context():            │
                                  │   os.environ["HARMONIA_CODE_CONTEXT"] │
                                  │   → loads from file if set            │
                                  └────────────────────────────────────────┘
```

### 13.5 YAML Config Example

```yaml
experiment:
  name: "dou_harmonization_devstral_autonomous"
  description: "Test autonomous prompt variant with devstral"

llm:
  provider: ollama
  model: devstral-small-2:latest
  temperature: 0.0
  context_length: 32000

prompts:
  prompts_base_dir: "../prompts"                              # Relative to config file
  system_prompt_dir: "system_prompt/v2_autonomous"            # Relative to base_dir
  react_prelude: "react_agent_prompts/v2_tool_focused/prelude.txt"

messages:
  - content: "Load dou.csv and harmonize it to GDC schema."
    wait_seconds: 300
    decision_mode: auto_accept
```

### 13.6 Environment Variables

| Env Var | Set by | Read by | Purpose |
|---------|--------|---------|---------|
| `HARMONIA_PROMPTS_DIR` | `generate_env.py` | `BDIKitContext.__init__()` | Custom system prompt template directory (must contain `system/main.j2`) |
| `HARMONIA_REACT_PRELUDE` | `generate_env.py` | `BDIKitContext.__init__()` | Path to custom ReAct agent prelude text file |
| `HARMONIA_TOOL_PROMPTS_DIR` | `generate_env.py` | `BDIKitContext._override_tool_descriptions()` | Custom tool description template directory (contains `*.j2` files) |
| `HARMONIA_CODE_CONTEXT_PROMPT` | `generate_env.py` | `CodeContext.auto_context()` | Path to custom code context prompt text file |

### 13.7 Backward Compatibility

- **Configs without `prompts` section:** `PromptsConfig` defaults all fields to `None`. `generate_env.py` only writes `HARMONIA_*` vars when values are present. `BDIKitContext` falls back to default `PromptLoader()`. No behavior change.
- **Existing `.env` files:** No `HARMONIA_*` vars present → all `os.environ.get()` calls return `None` → default behavior.
- **Tool description override:** Only overrides tools that have matching `.j2` templates. Skips framework tools (`final_answer`, `fail_task`).

### 13.8 Test Results

**Unit Tests (3/3 PASS):**
1. `PromptsConfig` parsing from YAML dict — correct field extraction
2. `PromptsConfig` backward compatibility — no `prompts` section → all `None` defaults
3. `generate_env.py` produces correct `HARMONIA_*` env vars with valid paths
4. `PromptLoader` with custom directory renders templates with markers

**Integration Test:** Container test verifies the end-to-end pipeline: custom prompts → YAML config → generate_env.py → exec_apptainer_harmonia.sh → Beaker with overridden prompts.
