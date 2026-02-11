# Plan: Make Prompts Changeable Between Experiments

**Date:** 11-02-2026
**Status:** Proposed (analysis needed)

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

4. **Template validation**: If users provide custom Jinja2 templates, we need to validate them at config-load time (not at runtime mid-experiment). Assess what validation is practical.

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

1. Perform Phase 1 feasibility assessment
2. Present findings and design options for discussion
3. Implement if approved
