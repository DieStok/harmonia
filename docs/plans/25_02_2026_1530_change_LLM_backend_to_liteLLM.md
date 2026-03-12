# Plan: Switch Top-Level Agent LLM Backend from any-llm to liteLLM

**Date:** 25 February 2026
**Status:** Ready for implementation (execute AFTER bdi-kit upgrade plan is complete)
**Prerequisite:** `25_02_2026_1527_update_bdikit_and_add_proper_LLM_selection_for_schema_and_value_matching_tools.md`

## 1. Problem Statement

Harmonia currently uses two different LLM abstraction libraries simultaneously:

| Layer | Library | Purpose |
|---|---|---|
| **Top-level agent** (Beaker/Archytas reasoning) | **any-llm-sdk** | The AI agent that interprets user requests, calls tools, generates responses |
| **bdi-kit internal** (schema/value matching) | **litellm** | LLM calls within bdi-kit's `method="llm"`, `magneto_*_llm`, etc. |

This creates unnecessary complexity:
- Two LLM libraries in the same container with overlapping functionality
- Different model naming conventions and error handling
- any-llm has a rough token counting estimate (4 chars per token) vs litellm's model-specific counters
- Extra dependency (`any-llm-sdk`) that could be removed
- Debugging is harder when two different libraries make LLM calls

After the bdi-kit upgrade to v0.9, litellm is already a required dependency. Switching the top-level agent to litellm too would unify the LLM stack.

## 2. Goals

1. Replace `any-llm-sdk` with `litellm` as the top-level agent's LLM backend
2. Remove `any-llm-sdk` from dependencies
3. Maintain full compatibility with all existing providers (Ollama, OpenRouter, OpenAI, Anthropic, etc.)
4. Maintain full compatibility with Beaker/Archytas agent framework interface
5. Improve token counting accuracy

## 3. Scope Assessment

### What needs to change

any-llm-sdk is used in **exactly 2 source files:**

| File | Lines | Classes/Functions |
|---|---|---|
| `src/bdikit_context/llm/anyllm.py` (443 lines) | All | `ChatAnyLLM`, `AnyLLMModel`, helper functions |
| `src/bdikit_context/llm/direct.py` (263 lines) | All | `DirectLLMRunner`, `DirectLLMConfig`, `DirectLLMResult`, convenience functions |

Plus references in:
| File | Type of Change |
|---|---|
| `src/bdikit_context/llm/__init__.py` | Update provider import map (point to new litellm module) |
| `pyproject.toml` | Remove `any-llm-sdk`, add explicit `litellm` dep |
| `harmonia_beaker_LLM_agent_environment_apptainer.def` | Remove `any-llm-sdk` install step |
| `build_harmonia_apptainer.sh` | Remove any-llm verification steps |

### What does NOT need to change

- `src/bdikit_context/agent.py` — tools/agent logic unchanged
- `src/bdikit_context/context.py` — context setup unchanged
- `src/bdikit_context/config/` — config classes unchanged
- `src/bdikit_context/procedures/` — procedure templates unchanged
- `src/bdikit_context/prompts/` — prompt templates unchanged
- `generate_env.py` — env generation unchanged
- `exec_apptainer_harmonia.sh` — env passing unchanged
- All experiment YAML configs — unchanged
- bdi-kit itself — already uses litellm internally

## 4. Architecture: Before and After

### Before (current)
```
User Request
    ↓
Beaker Kernel → BDIKitContext → BDIKitAgent
    ↓
AnyLLMModel (archytas.models.base.BaseArchytasModel)
    ↓
ChatAnyLLM (LangChain-like adapter)
    ↓
AnyLLM.create(provider) → any_llm.AnyLLM client
    ↓
Provider SDK (e.g., openai, ollama, anthropic)
```

### After (target)
```
User Request
    ↓
Beaker Kernel → BDIKitContext → BDIKitAgent
    ↓
LiteLLMModel (archytas.models.base.BaseArchytasModel)
    ↓
ChatLiteLLM (LangChain-like adapter)
    ↓
litellm.acompletion(model="provider/model", ...)
    ↓
Provider API (e.g., OpenAI, Ollama, Anthropic)
```

## 5. Detailed Implementation

