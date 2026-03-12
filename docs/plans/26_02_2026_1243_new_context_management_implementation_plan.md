# Implementation Plan: Comprehensive Context Management for Archytas, Beaker, and Harmonia

**Date:** 26 February 2026
**Supersedes:** The `context_management:` YAML structure and `ContextManagementConfig` from `25_02_2026_2238_fix_context_issues.md`. Fix 1 (Ollama num_ctx passthrough + VRAM estimation) and the FETCH_STATE_CODE patch mechanics from Fix 2 of that plan are unchanged and should be implemented as written there. This plan replaces the configuration architecture and adds Archytas-level context management.

---

## Table of Contents

1. [Problem Summary](#1-problem-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [YAML Configuration Design](#3-yaml-configuration-design)
4. [Change Specifications by Codebase](#4-change-specifications-by-codebase)
5. [Implementation Order](#5-implementation-order)
6. [File Summary](#6-file-summary)
7. [Verification Checklist](#7-verification-checklist)
8. [Commit Instructions](#8-commit-instructions)

---

## 1. Problem Summary

### 1.1 Current State

The Harmonia system uses three codebases for LLM agent execution:

| Codebase | Version | Path | Role |
|---|---|---|---|
| **Archytas** | 1.6.6 (PyPI, latest upstream) | `/hpc/compgen/projects/llm_GEO_project/archytas/` | LLM agent framework: ReAct loop, chat history, summarization |
| **Beaker** | 1.14.0 (dev branch, latest upstream) | `/hpc/compgen/projects/llm_GEO_project/beaker-kernel/` | Jupyter kernel + agent integration, model instantiation |
| **Harmonia** | Local | `harmonia_metadata_agent/analysis/dstoker/harmonia/` | Experiment config, env generation, container orchestration |

The config pipeline is:

```
Experiment YAML
    → generate_env.py → .env file
    → exec_apptainer_harmonia.sh (--env-file) → Apptainer container env vars
    → Beaker Config.from_config_file() → Config object
    → Config.get_model() → deep-copies providers[provider] dict → adds model_name, api_key
    → cls(config_obj) → ModelConfig → BaseArchytasModel subclass
    → BeakerAgent.__init__ → ReActAgent.__init__(model=model, ...)
```

### 1.2 Problems Identified

| # | Problem | Impact | Root cause |
|---|---|---|---|
| P1 | `summarization_threshold_pct` never reaches Archytas | Summarization triggers at 50% (Archytas default) instead of configured value | Beaker's static `providers` dict only has `import_path`, `default_model_name`, `api_key`. The `summarization_threshold_pct` field exists on `LLM_Service_Provider` (default: 20%) but is not in the static dict entries (config.py lines 276-307) |
| P2 | Ollama `contextsize()` can return `None` | Summarization **silently never triggers** because `summarization_threshold` returns `None` and `needs_summarization()` returns `False` | `OllamaModel.contextsize()` (ollama.py:37-48) queries the API; if model info lacks the context_length key, returns `None` |
| P3 | `max_react_steps` is unlimited | Runaway ReAct loops fill the entire context window before summarization kicks in | `BeakerAgent.__init__` (agent.py:27-50) does not pass `max_react_steps` to `ReActAgent`. Default is `float("inf")` |
| P4 | Tool output truncation is hardcoded | 1000-char snippet is too small for some tasks, too large for others; not tunable per experiment | `MESSAGE_SUMMARIZATION_THRESHOLD` and `MESSAGE_SUMMARIZATION_SNIPPET_SIZE` are constants in summarizers.py:27-28 |
| P5 | No summarization model separation | Summarization consumes tokens on the primary (expensive/large) model | `default_history_summarizer` and `default_loop_summarizer` always use `agent.model` |
| P6 | No configurable context management in experiment YAML | All context behavior is hardcoded or uses defaults | No `context_management:` section exists in experiment configs |

### 1.3 Key Code Locations (Reference)

**Archytas** (`/hpc/compgen/projects/llm_GEO_project/archytas/archytas/`):

| File | Key contents |
|---|---|
| `models/base.py:40-46` | `ModelConfig` — pydantic model with `model_name`, `api_key`, `summarization_ratio`, `summarization_threshold`, `summarization_threshold_pct`. Uses `extra='allow'` so additional dict keys are stored in `model_extra`. |
| `models/base.py:95-144` | `BaseArchytasModel` — `DEFAULT_SUMMARIZATION_RATIO = 0.5`, `contextsize()` returns `None` by default, `summarization_threshold` property implements priority chain: explicit threshold > ratio > pct > default 0.5 |
| `models/ollama.py:36-48` | `OllamaModel.contextsize()` — queries Ollama API `show()` for `{arch}.context_length`. Returns `None` on `KeyError`. |
| `summarizers.py:27-28` | `MESSAGE_SUMMARIZATION_THRESHOLD = 1000`, `MESSAGE_SUMMARIZATION_SNIPPET_SIZE = 1000` — hardcoded constants |
| `summarizers.py:84-103` | `default_loop_summarizer()` — summarizes tool messages within a ReAct loop. Accepts `model` param. |
| `summarizers.py:108-165` | `default_history_summarizer()` — summarizes full conversation when threshold exceeded. Accepts `model` param but always receives `agent.model`. |
| `summarizers.py:168-203` | `default_tool_summarizer()` — truncates tool output to first `SNIPPET_SIZE` chars if over `THRESHOLD`. |
| `chat_history.py:126-181` | `ChatHistory.__init__()` — accepts `model`, `loop_summarizer`, `history_summarizer`. Stores `summarization_threshold` from `model.default_summarization_threshold` or -1. |
| `chat_history.py:231-240` | `needs_summarization()` — checks `model.summarization_threshold` (property, not stored value). Returns `False` if threshold is `None`. |
| `chat_history.py:265-315` | `summarize_history()` — creates asyncio task calling `self.history_summarizer()`, passing `model=agent.model`. |
| `agent.py:78-120` | `Agent.__init__()` — creates `ChatHistory(messages)` without passing `model` parameter. Sets temperature. |
| `react.py:174-235` | `ReActAgent.__init__()` — accepts `max_errors=3`, `max_react_steps=None` (defaults to `float("inf")`). |

**Beaker** (`/hpc/compgen/projects/llm_GEO_project/beaker-kernel/beaker_kernel/`):

| File | Key contents |
|---|---|
| `lib/config.py:175-200` | `LLM_Service_Provider` dataclass — fields: `import_path`, `default_model_name`, `api_key`, `summarization_threshold_pct` (default: 20) |
| `lib/config.py:273-308` | `ConfigClass.providers` — static dict of provider entries. Only contains `import_path`, `default_model_name`, `api_key`. Does NOT include `summarization_threshold_pct`. |
| `lib/config.py:433-480` | `Config.get_model()` — deep-copies provider dict, adds `model_name`/`api_key`/`import_path` overrides, calls `cls(config_obj)`. |
| `lib/agent.py:27-50` | `BeakerAgent.__init__()` — calls `super().__init__(model=model, ...)`. Does NOT pass `max_react_steps` or `max_errors`. |

**Harmonia**:

| File | Key contents |
|---|---|
| `src/automation/config.py` | `ExperimentConfig.from_dict()` — parses YAML. No `context_management` section. |
| `generate_env.py` | Transforms YAML → .env. Does NOT emit summarization or context management env vars. |
| `exec_apptainer_harmonia.sh:618-622` | Exports `OLLAMA_CONTEXT_LENGTH`. Does not export `OLLAMA_NUM_CTX`. |
| `exec_apptainer_harmonia.sh:514-537` | Pre-loads Ollama model via `/api/generate` with `num_ctx`. Only pre-loads one model. |
| `exec_apptainer_harmonia.sh:892` | Passes `--env-file ${ENV_FILE}` to Apptainer. |
| `.env.template` | Documents available env vars. No context management vars. |
| `harmonia_beaker_LLM_agent_environment_apptainer.def` | Installs `beaker_kernel>=1.14.0` (which pulls `archytas>=1.6.5`). No FETCH_STATE_CODE patches. |

---

## 2. Architecture Overview

### 2.1 Data Flow for New Configuration

```
Experiment YAML
│
├─ context_management.python_kernel.*  ──→ generate_env.py ──→ HARMONIA_STATE_* env vars
│                                                                  │
│                                                            exec_apptainer_harmonia.sh
│                                                                  │
│                                                            Apptainer --env-file
│                                                                  │
│                                                            FETCH_STATE_CODE patch
│                                                            (reads env vars at kernel runtime)
│
├─ context_management.archytas.*  ──→ generate_env.py ──→ ARCHYTAS_* env vars
│                                                              │
│                              ┌───────────────────────────────┤
│                              │                               │
│                    ┌─────────▼──────────┐        ┌───────────▼────────────┐
│                    │ Beaker config.py   │        │ Archytas summarizers.py│
│                    │ (provider dict)    │        │ (reads env vars for    │
│                    │ + agent.py kwargs  │        │  snippet size, etc.)   │
│                    └─────────┬──────────┘        └────────────────────────┘
│                              │
│                    ┌─────────▼──────────┐
│                    │ ModelConfig        │
│                    │ (summarization_    │
│                    │  threshold_pct,    │
│                    │  context_window_   │
│                    │  override)         │
│                    └─────────┬──────────┘
│                              │
│                    ┌─────────▼──────────┐
│                    │ ReActAgent         │
│                    │ (max_react_steps,  │
│                    │  max_errors)       │
│                    └────────────────────┘
│
└─ context_management.archytas.summarization_model  ──→ generate_env.py
                                                            │
                                                    ARCHYTAS_SUMMARIZATION_MODEL_CONFIG (JSON)
                                                            │
                                              ┌─────────────▼─────────────────┐
                                              │ Archytas summarizers.py       │
                                              │ (lazy model creation on       │
                                              │  first summarization call)    │
                                              └───────────────────────────────┘
                                                            +
                                              exec_apptainer_harmonia.sh
                                              (pre-pulls Ollama model if local)
```

### 2.2 Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| YAML location | `context_management:` with `python_kernel:` and `archytas:` subsections | User preference. Groups all context management together with clear separation of concerns. |
| How settings reach Archytas | Hybrid: model config via env vars → ModelConfig; agent settings via Beaker patch → ReActAgent kwargs | Model-level settings (threshold, context window) belong in ModelConfig. Agent-level settings (max_steps) must pass through ReActAgent constructor. |
| Archytas hardcoded constants | Modify Archytas to read env vars with current values as defaults | Clean, upstream-friendly, single source of truth. |
| Summarization model | Lazy creation in Archytas from JSON env var config; Ollama pre-pull in exec script | Future-proof: works for local + remote models, zero Beaker changes needed, fallback to primary model when unset. |
| `summarization_threshold_pct` flow | Fix Beaker's provider dict + add env var fallback in Archytas | Belt and suspenders: fix the intended mechanism, add fallback for robustness. |
| `context_window_override` | New field on `ModelConfig`, checked in `BaseArchytasModel.contextsize()` | Works for all model backends, not just Ollama. |

---

## 3. YAML Configuration Design

### 3.1 New `context_management:` Section

Add this to experiment config YAMLs. All fields are optional with sensible defaults.

```yaml
# Context management configuration
# Controls how conversation history, kernel state, and tool outputs are managed
# to prevent context window exhaustion.
context_management:

  # --- Python kernel state budget (Beaker FETCH_STATE_CODE patch) ---
  # Controls how much of the kernel namespace is serialized and sent to the LLM.
  python_kernel:
    # Max chars per single variable in kernel state (0 = disabled)
    max_variable_size: 20000
    # Total state budget as percentage of model context window
    state_budget_pct: 25
    # Type names to exclude from kernel state serialization
    type_blacklist:
      - SchemaGraph
      - SimilarityFloodingMatcher
      - ColumnMappingSpec
      - ValueMappingSpec
    # Variable names to always include in full, even if over size cap
    var_whitelist:
      - df
      - df_harmonized
      - df_subset
      - result
      - results
      - output
      - harmonized
      - mapping
      - column_mapping
      - value_mapping

  # --- Archytas agent/model context management ---
  # Controls LLM conversation summarization, tool output truncation,
  # and ReAct loop limits.
  archytas:
    # When to trigger history summarization (% of model context window).
    # Lower = more aggressive summarization (less context used before compressing).
    # Range: 0-100. Default: 50.
    summarization_threshold_pct: 50

    # Force the context window size in tokens.
    # Critical for Ollama models where the API may not report context length.
    # When null, Archytas queries the model API (which may return None for Ollama,
    # silently disabling all summarization).
    # Set this to the value of llm.context_length for safety.
    context_window_override: null

    # Max output tokens per LLM response (null = model/provider default).
    max_tokens: null

    # Tool output truncation: outputs shorter than this (in chars) are left as-is.
    # Longer outputs are truncated to tool_output_snippet_size chars.
    tool_output_summarization_threshold: 1000

    # Number of chars to keep when truncating long tool outputs.
    tool_output_snippet_size: 1000

    # Max ReAct loop iterations per user query (null = unlimited).
    # Prevents runaway loops from filling the context window.
    max_react_steps: 30

    # Max errors per ReAct loop before the agent gives up.
    max_errors: 3

    # Separate model for summarization (null = use primary model).
    # Useful for using a smaller/cheaper model for context compression.
    # Must be a model accessible by the same provider infrastructure.
    summarization_model: null

    # Provider for the summarization model (null = same as primary).
    # Only needed if summarization_model uses a different provider.
    summarization_model_provider: null
```

### 3.2 Example: Ollama Experiment with Full Context Management

```yaml
experiment:
  name: dou_harmonization_devstral
  description: Harmonize dou.csv to GDC schema using devstral via Ollama

llm:
  provider: ollama
  model: devstral:latest
  base_url: http://localhost:11434
  temperature: 0.0
  context_length: 64000

context_management:
  python_kernel:
    max_variable_size: 20000
    state_budget_pct: 25
  archytas:
    summarization_threshold_pct: 50
    context_window_override: 64000  # Match llm.context_length for safety
    max_react_steps: 30
    tool_output_snippet_size: 2000  # Keep more tool context for this experiment

# ... messages, output, evaluation sections as before ...
```

### 3.3 Example: OpenRouter Experiment with Summarization Model

```yaml
experiment:
  name: dou_harmonization_claude
  description: Harmonize dou.csv using Claude via OpenRouter

llm:
  provider: openrouter
  model: anthropic/claude-sonnet-4-20250514

context_management:
  archytas:
    summarization_threshold_pct: 60
    max_react_steps: 25
    summarization_model: meta-llama/llama-3.1-8b-instruct
    summarization_model_provider: openrouter
```

---

## 4. Change Specifications by Codebase

### 4.1 Archytas Changes

All changes to `/hpc/compgen/projects/llm_GEO_project/archytas/archytas/`.

#### 4.1.1 `models/base.py` — Add `context_window_override` to ModelConfig

**What:** Add a new optional field to `ModelConfig` and modify `BaseArchytasModel.contextsize()` to check it first.

**Why:** Solves P2. When Ollama's API doesn't report context length, this provides a fallback so summarization thresholds can be calculated.

**Current code (lines 40-46):**
```python
class ModelConfig(PydanticModel, extra='allow'):
    model_name: str
    model_config = ConfigDict(extra="allow", protected_namespaces=())
    api_key: str | None = None
    summarization_ratio: float | None = None
    summarization_threshold: int | None = None
    summarization_threshold_pct: int | None = None
```

**New code (replace):**
```python
class ModelConfig(PydanticModel, extra='allow'):
    model_name: str
    model_config = ConfigDict(extra="allow", protected_namespaces=())
    api_key: str | None = None
    summarization_ratio: float | None = None
    summarization_threshold: int | None = None
    summarization_threshold_pct: int | None = None
    context_window_override: int | None = None
```

**Current `contextsize()` method (lines 168-172):**
```python
@cache
def contextsize(self, model_name: Optional[str]=None) -> int | None:
    if model_name is None:
        model_name = self.model_name
    return None
```

**New `contextsize()` method (replace):**
```python
@cache
def contextsize(self, model_name: Optional[str]=None) -> int | None:
    if model_name is None:
        model_name = self.model_name
    # Check config override first (critical for Ollama models where API may not report context length)
    override = getattr(self.config, 'context_window_override', None)
    if override is None:
        # Fall back to env var
        import os
        env_override = os.environ.get('ARCHYTAS_CONTEXT_WINDOW_OVERRIDE')
        if env_override:
            try:
                override = int(env_override)
            except ValueError:
                pass
    if override is not None:
        return int(override)
    return None
```

**Important:** Subclasses (`OllamaModel`, `AnthropicModel`, etc.) override `contextsize()` with their own `@lru_cache` decorator. The override in the base class only applies when the subclass's method returns `None`. We must also modify the subclass pattern. See 4.1.2.

#### 4.1.2 `models/ollama.py` — Check override before API query

**Current `contextsize()` (lines 36-48):**
```python
@lru_cache()
def contextsize(self, model_name: str | None = None) -> int | None:
    if model_name is None:
        model_name = self.model_name
    show_response = self.model._client.show(self.model_name)
    model_info = show_response.modelinfo
    try:
        model_arch = model_info["general.architecture"]
        context_length = model_info[f"{model_arch}.context_length"]
        return int(context_length)
    except KeyError:
        print("No context length in model info")
        return None
```

**New `contextsize()` (replace):**
```python
@lru_cache()
def contextsize(self, model_name: str | None = None) -> int | None:
    if model_name is None:
        model_name = self.model_name
    # Check config override and env var (critical for Ollama models)
    override = getattr(self.config, 'context_window_override', None)
    if override is None:
        import os
        env_override = os.environ.get('ARCHYTAS_CONTEXT_WINDOW_OVERRIDE')
        if env_override:
            try:
                override = int(env_override)
            except ValueError:
                pass
    if override is not None:
        return int(override)
    # Query Ollama API
    try:
        show_response = self._model._client.show(self.model_name)
        model_info = show_response.modelinfo
        model_arch = model_info["general.architecture"]
        context_length = model_info[f"{model_arch}.context_length"]
        return int(context_length)
    except (KeyError, Exception) as e:
        logger.warning(f"Could not determine context length for {model_name} from Ollama API: {e}. "
                       "Set context_window_override in ModelConfig or ARCHYTAS_CONTEXT_WINDOW_OVERRIDE env var.")
        return None
```

Add `import logging` and `logger = logging.getLogger(__name__)` at the top of the file if not already present.

#### 4.1.3 `models/base.py` — Add env var fallback for `summarization_threshold_pct`

**Why:** Solves P1 (belt-and-suspenders). Even if Beaker's provider dict is fixed, the env var fallback ensures it works in all scenarios.

**Current `summarization_threshold` property (lines 127-144):**
```python
@property
def summarization_threshold(self) -> int | None:
    context_size = self.contextsize(self.model_name)
    if summarization_threshold := getattr(self.config, 'summarization_threshold', None):
        if context_size is None:
            return summarization_threshold
        else:
            return min(int(summarization_threshold), context_size)
    elif summarization_ratio := getattr(self.config, 'summarization_ratio', None):
        pass
    elif summarization_threshold_pct := getattr(self.config, 'summarization_threshold_pct', None):
        summarization_ratio = float(summarization_threshold_pct) / 100
        self.config.summarization_ratio = summarization_ratio
    else:
        summarization_ratio = self.DEFAULT_SUMMARIZATION_RATIO
    if context_size is None:
        return None
    return int(context_size * summarization_ratio)
```

**New `summarization_threshold` property (replace):**
```python
@property
def summarization_threshold(self) -> int | None:
    context_size = self.contextsize(self.model_name)
    if summarization_threshold := getattr(self.config, 'summarization_threshold', None):
        if context_size is None:
            return summarization_threshold
        else:
            return min(int(summarization_threshold), context_size)
    elif summarization_ratio := getattr(self.config, 'summarization_ratio', None):
        pass
    elif summarization_threshold_pct := getattr(self.config, 'summarization_threshold_pct', None):
        summarization_ratio = float(summarization_threshold_pct) / 100
        self.config.summarization_ratio = summarization_ratio
    else:
        # Env var fallback for summarization_threshold_pct
        import os
        env_pct = os.environ.get('ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT')
        if env_pct:
            try:
                summarization_ratio = float(env_pct) / 100
            except ValueError:
                summarization_ratio = self.DEFAULT_SUMMARIZATION_RATIO
        else:
            summarization_ratio = self.DEFAULT_SUMMARIZATION_RATIO
    if context_size is None:
        return None
    return int(context_size * summarization_ratio)
```

#### 4.1.4 `summarizers.py` — Make constants configurable via env vars

**Why:** Solves P4.

**Current code (lines 27-28):**
```python
MESSAGE_SUMMARIZATION_THRESHOLD: int = 1000
MESSAGE_SUMMARIZATION_SNIPPET_SIZE: int = 1000
```

**New code (replace):**
```python
import os as _os

MESSAGE_SUMMARIZATION_THRESHOLD: int = int(
    _os.environ.get("ARCHYTAS_TOOL_SUMMARIZATION_THRESHOLD", "1000")
)
MESSAGE_SUMMARIZATION_SNIPPET_SIZE: int = int(
    _os.environ.get("ARCHYTAS_TOOL_SNIPPET_SIZE", "1000")
)
```

Note: `os` is already imported in the file for other purposes. If not, add it. The `_os` alias avoids shadowing if there's a local `os` variable, but using the existing `os` import is also fine — check the file's existing imports.

#### 4.1.5 `summarizers.py` — Add lazy summarization model support

**Why:** Solves P5.

Add a module-level cached function and modify `default_history_summarizer` to use it.

**Add this new function after the existing imports (around line 30):**

```python
_summarization_model_cache = None
_summarization_model_initialized = False

def _get_summarization_model():
    """
    Lazily create a separate model for summarization if configured via env var.
    Returns None if no summarization model is configured (caller should use agent.model).

    The env var ARCHYTAS_SUMMARIZATION_MODEL_CONFIG should be a JSON dict with at minimum:
      {"import_path": "archytas.models.ollama.OllamaModel", "model_name": "llama3.2:3b"}
    Additional keys (api_key, etc.) are passed to the model constructor.
    """
    global _summarization_model_cache, _summarization_model_initialized
    if _summarization_model_initialized:
        return _summarization_model_cache

    _summarization_model_initialized = True

    config_json = os.environ.get("ARCHYTAS_SUMMARIZATION_MODEL_CONFIG")
    if not config_json:
        return None

    try:
        import importlib
        config_dict = json.loads(config_json)
        import_path = config_dict.pop("import_path")
        module_name, cls_name = import_path.rsplit('.', 1)
        module = importlib.import_module(module_name)
        cls = getattr(module, cls_name)
        _summarization_model_cache = cls(config_dict)
        logger.info(f"Created separate summarization model: {import_path} ({config_dict.get('model_name', 'unknown')})")
    except Exception as e:
        logger.warning(f"Failed to create summarization model from ARCHYTAS_SUMMARIZATION_MODEL_CONFIG: {e}. "
                       "Falling back to primary model for summarization.")
        _summarization_model_cache = None

    return _summarization_model_cache
```

**Modify `default_history_summarizer` (currently lines 108-165):**

Change the beginning of the function from:

```python
async def default_history_summarizer(
    chat_history: "ChatHistory",
    agent: "Agent",
    recordset: "list[MessageRecord[BaseMessage]|SummaryRecord]",
    model: "BaseArchytasModel" = None,
    force_update: bool = False,
):
    from .chat_history import MessageRecord, SummaryRecord, AIMessage, SystemMessage, HumanMessage, BaseMessage
    logger.debug(f"Summarizing history {chat_history=}, {agent=}, {force_update=}")

    if not recordset:
        return

    if model is None:
        model = agent.model
```

To:

```python
async def default_history_summarizer(
    chat_history: "ChatHistory",
    agent: "Agent",
    recordset: "list[MessageRecord[BaseMessage]|SummaryRecord]",
    model: "BaseArchytasModel" = None,
    force_update: bool = False,
):
    from .chat_history import MessageRecord, SummaryRecord, AIMessage, SystemMessage, HumanMessage, BaseMessage
    logger.debug(f"Summarizing history {chat_history=}, {agent=}, {force_update=}")

    if not recordset:
        return

    # Use dedicated summarization model if configured, otherwise primary model
    summarization_model = _get_summarization_model()
    if summarization_model is not None:
        model = summarization_model
    elif model is None:
        model = agent.model
```

**Similarly modify `default_loop_summarizer` (currently lines 84-103):**

After `if model is None: model = agent.model`, add the summarization model check:

```python
async def default_loop_summarizer(
    loop_records: "list[MessageRecord]",
    chat_history: "ChatHistory",
    agent: "Agent",
    model: "BaseArchytasModel" = None,
    token_threshold: int = 4000,
    force_update: bool = False,
):
    from langchain_core.messages import ToolMessage
    # Use dedicated summarization model if configured, otherwise primary model
    summarization_model = _get_summarization_model()
    if summarization_model is not None:
        model = summarization_model
    elif model is None:
        model = agent.model
    # ... rest of function unchanged ...
```

### 4.2 Beaker Changes

All changes to `/hpc/compgen/projects/llm_GEO_project/beaker-kernel/beaker_kernel/`.

#### 4.2.1 `lib/config.py` — Fix provider dict to include `summarization_threshold_pct`

**Why:** Solves P1 (primary fix). The field exists on `LLM_Service_Provider` but the static defaults don't include it, so it never flows into the ModelConfig dict.

**Current `providers` default_factory (lines 276-307):**
```python
"openai": {
    "import_path": "archytas.models.openai.OpenAIModel",
    "default_model_name": "gpt-4o-mini",
    "api_key": ""
},
```

**New (add `summarization_threshold_pct` to each entry):**
```python
"openai": {
    "import_path": "archytas.models.openai.OpenAIModel",
    "default_model_name": "gpt-4o-mini",
    "api_key": "",
    "summarization_threshold_pct": 20,
},
```

Repeat for all 6 providers: `openai`, `anthropic`, `bedrock`, `gemini`, `groq`, `ollama`.

Additionally, add `context_window_override` to `Config.get_model()` so it flows from env vars:

**In `get_model()`, after the `if self.llm_service_token:` block (around line 461), add:**

```python
# Pass through context management env vars to model config
import os
env_context_override = os.environ.get('ARCHYTAS_CONTEXT_WINDOW_OVERRIDE')
if env_context_override:
    config_obj["context_window_override"] = int(env_context_override)
env_summ_pct = os.environ.get('ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT')
if env_summ_pct:
    config_obj["summarization_threshold_pct"] = int(env_summ_pct)
```

#### 4.2.2 `lib/agent.py` — Pass `max_react_steps` and `max_errors` to ReActAgent

**Why:** Solves P3.

**Current `BeakerAgent.__init__` super() call (around line 45):**
```python
super().__init__(
    model=model,
    api_key=config.llm_service_token,
    tools=tools,
    verbose=self.context.beaker_kernel.verbose,
    spinner=None,
    rich_print=False,
    allow_ask_user=False,
    thought_handler=context.beaker_kernel.handle_thoughts,
    **kwargs
)
```

**New (add env var reads before super call, pass as kwargs):**

Add before the `super().__init__()` call:

```python
# Read agent-level context management settings from env vars
import os
max_react_steps_str = os.environ.get('ARCHYTAS_MAX_REACT_STEPS')
max_errors_str = os.environ.get('ARCHYTAS_MAX_ERRORS')
if max_react_steps_str:
    try:
        kwargs['max_react_steps'] = int(max_react_steps_str)
    except ValueError:
        pass
if max_errors_str:
    try:
        kwargs['max_errors'] = int(max_errors_str)
    except ValueError:
        pass
```

The existing `**kwargs` in the super call will pass these through to `ReActAgent.__init__()`.

### 4.3 Harmonia Changes

All changes in `harmonia_metadata_agent/analysis/dstoker/harmonia/`.

#### 4.3.1 `src/automation/config.py` — Add `ContextManagementConfig`

**Add these new dataclasses before `ExperimentConfig`:**

```python
@dataclass
class PythonKernelContextConfig:
    """Configuration for kernel state budget enforcement (FETCH_STATE_CODE patch)."""
    max_variable_size: int = 20_000
    state_budget_pct: int = 25
    type_blacklist: list[str] = field(default_factory=lambda: [
        "SchemaGraph", "SimilarityFloodingMatcher",
        "ColumnMappingSpec", "ValueMappingSpec",
    ])
    var_whitelist: list[str] = field(default_factory=lambda: [
        "df", "df_harmonized", "df_subset", "result", "results",
        "output", "harmonized", "mapping", "column_mapping", "value_mapping",
    ])


@dataclass
class ArchytasContextConfig:
    """Configuration for Archytas agent/model context management."""
    summarization_threshold_pct: int = 50
    context_window_override: Optional[int] = None
    max_tokens: Optional[int] = None
    tool_output_summarization_threshold: int = 1000
    tool_output_snippet_size: int = 1000
    max_react_steps: Optional[int] = 30
    max_errors: int = 3
    summarization_model: Optional[str] = None
    summarization_model_provider: Optional[str] = None


@dataclass
class ContextManagementConfig:
    """Top-level context management configuration."""
    python_kernel: PythonKernelContextConfig = field(default_factory=PythonKernelContextConfig)
    archytas: ArchytasContextConfig = field(default_factory=ArchytasContextConfig)
```

**Add `context_management` to `ExperimentConfig`:**

```python
@dataclass
class ExperimentConfig:
    """Complete experiment configuration."""
    name: str
    description: str
    llm: LLMConfig
    messages: list[MessageConfig]
    output: OutputConfig = field(default_factory=OutputConfig)
    decision_handling: DecisionConfig = field(default_factory=DecisionConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    context_management: ContextManagementConfig = field(default_factory=ContextManagementConfig)
    manual_mode: bool = False
    dataset_metadata: Optional[str] = None
    context: Optional[str] = None
```

**Add parsing to `ExperimentConfig.from_dict()`:**

After the `prompts_data` line (around line 99), add:

```python
cm_data = data.get("context_management", {})
pk_data = cm_data.get("python_kernel", {})
arch_data = cm_data.get("archytas", {})

python_kernel_config = PythonKernelContextConfig(
    max_variable_size=pk_data.get("max_variable_size", 20_000),
    state_budget_pct=pk_data.get("state_budget_pct", 25),
    type_blacklist=pk_data.get("type_blacklist", PythonKernelContextConfig().type_blacklist),
    var_whitelist=pk_data.get("var_whitelist", PythonKernelContextConfig().var_whitelist),
)
archytas_config = ArchytasContextConfig(
    summarization_threshold_pct=arch_data.get("summarization_threshold_pct", 50),
    context_window_override=arch_data.get("context_window_override"),
    max_tokens=arch_data.get("max_tokens"),
    tool_output_summarization_threshold=arch_data.get("tool_output_summarization_threshold", 1000),
    tool_output_snippet_size=arch_data.get("tool_output_snippet_size", 1000),
    max_react_steps=arch_data.get("max_react_steps", 30),
    max_errors=arch_data.get("max_errors", 3),
    summarization_model=arch_data.get("summarization_model"),
    summarization_model_provider=arch_data.get("summarization_model_provider"),
)
context_management = ContextManagementConfig(
    python_kernel=python_kernel_config,
    archytas=archytas_config,
)
```

Add `context_management=context_management,` to the `return cls(...)` call.

#### 4.3.2 `generate_env.py` — Emit context management env vars

**Why:** Bridges the YAML config to the env var pipeline that reaches Archytas and Beaker inside the container.

**Add this block after the `bdikit_models` section (around line 198), before the output path calculation:**

```python
# Handle context management configuration
cm_config = config.get('context_management', {})

# --- Python kernel state budget env vars ---
pk_config = cm_config.get('python_kernel', {})
pk_vars = {
    'max_variable_size': ('HARMONIA_STATE_MAX_VAR_SIZE', '20000'),
    'state_budget_pct': ('HARMONIA_STATE_BUDGET_PCT', '25'),
}
for yaml_key, (env_var, default) in pk_vars.items():
    value = pk_config.get(yaml_key)
    if value is not None:
        env_content = update_env_value(env_content, env_var, str(value))

# Type blacklist and var whitelist as comma-separated strings
type_blacklist = pk_config.get('type_blacklist')
if type_blacklist and isinstance(type_blacklist, list):
    env_content = update_env_value(env_content, 'HARMONIA_STATE_TYPE_BLACKLIST', ','.join(type_blacklist))

var_whitelist = pk_config.get('var_whitelist')
if var_whitelist and isinstance(var_whitelist, list):
    env_content = update_env_value(env_content, 'HARMONIA_STATE_VAR_WHITELIST', ','.join(var_whitelist))

# --- Archytas context management env vars ---
arch_config = cm_config.get('archytas', {})

arch_vars = {
    'summarization_threshold_pct': ('ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT', None),
    'context_window_override': ('ARCHYTAS_CONTEXT_WINDOW_OVERRIDE', None),
    'tool_output_summarization_threshold': ('ARCHYTAS_TOOL_SUMMARIZATION_THRESHOLD', None),
    'tool_output_snippet_size': ('ARCHYTAS_TOOL_SNIPPET_SIZE', None),
    'max_react_steps': ('ARCHYTAS_MAX_REACT_STEPS', None),
    'max_errors': ('ARCHYTAS_MAX_ERRORS', None),
    'max_tokens': ('LLM_MAX_TOKENS', None),
}
for yaml_key, (env_var, _) in arch_vars.items():
    value = arch_config.get(yaml_key)
    if value is not None:
        env_content = update_env_value(env_content, env_var, str(value))

# Build summarization model config JSON if specified
summ_model = arch_config.get('summarization_model')
if summ_model:
    summ_provider = arch_config.get('summarization_model_provider', provider)
    import json as _json

    # Build the import path for the summarization model
    summ_import_path = get_provider_import_path(summ_provider)

    summ_config = {
        "import_path": summ_import_path,
        "model_name": summ_model,
    }

    # For providers that need a base_url (Ollama), add it
    if 'ollama' in summ_provider.lower():
        summ_base_url = llm_config.get('base_url', 'http://localhost:11434')
        summ_config["base_url"] = summ_base_url

    # For providers that need an API key, try to get it from the base env
    summ_api_key = get_api_key_for_provider(summ_provider, env_content)
    if summ_api_key:
        summ_config["api_key"] = summ_api_key

    env_content = update_env_value(
        env_content,
        'ARCHYTAS_SUMMARIZATION_MODEL_CONFIG',
        _json.dumps(summ_config),
    )
```

#### 4.3.3 `exec_apptainer_harmonia.sh` — Pre-pull summarization model + calculate absolute budgets

**Why:** For Ollama summarization models, the model must be downloaded and available before Archytas lazily instantiates it. Also, the FETCH_STATE_CODE patch needs absolute char budgets calculated from percentage + context window.

**Add after the existing OLLAMA_CONTEXT_LENGTH export block (line 622), before `start_ollama_server`:**

```bash
# Export OLLAMA_CONTEXT_LENGTH and OLLAMA_NUM_CTX if set.
# Both env vars are set because the exact name varies across Ollama versions.
# Without this, Ollama defaults to num_ctx=4096 on /api/chat calls and silently truncates.
if [ -n "$OLLAMA_CONTEXT_LENGTH" ]; then
    export OLLAMA_CONTEXT_LENGTH
    export OLLAMA_NUM_CTX="${OLLAMA_CONTEXT_LENGTH}"
    echo "   OLLAMA_CONTEXT_LENGTH: ${OLLAMA_CONTEXT_LENGTH}"
    echo "   OLLAMA_NUM_CTX:        ${OLLAMA_CONTEXT_LENGTH} (server-level default for /api/chat)"
fi

# Read context management env vars from .env for display and budget calculation
HARMONIA_STATE_BUDGET_PCT=$(grep "^HARMONIA_STATE_BUDGET_PCT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT=$(grep "^ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
ARCHYTAS_SUMMARIZATION_MODEL_CONFIG=$(grep "^ARCHYTAS_SUMMARIZATION_MODEL_CONFIG=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2-)

# Calculate absolute state budget from percentage if context_length is known
if [ -n "$OLLAMA_CONTEXT_LENGTH" ] && [ -n "$HARMONIA_STATE_BUDGET_PCT" ]; then
    CHARS_PER_TOKEN=4
    CONTEXT_CHARS=$((OLLAMA_CONTEXT_LENGTH * CHARS_PER_TOKEN))
    HARMONIA_STATE_TOTAL_BUDGET=$((CONTEXT_CHARS * HARMONIA_STATE_BUDGET_PCT / 100))
    echo "   State budget: ${HARMONIA_STATE_BUDGET_PCT}% of ${OLLAMA_CONTEXT_LENGTH} tokens ≈ ${HARMONIA_STATE_TOTAL_BUDGET} chars"
    # Write back to .env so it's available in the container
    echo "HARMONIA_STATE_TOTAL_BUDGET=${HARMONIA_STATE_TOTAL_BUDGET}" >> "$ENV_FILE"
fi
```

**Add after the existing model pre-load block (after line 537), to pre-pull the summarization model:**

```bash
# Pre-pull summarization model if configured and it's an Ollama model
if [ -n "$ARCHYTAS_SUMMARIZATION_MODEL_CONFIG" ]; then
    # Extract model name from JSON config
    SUMM_MODEL=$(echo "$ARCHYTAS_SUMMARIZATION_MODEL_CONFIG" | python3 -c "
import sys, json
try:
    config = json.loads(sys.stdin.read())
    if 'ollama' in config.get('import_path', '').lower():
        print(config.get('model_name', ''))
except: pass
" 2>/dev/null)

    if [ -n "$SUMM_MODEL" ] && [ "$SUMM_MODEL" != "$LLM_MODEL" ]; then
        echo ""
        echo "   Pre-pulling summarization model: ${SUMM_MODEL}..."
        if ollama pull "$SUMM_MODEL" >> "${OLLAMA_LOG_FILE}" 2>&1; then
            echo "   ✓ Summarization model pulled successfully"
        else
            echo "   ⚠ Warning: Failed to pull summarization model ${SUMM_MODEL}"
            echo "     Summarization will fall back to primary model"
        fi
    fi
fi
```

#### 4.3.4 `.env.template` — Add context management env var documentation

**Add this new section after the existing `# System Settings` section:**

```bash
# -----------------------------------------------------------------------------
# Context Management (auto-generated by generate_env.py from experiment YAML)
# -----------------------------------------------------------------------------
# These are typically set via the context_management: section in experiment YAML.
# They can also be set manually here for overrides.

# Archytas: When to trigger conversation history summarization (% of context window)
# ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT=50

# Archytas: Force context window size in tokens (critical for Ollama models)
# ARCHYTAS_CONTEXT_WINDOW_OVERRIDE=64000

# Archytas: Tool output truncation threshold (chars)
# ARCHYTAS_TOOL_SUMMARIZATION_THRESHOLD=1000

# Archytas: Chars to keep when truncating tool output
# ARCHYTAS_TOOL_SNIPPET_SIZE=1000

# Archytas: Max ReAct loop steps per query
# ARCHYTAS_MAX_REACT_STEPS=30

# Archytas: Max errors per ReAct loop
# ARCHYTAS_MAX_ERRORS=3

# Archytas: Separate model for summarization (JSON config dict)
# ARCHYTAS_SUMMARIZATION_MODEL_CONFIG={"import_path":"archytas.models.ollama.OllamaModel","model_name":"llama3.2:3b"}

# Python kernel state budget: max chars per variable
# HARMONIA_STATE_MAX_VAR_SIZE=20000

# Python kernel state budget: total budget as % of context window
# HARMONIA_STATE_BUDGET_PCT=25

# Python kernel state budget: absolute total budget in chars (calculated from PCT)
# HARMONIA_STATE_TOTAL_BUDGET=50000

# Python kernel state budget: type names to exclude (comma-separated)
# HARMONIA_STATE_TYPE_BLACKLIST=SchemaGraph,SimilarityFloodingMatcher

# Python kernel state budget: variable names to always include (comma-separated)
# HARMONIA_STATE_VAR_WHITELIST=df,df_harmonized,result
```

#### 4.3.5 Experiment Config YAMLs — Add `context_management:` section

Add the `context_management:` section to all experiment config YAMLs. For Ollama experiments, always set `context_window_override` to match `llm.context_length`.

**For Ollama-based configs** (e.g., `dou_harmonization_olmo3.yaml`, `dou_harmonization_devstral.yaml`):
```yaml
context_management:
  python_kernel:
    max_variable_size: 20000
    state_budget_pct: 25
  archytas:
    summarization_threshold_pct: 50
    context_window_override: 64000  # Must match llm.context_length
    max_react_steps: 30
```

**For cloud-based configs** (e.g., OpenRouter):
```yaml
context_management:
  archytas:
    summarization_threshold_pct: 50
    max_react_steps: 30
```

Cloud providers have reliable `contextsize()` implementations, so `context_window_override` is not needed. The `python_kernel` section can be omitted to use defaults.

---

## 5. Implementation Order

| Step | What | Codebase | Files | Depends on |
|---|---|---|---|---|
| 1 | Add `context_window_override` to ModelConfig + contextsize() | Archytas | `models/base.py`, `models/ollama.py` | — |
| 2 | Add env var fallback for `summarization_threshold_pct` | Archytas | `models/base.py` | — |
| 3 | Make summarizer constants configurable via env vars | Archytas | `summarizers.py` | — |
| 4 | Add lazy summarization model support | Archytas | `summarizers.py` | — |
| 5 | Fix provider dict to include `summarization_threshold_pct` | Beaker | `lib/config.py` | — |
| 6 | Pass env var overrides through `get_model()` | Beaker | `lib/config.py` | Step 1 |
| 7 | Pass `max_react_steps` and `max_errors` from env to ReActAgent | Beaker | `lib/agent.py` | — |
| 8 | Add `ContextManagementConfig` dataclasses | Harmonia | `src/automation/config.py` | — |
| 9 | Emit context management env vars in generate_env.py | Harmonia | `generate_env.py` | Step 8 |
| 10 | Add OLLAMA_NUM_CTX export, budget calculation, summarization model pre-pull | Harmonia | `exec_apptainer_harmonia.sh` | Step 9 |
| 11 | Add env var documentation | Harmonia | `.env.template` | — |
| 12 | Add `context_management:` to experiment YAMLs | Harmonia | `experiments/.../configs/**/*.yaml` | Step 8 |
| 13 | Rebuild Apptainer container | Harmonia | `.sif` | Steps 1-7 (Archytas + Beaker changes must be installed) |
| 14 | End-to-end test: run experiment with context management | — | — | Step 13 |

**Critical note on Step 13:** The Apptainer container installs Archytas and Beaker from PyPI (`archytas>=1.6.5` via `beaker_kernel>=1.14.0`). To get our Archytas and Beaker changes into the container, we have two options:

**Option A (recommended for development):** Modify the Apptainer `.def` to install Archytas and Beaker from local paths instead of PyPI:
```bash
# In the .def %post section, after installing beaker_kernel from PyPI:
# Reinstall archytas from local patched version
TMPDIR=/var/tmp uv pip install --system --no-cache /path/to/archytas/
# Reinstall beaker-kernel from local patched version
TMPDIR=/var/tmp uv pip install --system --no-cache /path/to/beaker-kernel/
```
These paths must be bind-mounted during build.

**Option B (production):** Publish patched versions to a private PyPI index or install from git.

---

## 6. File Summary

| Action | Codebase | File | Description |
|---|---|---|---|
| **Modify** | Archytas | `archytas/models/base.py` | Add `context_window_override` to `ModelConfig`. Add env var fallback for `summarization_threshold_pct`. Modify `contextsize()` to check override. |
| **Modify** | Archytas | `archytas/models/ollama.py` | Modify `contextsize()` to check `context_window_override` and env var before API query. Add logging. |
| **Modify** | Archytas | `archytas/summarizers.py` | Read `MESSAGE_SUMMARIZATION_THRESHOLD` and `MESSAGE_SUMMARIZATION_SNIPPET_SIZE` from env vars. Add `_get_summarization_model()` for lazy model creation. Modify `default_history_summarizer` and `default_loop_summarizer` to use it. |
| **Modify** | Beaker | `beaker_kernel/lib/config.py` | Add `summarization_threshold_pct: 20` to all static provider dict entries. Add env var passthrough for `context_window_override` and `summarization_threshold_pct` in `get_model()`. |
| **Modify** | Beaker | `beaker_kernel/lib/agent.py` | Read `ARCHYTAS_MAX_REACT_STEPS` and `ARCHYTAS_MAX_ERRORS` from env, pass via kwargs to ReActAgent. |
| **Modify** | Harmonia | `src/automation/config.py` | Add `PythonKernelContextConfig`, `ArchytasContextConfig`, `ContextManagementConfig` dataclasses. Add to `ExperimentConfig` and `from_dict()`. |
| **Modify** | Harmonia | `generate_env.py` | Emit `ARCHYTAS_*` and `HARMONIA_STATE_*` env vars from `context_management:` YAML section. Build `ARCHYTAS_SUMMARIZATION_MODEL_CONFIG` JSON. |
| **Modify** | Harmonia | `exec_apptainer_harmonia.sh` | Export `OLLAMA_NUM_CTX`. Calculate absolute state budget. Pre-pull summarization model for Ollama. |
| **Modify** | Harmonia | `.env.template` | Add documentation for all new context management env vars. |
| **Modify** | Harmonia | `experiments/.../configs/**/*.yaml` | Add `context_management:` section to all experiment configs. |

---

## 7. Verification Checklist

### Archytas unit tests (run outside container, in local venv)

```bash
cd /hpc/compgen/projects/llm_GEO_project/archytas
# After making changes, verify nothing is broken:
python -c "from archytas.models.base import ModelConfig; mc = ModelConfig(model_name='test', context_window_override=64000); print(mc.context_window_override)"
python -c "from archytas.summarizers import MESSAGE_SUMMARIZATION_THRESHOLD; print(f'Threshold: {MESSAGE_SUMMARIZATION_THRESHOLD}')"
# Test env var override:
ARCHYTAS_TOOL_SUMMARIZATION_THRESHOLD=2000 python -c "from archytas.summarizers import MESSAGE_SUMMARIZATION_THRESHOLD; print(f'Threshold: {MESSAGE_SUMMARIZATION_THRESHOLD}')"
```

### Config parsing test (run in Harmonia venv)

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
.venv/bin/python -c "
from src.automation.config import load_config
# Test with a config that has context_management
config = load_config('experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_olmo3.yaml')
print(f'Archytas threshold: {config.context_management.archytas.summarization_threshold_pct}')
print(f'Kernel max var: {config.context_management.python_kernel.max_variable_size}')
print(f'Max react steps: {config.context_management.archytas.max_react_steps}')
"
```

### Env generation test

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
.venv/bin/python generate_env.py --config experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_olmo3.yaml --base-env .env
# Check the generated .env for new vars:
grep "ARCHYTAS_" experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_olmo3_associated.env
grep "HARMONIA_STATE_" experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_olmo3_associated.env
```

### Container build test

After modifying the `.def` to install local Archytas/Beaker:
```bash
# Build and verify the patched packages are installed
apptainer exec harmonia_beaker_LLM_agent_environment_apptainer.sif \
    python3 -c "from archytas.models.base import ModelConfig; print(hasattr(ModelConfig.model_fields, 'context_window_override') or 'context_window_override' in ModelConfig.model_fields)"
```

### End-to-end test

```bash
# Run a short experiment and verify:
grep "OLLAMA_NUM_CTX" logs/*.out           # Should show the env var
grep "ARCHYTAS_" logs/*.out                # Should show context management vars
# Check trace.json for budget metadata:
python3 -c "
import json
with open('results/<experiment_dir>/trace.json') as f:
    trace = json.load(f)
# Look for summarization activity or budget metadata
"
```

---

## 8. Commit Instructions

### Step 1: Archytas changes

```bash
cd /hpc/compgen/projects/llm_GEO_project/archytas
git add archytas/models/base.py archytas/models/ollama.py archytas/summarizers.py
git commit -m "$(cat <<'EOF'
Add configurable context management: context_window_override, env var thresholds, summarization model

Three changes to make context management configurable:

1. Add context_window_override field to ModelConfig and check it in
   contextsize() before querying model APIs. Critical for Ollama models
   where the API may not report context length, silently disabling all
   summarization. Also check ARCHYTAS_CONTEXT_WINDOW_OVERRIDE env var.

2. Make MESSAGE_SUMMARIZATION_THRESHOLD and MESSAGE_SUMMARIZATION_SNIPPET_SIZE
   configurable via ARCHYTAS_TOOL_SUMMARIZATION_THRESHOLD and
   ARCHYTAS_TOOL_SNIPPET_SIZE env vars (current values as defaults).

3. Add lazy summarization model support: if ARCHYTAS_SUMMARIZATION_MODEL_CONFIG
   env var is set (JSON dict with import_path + model_name), create a separate
   model instance for summarization. Falls back to primary model when unset.

4. Add env var fallback (ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT) for the
   summarization threshold percentage when not set via ModelConfig.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

### Step 2: Beaker changes

```bash
cd /hpc/compgen/projects/llm_GEO_project/beaker-kernel
git add beaker_kernel/lib/config.py beaker_kernel/lib/agent.py
git commit -m "$(cat <<'EOF'
Fix summarization_threshold_pct flow and add agent context management env vars

1. Add summarization_threshold_pct to all static provider dict entries so it
   actually flows through Config.get_model() to ModelConfig (was defined on
   LLM_Service_Provider dataclass but missing from the static defaults).

2. Pass ARCHYTAS_CONTEXT_WINDOW_OVERRIDE and ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT
   env vars through get_model() into the config dict.

3. Read ARCHYTAS_MAX_REACT_STEPS and ARCHYTAS_MAX_ERRORS from env vars in
   BeakerAgent.__init__ and pass to ReActAgent via kwargs.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

### Step 3: Harmonia changes

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
git add src/automation/config.py generate_env.py exec_apptainer_harmonia.sh .env.template
git add experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/*.yaml
git add experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/*.yaml
git commit -m "$(cat <<'EOF'
Add comprehensive context management configuration

New context_management: section in experiment YAML configs with two subsections:

- python_kernel: kernel state budget enforcement (max_variable_size,
  state_budget_pct, type_blacklist, var_whitelist)
- archytas: agent/model context management (summarization_threshold_pct,
  context_window_override, max_react_steps, max_errors, tool output
  truncation, summarization_model)

Changes:
- config.py: Add PythonKernelContextConfig, ArchytasContextConfig,
  ContextManagementConfig dataclasses with parsing
- generate_env.py: Emit ARCHYTAS_* and HARMONIA_STATE_* env vars from
  context_management YAML section, build summarization model JSON config
- exec_apptainer_harmonia.sh: Export OLLAMA_NUM_CTX alongside
  OLLAMA_CONTEXT_LENGTH, calculate absolute state budget from percentage,
  pre-pull Ollama summarization model if configured
- .env.template: Document all new context management env vars
- Experiment YAMLs: Add context_management section (Ollama configs include
  context_window_override matching llm.context_length)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Appendix A: Complete Env Var Reference

| Env var | Source | Read by | Default |
|---|---|---|---|
| `ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT` | generate_env.py from `context_management.archytas.summarization_threshold_pct` | Beaker config.py `get_model()` → ModelConfig; Archytas `base.py` (fallback) | 50 |
| `ARCHYTAS_CONTEXT_WINDOW_OVERRIDE` | generate_env.py from `context_management.archytas.context_window_override` | Beaker config.py `get_model()` → ModelConfig; Archytas `base.py` + `ollama.py` (fallback) | None |
| `ARCHYTAS_TOOL_SUMMARIZATION_THRESHOLD` | generate_env.py from `context_management.archytas.tool_output_summarization_threshold` | Archytas `summarizers.py` (module-level) | 1000 |
| `ARCHYTAS_TOOL_SNIPPET_SIZE` | generate_env.py from `context_management.archytas.tool_output_snippet_size` | Archytas `summarizers.py` (module-level) | 1000 |
| `ARCHYTAS_MAX_REACT_STEPS` | generate_env.py from `context_management.archytas.max_react_steps` | Beaker `agent.py` → ReActAgent kwargs | None (unlimited) |
| `ARCHYTAS_MAX_ERRORS` | generate_env.py from `context_management.archytas.max_errors` | Beaker `agent.py` → ReActAgent kwargs | 3 |
| `ARCHYTAS_SUMMARIZATION_MODEL_CONFIG` | generate_env.py (JSON built from `context_management.archytas.summarization_model` + `summarization_model_provider`) | Archytas `summarizers.py` `_get_summarization_model()` | None (use primary model) |
| `LLM_MAX_TOKENS` | generate_env.py from `context_management.archytas.max_tokens` | `LiteLLMModel.auth()` (already exists) | 4096 |
| `HARMONIA_STATE_MAX_VAR_SIZE` | generate_env.py from `context_management.python_kernel.max_variable_size` | FETCH_STATE_CODE patch (in kernel) | 20000 |
| `HARMONIA_STATE_BUDGET_PCT` | generate_env.py from `context_management.python_kernel.state_budget_pct` | exec_apptainer_harmonia.sh (for budget calc) | 25 |
| `HARMONIA_STATE_TOTAL_BUDGET` | Calculated by exec_apptainer_harmonia.sh from PCT × context_length | FETCH_STATE_CODE patch (in kernel) | 50000 |
| `HARMONIA_STATE_TYPE_BLACKLIST` | generate_env.py from `context_management.python_kernel.type_blacklist` (comma-separated) | FETCH_STATE_CODE patch (in kernel) | SchemaGraph,SimilarityFloodingMatcher,... |
| `HARMONIA_STATE_VAR_WHITELIST` | generate_env.py from `context_management.python_kernel.var_whitelist` (comma-separated) | FETCH_STATE_CODE patch (in kernel) | df,df_harmonized,result,... |
| `OLLAMA_NUM_CTX` | exec_apptainer_harmonia.sh (copies from OLLAMA_CONTEXT_LENGTH) | Ollama server (server-level default for /api/chat) | Not set |

## Appendix B: Relationship to Previous Plan

The `25_02_2026_2238_fix_context_issues.md` plan defined two fixes:

- **Fix 1 (Ollama num_ctx passthrough + VRAM estimation):** Unchanged. Implement as written in that plan. The `OLLAMA_NUM_CTX` export is also included in this plan's `exec_apptainer_harmonia.sh` changes (section 4.3.3) for completeness.

- **Fix 2 (FETCH_STATE_CODE kernel state budget):** The *mechanism* (inline patch in the Apptainer def) is unchanged. The *configuration structure* is superseded: instead of a flat `context_management:` section, the kernel state budget config is now under `context_management.python_kernel:`. The `ContextManagementConfig` dataclass is now subdivided into `PythonKernelContextConfig` + `ArchytasContextConfig`.

- **Fix 3 (this plan):** Everything in section 4 of this document is new.
