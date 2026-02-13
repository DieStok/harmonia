# Further Analysis: Configurable Prompts Implementation

**Date:** 12-02-2026
**Analyst:** Claude Code (code-path verification)
**Context:** Follow-up to `11_02_2026_1450_plan_to_make_prompts_changeable.md`

## Preamble

The original plan (11-02-2026) proposed making prompts configurable per-experiment via environment variables injected into the Apptainer container. That plan included a feasibility analysis with 17 container tests confirming the approach is viable.

This follow-up analysis was conducted to **independently verify four specific technical claims** in that plan before committing to implementation. The questions arose from reading the plan critically:

1. **Q1 (Config-to-context flow):** Is the env var path truly the only viable injection route, or could we pass prompt config through the `config` dict that `BDIKitContext` already receives? And is it feasible to change both `ExperimentConfig` and `generate_env.py` to create a clean end-to-end path?
2. **Q2 (auto_context / prompt_loader timing):** Does `auto_context()` actually read from `self.prompt_loader` (the instance attribute), or from the module-level singleton? If the latter, the plan's core mechanism wouldn't work.
3. **Q3 (bind_tools timing):** When tool descriptions are sent to the LLM, does `bind_tools()` serialize them eagerly (once at init) or read them fresh per request? If eager, mutating `StructuredTool.description` post-init (the plan's Option 1) would have no effect.
4. **Q6 (Tool name matching):** Do `StructuredTool.name` values match the `.j2` template filenames that `PromptLoader.get_tool_description()` expects? A mismatch would silently break tool description overrides.

---

## Q1: Config-to-Context Flow

### Hypothesis

The original plan stated that environment variables are "the cleanest injection point." The question was: is this because the `config` dict inside `BDIKitContext` doesn't carry the full experiment YAML, or is it a design preference? And can we make the flow cleaner by changing `ExperimentConfig` and `generate_env.py`?

### What we found

**The `config` dict inside BDIKitContext is NOT the experiment YAML.** We traced the full data flow:

1. **`ExperimentConfig.from_dict()`** (`src/automation/config.py:73-134`) extracts only known sections: `experiment`, `llm`, `messages`, `output`, `decision_handling`, `evaluation`. A hypothetical `prompts` section in the YAML would be **silently dropped** — there is no `prompts` field in `ExperimentConfig` and no code to parse it.

2. **`generate_env.py:91-149`** (`generate_env_from_config()`) reads the raw YAML dict (not the parsed `ExperimentConfig`), but only extracts `config["llm"]` and `config["env_settings"]`. It writes LLM-related env vars to the `.env` file. Non-LLM sections are ignored.

3. **`exec_apptainer_harmonia.sh`** passes the `.env` file into the container via `--env-file`. The original YAML file is **never bound into the container**.

4. **`BDIKitContext.__init__()` (`src/bdikit_context/context.py:22`)** receives a `config` dict from Beaker's internal context registry. This is Beaker's per-context metadata — **not** the experiment YAML. The experiment YAML is consumed by `generate_env.py` and `run_experiment.py` on the host side; it never enters the container.

### Key code evidence

| File | Line(s) | What it shows |
|------|---------|---------------|
| `src/automation/config.py` | 73-80 | `from_dict()` only parses known sections; `prompts` would be dropped |
| `generate_env.py` | 108-136 | Only reads `config["llm"]` and `config["env_settings"]` |
| `generate_env.py` | 34-45 | `update_env_value()` — the mechanism for adding new env vars to `.env` |
| `src/bdikit_context/context.py` | 22-24 | `BDIKitContext.__init__` receives Beaker config, not experiment YAML |

### Feasibility of changing ExperimentConfig + generate_env.py

**Fully feasible.** The required changes follow the existing patterns exactly:

**In `config.py`:** Add a `PromptsConfig` dataclass (same pattern as `LLMConfig`, `OutputConfig`, etc.) with all-`Optional` fields defaulting to `None`. Add parsing in `from_dict()`:

```python
@dataclass
class PromptsConfig:
    prompts_base_dir: Optional[str] = None
    system_prompt_dir: Optional[str] = None
    react_prelude: Optional[str] = None
    code_context_prompt: Optional[str] = None
    tool_prompts_dir: Optional[str] = None
```

In `from_dict()` (after line 80):
```python
prompts_data = data.get("prompts", {})
```

In the `cls()` constructor call (after line 133):
```python
prompts=PromptsConfig(**prompts_data) if prompts_data else PromptsConfig(),
```

**In `generate_env.py`:** Add a block after the LLM env vars (after line 136) that reads `config.get("prompts", {})`, resolves relative paths against `config_path.parent`, and writes `HARMONIA_PROMPTS_DIR`, `HARMONIA_REACT_PRELUDE`, `HARMONIA_CODE_CONTEXT_PROMPT`, and `HARMONIA_TOOL_PROMPTS_DIR` using the existing `update_env_value()` helper. Path resolution uses `(config_path.parent / base_dir / relative_path).resolve()` — the `config_path` is already available as a parameter to `generate_env_from_config()`.

**Why this is the right approach:**
- Single source of truth: prompt paths live in the experiment YAML alongside LLM config, messages, etc.
- Same pattern as LLM config: `YAML -> dataclass -> generate_env -> .env -> container env vars -> context reads os.environ`
- No new coupling: `BDIKitContext` still only reads env vars — it doesn't need to parse YAML
- Backward compatible: `PromptsConfig` with all-`None` defaults means old configs work unchanged; `generate_env.py` only writes prompt env vars when values are present

### Conclusion

Env vars are not just a preference — they are **the only channel** that currently bridges experiment config to the container interior. Changing `ExperimentConfig` + `generate_env.py` is the clean, comprehensive way to extend this channel for prompt config. The changes are additive and follow existing patterns.

---

## Q2: auto_context / prompt_loader Timing

### Hypothesis

The plan proposes setting `self.prompt_loader` to a custom `PromptLoader` instance in `BDIKitContext.__init__()`. The concern was: does `auto_context()` (renamed to `_auto_context` by the `__init_subclass__` hook) actually read from `self.prompt_loader`, or does it call the module-level `get_prompt_loader()` singleton? If the latter, the per-instance override wouldn't take effect.

### What we found

**`auto_context()` uses `self.prompt_loader` — the instance attribute.** The code is unambiguous:

```python
# src/bdikit_context/context.py, lines 22-43
class BDIKitContext(BeakerContext):
    def __init__(self, beaker_kernel, config):
        super().__init__(beaker_kernel, BDIKitAgent, config)
        self.prompt_loader = get_prompt_loader()   # line 24: stores on instance

    async def auto_context(self):                  # line 29
        tools = [...]                              # lines 32-38
        return self.prompt_loader.get_system_prompt(  # line 40: reads from instance
            tools=tools,
            suppress_output=True,
        )
```

The `__init_subclass__` renaming (stores `auto_context` as `_auto_context`) does **not** affect this — `self.prompt_loader` is an instance attribute, not a class attribute, so the renamed method still accesses it correctly via `self`.

Additionally, since `auto_context()` is called **every turn** (not during init), even setting `self.prompt_loader` after `super().__init__()` would take effect from the very first LLM interaction.

### Key code evidence

| File | Line(s) | What it shows |
|------|---------|---------------|
| `src/bdikit_context/context.py` | 24 | `self.prompt_loader = get_prompt_loader()` — stored on instance |
| `src/bdikit_context/context.py` | 40 | `self.prompt_loader.get_system_prompt(...)` — read from instance |
| `src/bdikit_context/prompts/__init__.py` | 59-64 | `get_prompt_loader()` returns singleton, but result is stored per-instance |

### Conclusion

The plan's approach of setting `self.prompt_loader = PromptLoader(custom_dir)` works correctly. The instance attribute is what `auto_context()` reads, regardless of the module-level singleton. No container test was needed — the code path is clear.

---

## Q3: bind_tools Timing and Tool Description Mutation

### Hypothesis

The plan's Option 1 proposes mutating `StructuredTool.description` in-place after agent creation to override tool descriptions. The concern was: if `bind_tools()` eagerly serializes tool schemas at init time (caching a dict/JSON copy), then mutating `.description` afterward would have no effect — the LLM would still see the old descriptions.

### What we found

**Option 1 works correctly** because `bind_tools()` is called fresh before every LLM request, not just once at init.

The critical code path:

1. **`BaseArchytasModel.model` property** (`archytas/models/base.py:147-151`):
   ```python
   @property
   def model(self):
       if self.lc_tools is not None:
           return self._model.bind_tools(self.lc_tools)  # Called EVERY access
       return self._model
   ```
   This property is accessed before every LLM request. It calls `bind_tools()` each time, passing the **same `self.lc_tools` list** (containing the same `StructuredTool` objects we mutated).

2. **For LangChain-based backends** (OpenAI, Ollama, Anthropic, Groq, Gemini, Bedrock): `bind_tools()` calls `convert_to_openai_tool(tool)` for each tool, which calls `_format_tool_to_openai_function(tool)` (`langchain_core/utils/function_calling.py:314-358`), which reads `tool.description` at call time:
   ```python
   def _format_tool_to_openai_function(tool: BaseTool) -> FunctionDescription:
       if tool.tool_call_schema and not is_simple_oai_tool:
           return _convert_pydantic_to_openai_function(
               tool.tool_call_schema, name=tool.name, description=tool.description  # line 336
           )
   ```

3. **For the OpenRouter backend** (`archytas/models/openrouter.py:48-67`): `bind_tools()` iterates tools and reads `tool.description` directly:
   ```python
   def bind_tools(self, tools):
       self._schemas = []
       for tool in tools:
           schema = {
               'type': 'function',
               'function': {
                   'name': tool.name,
                   'description': tool.description,   # line 57: read at bind time
                   ...
               },
           }
           self._schemas.append(schema)
   ```
   Even though OpenRouter caches into `self._schemas`, the `model` property re-calls `bind_tools()` on every access, so the cache is rebuilt each time with the current `.description` values.

### What about the `@cache` on `convert_tools()`?

The `@cache` decorator on `convert_tools()` (`base.py:189`) means the `StructuredTool` objects are created only once. But this is actually helpful — it means `self.lc_tools` always contains the **same objects** we mutated. When `bind_tools()` reads `.description` from those objects, it gets our mutated values.

### Key code evidence

| File | Line(s) | What it shows |
|------|---------|---------------|
| `archytas/models/base.py` | 147-151 | `model` property calls `bind_tools()` every access |
| `archytas/models/base.py` | 188-206 | `convert_tools()` creates `StructuredTool` objects (cached, but mutable) |
| `archytas/models/openrouter.py` | 48-67 | OpenRouter `bind_tools()` reads `tool.description` at call time |
| `langchain_core/utils/function_calling.py` | 314-337 | LangChain `_format_tool_to_openai_function()` reads `tool.description` |
| `langchain_openai/chat_models/base.py` | 1819-1861 | OpenAI `bind_tools()` calls `convert_to_openai_tool()` per tool |
| `langchain_ollama/chat_models.py` | 1230-1251 | Ollama `bind_tools()` calls `convert_to_openai_tool()` per tool |

### What the existing tests covered

The tests in `tests/test_prompt_feasibility.py` and `tests/test_prompt_integration.py` did **not** cover bind_tools timing. Test 10 confirmed tool `.j2` templates are dead code, and test 15 confirmed the post-init override pattern is viable for the ReAct prelude. But no test exercised the specific question of whether mutated `StructuredTool.description` values propagate through `bind_tools()` to the LLM. This analysis fills that gap by tracing the code paths directly.

### Conclusion

The plan's Option 1 is sound. Mutating `StructuredTool.description` after agent creation **does** propagate to the LLM because:
- `bind_tools()` is called fresh before every request (via the `model` property)
- `bind_tools()` re-reads `tool.description` from the live object each time
- The `@cache` on `convert_tools()` preserves the same mutable objects we modified

---

## Q6: Tool Name Matching Between StructuredTool and .j2 Templates

### Hypothesis

The plan's `_override_tool_descriptions()` method iterates `self.agent.model.lc_tools` and looks up each `lc_tool.name` in the template directory. If `StructuredTool.name` doesn't match the `.j2` filename convention that `PromptLoader.get_tool_description()` expects, overrides would silently fail.

### What we found

**The names match exactly.** The chain is:

1. **`@tool()` decorator** (`archytas/tool_utils.py:120`): Sets `func._name = name if name else func.__name__`. In `agent.py`, all `@tool()` calls use no `name` argument, so `_name` = the Python method name: `match_schema`, `top_matches`, `match_values`, `materialize_mapping`, `get_gdc_acceptable_values`.

2. **`make_tool_dict()`** (`archytas/tool_utils.py:468-479`): For class methods, uses `method._name` as the dict key. Since none of the tool names collide, the `{cls_name}__{method_name}` fallback is never triggered.

3. **`convert_tools()`** (`archytas/models/base.py:192-200`): Creates `StructuredTool(name=name, ...)` where `name` comes from the dict key — the Python method name.

4. **`PromptLoader.get_tool_description(tool_name)`** (`src/bdikit_context/prompts/__init__.py:39-45`): Looks for `tools/{tool_name}.j2`.

5. **Existing `.j2` files** in `src/bdikit_context/prompts/tools/`:
   - `match_schema.j2`
   - `top_matches.j2`
   - `match_values.j2`
   - `materialize_mapping.j2`
   - `get_gdc_acceptable_values.j2`

These are a 1:1 match with the Python method names.

### Key code evidence

| File | Line(s) | What it shows |
|------|---------|---------------|
| `archytas/tool_utils.py` | 120 | `func._name = name if name else func.__name__` |
| `archytas/tool_utils.py` | 468-479 | `make_tool_dict()` uses `method._name` as dict key |
| `archytas/models/base.py` | 192, 199-200 | `StructuredTool(name=name, ...)` where `name` = dict key |
| `src/bdikit_context/agent.py` | 29, 84, 130, 191, 285 | All `@tool()` decorators — no custom `name` argument |
| `src/bdikit_context/prompts/__init__.py` | 42 | `get_tool_description()` looks for `tools/{tool_name}.j2` |
| `src/bdikit_context/prompts/tools/` | (directory) | 5 `.j2` files matching the 5 Python method names |

### Edge cases

- **`final_answer` and `fail_task`**: These framework tools (added by `convert_tools()` at line 191) have no `.j2` templates. The plan handles this correctly — `_override_tool_descriptions()` only overrides tools for which `lc_tool.name in available_templates`.
- **Custom `@tool(name="...")`**: If someone later adds a tool with a custom name argument, the `StructuredTool.name` would differ from the Python method name. The `.j2` file would need to match the custom name. This is an unlikely edge case but worth documenting.

### What the existing tests covered

The tests confirmed that tool `.j2` templates are dead code (test 10) but did **not** verify the name matching chain from `@tool` decorator through `make_tool_dict()` to `StructuredTool.name` to `get_tool_description()`. This analysis fills that gap.

### Conclusion

Tool names match `.j2` filenames exactly. The `_override_tool_descriptions()` method will correctly find and apply templates for all 5 BDIKit tools, and correctly skip framework tools (`final_answer`, `fail_task`) that have no templates.

---

## Overall Conclusion

All four technical concerns are resolved favorably:

| Question | Concern | Verdict |
|----------|---------|---------|
| Q1 | Config-to-context flow | Env vars are the only channel; changing `ExperimentConfig` + `generate_env.py` is feasible, clean, and recommended |
| Q2 | `auto_context` / `prompt_loader` timing | `self.prompt_loader` on the instance works correctly |
| Q3 | `bind_tools` eagerly caches? | No — called fresh per request; in-place mutation propagates |
| Q6 | Tool names match `.j2` filenames? | Yes, exact 1:1 match for all 5 tools |

The implementation plan from 11-02-2026 is confirmed sound. No design changes needed.

---

## Implementation Status (12-02-2026)

**The plan has been implemented.** All changes described in the original plan and confirmed by this analysis have been coded and tested. See Section 13 of `11_02_2026_1450_plan_to_make_prompts_changeable.md` for the full implementation report with file-by-file details.