### Step 1: Create `src/bdikit_context/llm/litellm_model.py`

This replaces `anyllm.py`. It provides two classes that satisfy the same interfaces:

#### 5.1.1 `ChatLiteLLM` — replaces `ChatAnyLLM`

The class must implement the interface expected by Archytas:
- `__init__(provider, model, api_key, api_base, temperature, max_tokens)`
- `bind_tools(tools) -> self` — converts LangChain StructuredTools to OpenAI tool schemas
- `invoke(messages) -> AIMessage` — sync completion
- `ainvoke(messages) -> AIMessage` — async completion
- `get_num_tokens_from_messages(messages, tools) -> int` — token estimation

Key differences from `ChatAnyLLM`:

| Aspect | ChatAnyLLM (any-llm) | ChatLiteLLM (litellm) |
|---|---|---|
| Client creation | `AnyLLM.create(provider, api_key=..., api_base=...)` | No client object; `litellm.acompletion()` is stateless |
| Model string format | Separate `provider` and `model` params | Single `model` string: `"provider/model"` (e.g., `"ollama/devstral:latest"`) |
| Completion call | `client.acompletion(model=..., messages=..., tools=..., stream=False)` | `litellm.acompletion(model=..., messages=..., tools=..., stream=False)` |
| Response type | `any_llm.types.completion.ChatCompletion` | `litellm.ModelResponse` (OpenAI-compatible) |
| Tool call format | `tc.function.name`, `tc.function.arguments` | Same (OpenAI format) |
| Token counting | Manual ~4 chars/token estimate | `litellm.token_counter(model, messages)` |
| API key passing | Constructor param → SDK client | `api_key` kwarg to `acompletion()` or env var |
| Base URL passing | Constructor param → SDK client | `api_base` kwarg to `acompletion()` |

**Implementation notes:**

```python
import litellm
from litellm import acompletion, token_counter

class ChatLiteLLM:
    def __init__(self, *, provider, model, api_key=None, api_base=None, temperature=0.0, max_tokens=4096):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._tool_schemas = None

        # Construct litellm model string
        # litellm uses "provider/model" format, e.g., "ollama/devstral:latest"
        # For Ollama: "ollama/model" or "ollama_chat/model"
        # For OpenAI: "openai/gpt-4o" or just "gpt-4o"
        # For OpenRouter: "openrouter/model"
        self._litellm_model = self._build_model_string()

    def _build_model_string(self):
        """Build litellm model string from provider + model."""
        # litellm model format: https://docs.litellm.ai/docs/providers
        # Special cases:
        if self.provider == "ollama":
            return f"ollama_chat/{self.model}"
        elif self.provider == "openrouter":
            return f"openrouter/{self.model}"
        elif self.provider == "openai":
            return self.model  # OpenAI models don't need prefix
        elif self.provider == "anthropic":
            return f"anthropic/{self.model}"
        else:
            return f"{self.provider}/{self.model}"

    async def ainvoke(self, input, *args, **kwargs):
        messages = self._convert_messages(input)
        response = await acompletion(
            model=self._litellm_model,
            messages=messages,
            tools=self._tool_schemas,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            api_key=self.api_key,
            api_base=self.api_base,
            stream=False,
        )
        return self._convert_response(response)

    def get_num_tokens_from_messages(self, *, messages, tools=None):
        """Use litellm's model-specific token counter."""
        try:
            converted = self._convert_messages(messages)
            return token_counter(model=self._litellm_model, messages=converted)
        except Exception:
            # Fallback: rough estimate
            total_chars = sum(len(m.content) if isinstance(m.content, str) else 0 for m in messages)
            return total_chars // 4
```

The `_convert_messages()` and `_convert_response()` methods are **nearly identical** to the existing `ChatAnyLLM` versions, since both any-llm and litellm use OpenAI-compatible message and response formats.

The `bind_tools()` method is **identical** — same OpenAI tool schema format.

#### 5.1.2 `LiteLLMModel` — replaces `AnyLLMModel`

Same Archytas `BaseArchytasModel` interface:
- `auth(**kwargs)` — reads provider, api_key, api_base from config/env
- `initialize_model(**kwargs) -> ChatLiteLLM` — creates the chat model
- `get_num_tokens_from_messages(messages, tools) -> int`
- `contextsize(model_name) -> int`

The `auth()` method is **identical** to `AnyLLMModel.auth()` — same env vars, same logic.

The `initialize_model()` method returns `ChatLiteLLM(...)` instead of `ChatAnyLLM(...)`.

The `contextsize()` method can use `litellm.get_max_tokens(model)` instead of the hardcoded `CONTEXT_SIZES` dict:

```python
def contextsize(self, model_name=None):
    name = model_name or self.model_name or ""
    try:
        return litellm.get_max_tokens(self._litellm_model)
    except Exception:
        return 128000  # fallback
```

### Step 2: Create `src/bdikit_context/llm/litellm_direct.py`

This replaces `direct.py`. The `DirectLLMRunner` class is simpler — it's a standalone LLM caller without Beaker/Archytas. Replace the `AnyLLM.create()` client with direct `litellm.acompletion()` calls.

```python
import litellm

class DirectLiteLLMRunner:
    def __init__(self, provider, model, api_key=None, api_base=None, ...):
        self.config = DirectLLMConfig(provider=provider, model=model, ...)
        # No client to create — litellm is stateless

    async def complete(self, prompt, conversation_history=None, **kwargs):
        messages = self._build_messages(prompt, conversation_history)
        litellm_model = self._build_model_string()
        response = await litellm.acompletion(
            model=litellm_model,
            messages=messages,
            api_key=self.config.api_key,
            api_base=self.config.api_base,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        # ... extract content, usage, etc. from response
```

### Step 3: Update `src/bdikit_context/llm/__init__.py`

#### 3a. Update provider import map

Change all import paths from `AnyLLMModel` to `LiteLLMModel`:

```python
PROVIDER_IMPORT_MAP = {
    # Native Archytas providers (legacy — keep for backwards compatibility)
    "openai": "archytas.models.openai.OpenAIModel",
    "ollama": "archytas.models.ollama.OllamaModel",
    ...

    # litellm unified providers (replaces anyllm)
    "litellm": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:openai": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:ollama": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:anthropic": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:openrouter": "bdikit_context.llm.litellm_model.LiteLLMModel",
    ...

    # Backwards compatibility: anyllm: prefix still works (maps to litellm)
    "anyllm": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:openai": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:ollama": "bdikit_context.llm.litellm_model.LiteLLMModel",
    ...
}
```

#### 3b. Update `configure_llm_environment()`

Change the `anyllm:` prefix handling to also accept `litellm:` prefix:

```python
def configure_llm_environment():
    config = get_config()
    llm = config.llm
    provider_key = llm.provider.lower()

    # Handle litellm: or anyllm: prefixed providers
    if provider_key.startswith("litellm:") or provider_key.startswith("anyllm:"):
        actual_provider = provider_key.split(":", 1)[1]
        os.environ["LLM_SERVICE_PROVIDER"] = actual_provider
        import_path = PROVIDER_IMPORT_MAP.get(provider_key) or PROVIDER_IMPORT_MAP.get("litellm")
    elif provider_key in ("litellm", "anyllm"):
        actual_provider = os.getenv("LLM_SERVICE_PROVIDER", "openai")
        import_path = PROVIDER_IMPORT_MAP.get("litellm")
    else:
        actual_provider = provider_key
        import_path = PROVIDER_IMPORT_MAP.get(provider_key)
    ...
```

### Step 4: Update `pyproject.toml`

**Remove** `any-llm-sdk` from dependencies and optional dependencies:

```toml
dependencies = [
  "beaker_kernel>=1.14.0",
  "bdi-kit @ git+https://github.com/VIDA-NYU/bdi-kit.git@v0.9.0",
  "jinja2>=3.0",
  "litellm",  # Replaces any-llm-sdk (also required by bdi-kit v0.9)
]

# Remove all anyllm-* optional dependency groups:
# [project.optional-dependencies]
# anyllm-ollama = ...   <-- DELETE
# anyllm-openai = ...   <-- DELETE
# etc.
```

### Step 5: Update `harmonia_beaker_LLM_agent_environment_apptainer.def`

#### 5a. Remove the any-llm-sdk installation section (lines 89-98):
```
# DELETE these lines:
echo "Installing any-llm-sdk with ollama provider..."
TMPDIR=/var/tmp uv pip install --system --no-cache "any-llm-sdk[ollama] @ git+https://github.com/mozilla-ai/any-llm.git"
echo "=== Verifying any-llm installation ==="
python3 -c "from any_llm import AnyLLM; print('any_llm imported successfully')"
python3 -c "import ollama; print('ollama package imported successfully')"
```

#### 5b. Update verification steps (lines 117-126):
Replace any-llm verification with litellm verification:
```
echo "=== Verifying litellm installation ==="
python3 -c "import litellm; print(f'litellm {litellm.__version__} imported successfully')"

echo "=== Verifying bdikit_context litellm integration ==="
python3 -c "from bdikit_context.llm.litellm_model import LiteLLMModel; print('LiteLLMModel imported successfully')"
python3 -c "from bdikit_context.llm.litellm_model import ChatLiteLLM; print('ChatLiteLLM imported successfully')"
```

#### 5c. Update the installed packages check (line 170):
Replace `any-llm-sdk` with `litellm` in the package list.

### Step 6: Update `build_harmonia_apptainer.sh`

Replace any-llm verification in Phase 5 and Phase 7:

```bash
# Phase 5: Verify sandbox
apptainer exec $SANDBOX_DIR python3 -c "from bdikit_context.llm.litellm_model import LiteLLMModel; print('LiteLLMModel: OK')" || echo "FAILED: LiteLLMModel import"
apptainer exec $SANDBOX_DIR python3 -c "import litellm; print('litellm: OK')" || echo "FAILED: litellm import"

# Phase 7: Final verification
apptainer exec $SIF_FILE python -c "from bdikit_context.llm.litellm_model import LiteLLMModel; print('LiteLLMModel import: OK')"
apptainer exec $SIF_FILE python -c "import litellm; print('litellm import: OK')"
```

### Step 7: Update `generate_env.py`

Update `get_provider_import_path()` to point to the new litellm module:

```python
provider_map = {
    'openai': 'archytas.models.openai.OpenAIModel',
    'openrouter': 'archytas.models.openrouter.OpenRouterModel',
    ...
    # litellm providers (replaces anyllm)
    'litellm:openrouter': 'bdikit_context.llm.litellm_model.LiteLLMModel',
    'litellm:ollama': 'bdikit_context.llm.litellm_model.LiteLLMModel',
    ...
    # Backwards compatibility
    'anyllm:openrouter': 'bdikit_context.llm.litellm_model.LiteLLMModel',
    'anyllm:ollama': 'bdikit_context.llm.litellm_model.LiteLLMModel',
    ...
}
```

### Step 8: Optionally update experiment YAML configs

Existing configs using `provider: anyllm:ollama` will continue to work via backwards compatibility mapping. For new configs, prefer the `litellm:` prefix:

```yaml
llm:
  provider: litellm:ollama    # or still anyllm:ollama (backwards compatible)
  model: devstral:latest
```

### Step 9: Keep old files for reference (optional)

Rename rather than delete the old files:

```bash
mv src/bdikit_context/llm/anyllm.py src/bdikit_context/llm/anyllm.py.deprecated
mv src/bdikit_context/llm/direct.py src/bdikit_context/llm/direct.py.deprecated
```

Or simply delete them if the git history is sufficient reference.

### Step 10: Rebuild container and verify

Same as bdi-kit upgrade plan — rebuild the container and verify all imports work.

## 6. LiteLLM Provider Model String Reference

litellm uses a `provider/model` format. Key mappings:

| Harmonia Provider | litellm Model String | Notes |
|---|---|---|
| `ollama` | `ollama_chat/devstral:latest` | Use `ollama_chat/` for chat, `ollama/` for completion |
| `openai` | `gpt-4o` | No prefix needed for OpenAI |
| `openrouter` | `openrouter/mistralai/devstral` | Full path including org |
| `anthropic` | `anthropic/claude-sonnet-4-5-20250929` | Anthropic prefix required |
| `groq` | `groq/llama-3.3-70b-versatile` | Groq prefix required |
| `together` | `together_ai/meta-llama/Llama-3-70b-chat-hf` | together_ai prefix |
| `deepseek` | `deepseek/deepseek-chat` | deepseek prefix |
| `azure` | `azure/deployment-name` | Azure prefix + deployment name |
| `bedrock` | `bedrock/anthropic.claude-v2` | Bedrock prefix + model ID |

The `_build_model_string()` method in `ChatLiteLLM` must handle these mappings correctly. Refer to https://docs.litellm.ai/docs/providers for the complete list.

## 7. Risk Assessment

| Risk | Impact | Mitigation |
|---|---|---|
| litellm model string format differs from what configs specify | Agent can't connect to LLM | `_build_model_string()` must map correctly; test with each provider |
| litellm handles tool calling differently | Agent tool calls fail | litellm normalizes to OpenAI format — same as any-llm; test thoroughly |
| litellm error messages differ from any-llm | Confusing error output | Map litellm exceptions to clear messages in `auth()` |
| Backwards compatibility breaks for `anyllm:` prefix configs | Existing configs stop working | Keep `anyllm:*` entries in provider map pointing to new LiteLLMModel |
| litellm is larger dependency | Container size increase | litellm is already required by bdi-kit v0.9, so no new dependency |
| Token counting differences | Context window overflow or premature truncation | litellm's counting is more accurate; this is an improvement |

## 8. Files Changed Summary

| File | Change | Description |
|---|---|---|
| `src/bdikit_context/llm/litellm_model.py` | **NEW** | `ChatLiteLLM` + `LiteLLMModel` classes (replaces anyllm.py) |
| `src/bdikit_context/llm/litellm_direct.py` | **NEW** | `DirectLiteLLMRunner` (replaces direct.py) |
| `src/bdikit_context/llm/anyllm.py` | **DELETE** | Replaced by litellm_model.py |
| `src/bdikit_context/llm/direct.py` | **DELETE** | Replaced by litellm_direct.py |
| `src/bdikit_context/llm/__init__.py` | Edit | Update provider map, handle `litellm:` prefix |
| `pyproject.toml` | Edit | Remove `any-llm-sdk`, ensure `litellm` is listed |
| `harmonia_beaker_LLM_agent_environment_apptainer.def` | Edit | Remove any-llm install, update verifications |
| `build_harmonia_apptainer.sh` | Edit | Update verification steps |
| `generate_env.py` | Edit | Update provider import paths |

## 9. Testing Plan

1. **Unit: ChatLiteLLM message conversion** — verify LangChain messages convert correctly to/from litellm format
2. **Unit: Tool binding** — verify `bind_tools()` produces valid OpenAI tool schemas
3. **Unit: Model string construction** — verify `_build_model_string()` produces correct litellm model strings for each provider
4. **Integration: Ollama provider** — start an Ollama instance, run a manual experiment with `provider: litellm:ollama`
5. **Integration: OpenRouter provider** — run with `provider: litellm:openrouter` (or `anyllm:openrouter` for backwards compat)
6. **Integration: Tool calling** — verify the agent can call all 5 bdi-kit tools and get results
7. **Regression: Existing configs** — verify configs with `provider: anyllm:ollama` still work via backwards compatibility

## 10. Comparison: any-llm vs litellm in This Context

Based on the comparison document at `docs/miscellaneous/anyllm_vs_litellm_comparison.docx`:

| Dimension | any-llm | litellm | Winner for Harmonia |
|---|---|---|---|
| Provider count | ~36 | 100+ | litellm (more future options) |
| Already a dependency | After removal: no | Yes (bdi-kit v0.9 requires it) | litellm (unified stack) |
| Token counting | Manual ~4 chars/token | Model-specific counters | litellm |
| Model string format | Separate provider + model | Single `provider/model` string | litellm (matches bdi-kit) |
| SDK strategy | Wraps official SDKs | Reimplements provider APIs | any-llm (higher fidelity) |
| Latency overhead | Zero (direct SDK) | Minimal (translation layer) | any-llm (marginal) |

**Net assessment:** litellm wins for Harmonia because it unifies the stack, is already a required dependency, and provides better token counting. The marginal latency advantage of any-llm is not significant for Harmonia's use case (agent interactions are not latency-critical compared to the LLM inference time itself).
