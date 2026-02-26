# Context Management Between Beaker and Archytas

**Date:** 25 February 2026
**Purpose:** Comprehensive reference on how context flows between the Beaker kernel and Archytas agent framework, where intervention points exist, and what strategies are available for managing context size.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Beaker: Kernel State Serialization (FETCH_STATE_CODE)](#2-beaker-kernel-state-serialization)
3. [Beaker → Archytas: The Auto-Context Bridge](#3-beaker--archytas-the-auto-context-bridge)
4. [Archytas: Message Accumulation & Chat History](#4-archytas-message-accumulation--chat-history)
5. [Archytas: Summarization System](#5-archytas-summarization-system)
6. [Archytas → LLM: Model Adapters & Token Accounting](#6-archytas--llm-model-adapters--token-accounting)
7. [Ollama: Context Length Configuration](#7-ollama-context-length-configuration)
8. [Intervention Points for Context Size Control](#8-intervention-points-for-context-size-control)
9. [Context Management Strategies (Literature & Practice)](#9-context-management-strategies)
10. [References](#10-references)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXPERIMENT FLOW                              │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────────────┐ │
│  │ Python Kernel │───>│   Beaker     │───>│      Archytas          │ │
│  │ (Jupyter)     │    │   Server     │    │   (Agent Framework)    │ │
│  │               │    │              │    │                        │ │
│  │ - Variables   │    │ - Runs       │    │ - Chat History         │ │
│  │ - Modules     │    │   FETCH_     │    │ - Summarization        │ │
│  │ - Functions   │    │   STATE_CODE │    │ - Token Estimation     │ │
│  │ - Classes     │    │ - Formats as │    │ - ReAct Loop           │ │
│  │               │    │   auto_ctx   │    │                        │ │
│  └──────────────┘    └──────────────┘    └────────┬───────────────┘ │
│                                                    │                 │
│                                          ┌────────▼───────────────┐ │
│                                          │   LLM Provider API     │ │
│                                          │                        │ │
│                                          │ - Ollama /api/chat     │ │
│                                          │ - OpenRouter            │ │
│                                          │ - OpenAI               │ │
│                                          └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow Per Turn

```
1. User/Automation sends message
       │
2. Beaker executes FETCH_STATE_CODE in kernel
       │ Returns: {modules, variables, functions, classes} as JSON
       │
3. Beaker formats state as Markdown + JSON code block (auto_context)
       │
4. Archytas assembles message list:
       │   [system_prompt, auto_context, summaries, raw_messages]
       │
5. Archytas estimates tokens
       │   If > summarization_threshold → trigger summarization
       │
6. Archytas sends messages to LLM via model adapter
       │   (ChatOllama, OpenAI, etc.)
       │
7. LLM responds → Archytas records in chat_history
       │
8. If ReAct loop: execute tool calls → kernel runs code → go to step 2
       │
9. Post-loop: summarize tool outputs if large
```

---

## 2. Beaker: Kernel State Serialization

### FETCH_STATE_CODE

**File:** `.venv/lib/python3.11/site-packages/beaker_kernel/subkernels/python.py` (lines 27–124)

This is a Python code string that Beaker executes *inside the Jupyter kernel* after each turn. It introspects the kernel namespace and returns a JSON dictionary.

### What It Serializes

```python
_result = {
    "modules": {},      # Imported modules: {name: {path, full_name}}
    "variables": {},    # User variables: {name: {value, type, size, truncated?}}
    "functions": {},    # Defined functions: {name: {docstring, signature}}
    "classes": {}       # Defined classes: {name: {docstring}}
}
```

### Existing Truncation Rules

| Data Type | Truncation | Lines |
|-----------|-----------|-------|
| DataFrames | `.head()` (first 5 rows) | ~96–99 |
| Sequences (list, tuple, set) | First 99 items, `truncated: True` flag | ~100–107 |
| Private vars (`_name`) | Skipped entirely | ~78 |
| Builtins (`In`, `Out`, etc.) | Skipped | ~80–82 |
| Non-serializable objects | Stringified via `_SubkernelStateEncoder` | ~119 |

### What Is NOT Limited

- **Total output size**: No byte/character budget. If 50 variables each serialize to 20KB, the total is 1MB.
- **Individual variable size**: A single dict with 10,000 nested entries will be fully serialized (only top-level collections are truncated to 99 items).
- **Nested structures**: The 99-item limit applies only at the top level. A dict with 5 keys, each containing a list of 100,000 items, passes through.
- **String values**: No character limit on string variable values.

### The GDC Schema Problem

When `bdi.match_schema(df, target="gdc", method="similarity_flooding")` runs, it loads the full GDC schema vocabulary into kernel memory as deeply nested Python dicts/lists. These become regular variables in `locals()`. FETCH_STATE_CODE serializes them all, producing ~1M tokens of JSON. The 99-item truncation doesn't help because:
- The schema is structured as nested dicts, not flat lists
- Each top-level key maps to a complex nested object
- The encoder faithfully serializes all nested content

---

## 3. Beaker → Archytas: The Auto-Context Bridge

### State Retrieval

**File:** `.venv/lib/python3.11/site-packages/beaker_kernel/lib/context.py` (lines 460–465)

```python
async def get_subkernel_state(self):
    fetch_state_code = self.subkernel.FETCH_STATE_CODE
    state = await self.evaluate(fetch_state_code)
    for warning in state["stderr_list"]:
        logger.warning(warning)
    return state["return"]
```

### Auto-Context Formatting

**File:** `.venv/lib/python3.11/site-packages/beaker_kernel/lib/context.py` (lines 210–252)

```python
async def auto_context(self):
    parts = []
    # ... other context parts ...
    if beaker_config.send_kernel_state:
        kernel_state = await self.get_subkernel_state()
        if kernel_state:
            parts.append(f"""## Kernel state
```application/json
{json.dumps(kernel_state)}
```""")
    return "\n\n".join(parts)
```

The serialized kernel state becomes a **Markdown section with an embedded JSON code block**. This entire string becomes a single `AutoContextMessage` in Archytas.

### Registration with Archytas

**File:** `.venv/lib/python3.11/site-packages/archytas/agent.py` (lines 212–234)

```python
self.chat_history.auto_context_message = AutoContextMessage(
    default_content=default_content,
    content_updater=content_updater,  # ← The auto_context() callable
    model=self.model,
)
```

The `AutoContextMessage` is:
- Updated **before every LLM call** via `update_content()`
- Positioned **after the system prompt, before conversation history**
- A `SystemMessage` subclass — it is NOT subject to summarization

---

## 4. Archytas: Message Accumulation & Chat History

### ChatHistory Structure

**File:** `.venv/lib/python3.11/site-packages/archytas/chat_history.py` (lines 126–182)

```python
class ChatHistory:
    raw_records: list[MessageRecord]          # All messages
    summaries: list[SummaryRecord]            # Compressed message groups
    system_message: Optional[MessageRecord]   # System prompt
    auto_context_message: Optional[AutoContextMessage]  # Kernel state
    summarization_threshold: int              # Token trigger
    tool_token_estimate: int                  # Tool definitions size
    base_tokens: int                          # Overhead
```

### Message List Assembly

**File:** `.venv/lib/python3.11/site-packages/archytas/chat_history.py` (lines 393–420)

`records()` returns messages in this order:

```
1. system_message           (SystemMessage — never summarized)
2. auto_context_message     (AutoContextMessage — never summarized)
3. summaries                (SummaryRecord — compressed prior turns)
4. user_preamble            (if present)
5. raw_records              (unsummarized recent messages)
```

### Message Recording

**File:** `.venv/lib/python3.11/site-packages/archytas/chat_history.py` (lines 459–467)

```python
def add_message(self, message, token_count=None):
    record = MessageRecord(
        message=message,
        token_count=token_count,
        react_loop_id=self.current_loop_id
    )
    self.raw_records.append(record)
    return record
```

---

## 5. Archytas: Summarization System

### Two-Tier Summarization

#### Tier 1: Loop Summarization (Tool Outputs)

**File:** `.venv/lib/python3.11/site-packages/archytas/summarizers.py` (lines 84–105)

After each ReAct loop, tool outputs exceeding `MESSAGE_SUMMARIZATION_THRESHOLD` (1000 chars) are truncated to the first 1000 characters.

#### Tier 2: History Summarization (Conversation Compression)

**File:** `.venv/lib/python3.11/site-packages/archytas/summarizers.py` (lines 108–177)

When total tokens exceed the summarization threshold, the oldest messages are bundled and sent to the LLM for summarization. The LLM produces a compressed `SummaryRecord` that replaces those messages.

### Summarization Threshold

**File:** `.venv/lib/python3.11/site-packages/archytas/models/base.py` (lines 121–144)

```python
DEFAULT_SUMMARIZATION_RATIO = 0.5  # 50% of context window

@property
def summarization_threshold(self):
    context_size = self.contextsize(self.model_name)
    # Use explicit threshold, percentage, or default 50%
    return int(context_size * summarization_ratio)
```

### What Gets Summarized vs. What Doesn't

| Message Type | Summarized? |
|-------------|------------|
| System prompt | Never |
| AutoContextMessage (kernel state) | **Never** |
| SummaryRecords (already summarized) | Never |
| User messages | Yes |
| Assistant messages | Yes |
| Tool call/result messages | Yes (after loop summarization) |

### ContextWindowExceededError Recovery

**File:** `.venv/lib/python3.11/site-packages/archytas/react.py` (lines 519–529)

```python
except ContextWindowExceededError:
    history_summarization_task = self.chat_history.history_summarization_task
    if not history_summarization_task:
        history_summarization_task = await self.chat_history.summarize_history(
            agent=self, in_loop=True
        )
    if history_summarization_task:
        await history_summarization_task
    reaction = await self.execute()  # Retry with compressed history
```

### Why Summarization Doesn't Fix the GDC Schema Problem

The auto-context message (containing serialized kernel state) is a `SystemMessage` subtype and is **excluded from summarization**. Even if all conversation history were summarized to zero tokens, the auto-context alone can be ~1M tokens — exceeding the entire context window. Archytas's summarizer operates on *conversation history*, not on the *kernel state payload*.

---

## 6. Archytas → LLM: Model Adapters & Token Accounting

### Ollama Adapter

**File:** `.venv/lib/python3.11/site-packages/archytas/models/ollama.py`

```python
# Context size discovery (lines 36-48)
@lru_cache()
def contextsize(self, model_name=None):
    show_response = self.model._client.show(self.model_name)
    model_info = show_response.modelinfo
    model_arch = model_info["general.architecture"]
    context_length = model_info[f"{model_arch}.context_length"]
    return int(context_length)
```

### ChatOllama (LangChain-Ollama)

**File:** `.venv/lib/python3.11/site-packages/langchain_ollama/chat_models.py`

```python
# num_ctx field definition (lines 572-576)
num_ctx: int | None = None  # Default: None → Ollama uses its own default (4096)

# Chat params building (lines 717-785)
def _chat_params(self, messages, stop=None, **kwargs):
    options_dict = {
        "num_ctx": self.num_ctx,  # ← Only sent if set on instance
        # ... other options ...
    }
    params = {
        "messages": ollama_messages,
        "options": options_dict,
        # ...
    }
```

**Key finding:** `num_ctx` is only included in `/api/chat` requests if explicitly set on the `ChatOllama` instance. By default it's `None`, which means Ollama falls back to 4096.

### Token Estimation

**File:** `.venv/lib/python3.11/site-packages/archytas/chat_history.py` (lines 317–391)

```python
token_estimate = (
    base_tokens +
    tool_token_estimate +
    auto_context_message_token_estimate +
    sum(record.token_count for record in records)
)
```

**Note:** For Ollama models, `get_num_tokens_from_messages()` is not accurately implemented — it returns approximate counts. Actual usage comes from response metadata.

---

## 7. Ollama: Context Length Configuration

### The num_ctx Disconnect

There are **three separate places** where context length can be configured for Ollama, and they don't propagate to each other:

```
1. OLLAMA_CONTEXT_LENGTH in .env
   → Read by exec_apptainer_harmonia.sh
   → Passed to /api/generate (pre-load only)
   → NOT passed to /api/chat

2. ChatOllama(num_ctx=N)
   → Passed to /api/chat via options dict
   → NOT set by Harmonia's codebase (defaults to None → 4096)

3. OLLAMA_NUM_CTX environment variable
   → Read by Ollama server at startup
   → Applies globally to all /api/chat calls
   → NOT currently set by exec_apptainer_harmonia.sh
```

### Ollama's Default Behavior

- Default `num_ctx` = 4096 tokens
- When prompt exceeds `num_ctx`, Ollama **silently truncates** from the start
- Warning only appears in Ollama's own log: `msg="truncating input prompt" limit=4096 prompt=N`
- No error is raised, no exception — the LLM just receives a clipped prompt

### Relevant Ollama Source

The truncation happens in `runner.go` (Ollama's Go codebase). The warning includes:
- `limit`: the `num_ctx` value
- `prompt`: total tokens in the incoming prompt
- `keep`: tokens preserved at the start (system prompt protection)
- `new`: resulting prompt size after truncation

---

## 8. Intervention Points for Context Size Control

```
                    INTERVENTION POINTS

[Python Kernel]
    │
    ▼
[FETCH_STATE_CODE]  ◄─── POINT A: Cap serialized state size
    │                     - Per-variable size limit
    │                     - Total budget limit
    │                     - Type-based blacklisting
    ▼
[BeakerContext.auto_context()]  ◄─── POINT B: Truncate auto-context
    │                                 - Measure JSON size before embedding
    │                                 - Drop large sections
    ▼
[ChatHistory.records()]  ◄─── POINT C: Pre-flight token check
    │                          - Estimate total before sending
    │                          - Refuse if over budget
    ▼
[Agent.execute()]  ◄─── POINT D: Archytas summarization
    │                    - Already exists (50% threshold)
    │                    - Cannot compress auto-context
    ▼
[Model.ainvoke()]  ◄─── POINT E: Model adapter config
    │                    - Pass num_ctx for Ollama
    │                    - Use middle-out for OpenRouter
    ▼
[Ollama /api/chat]  ◄─── POINT F: Server-level config
                          - OLLAMA_NUM_CTX env var
                          - Per-model Modelfile
```

### Which Points Address Which Problems

| Problem | Root Cause | Best Intervention Point |
|---------|-----------|------------------------|
| Ollama silent truncation (3H) | num_ctx not passed | **Point E** (model adapter) or **Point F** (env var) |
| GDC schema explosion (3E) | Kernel state too large | **Point A** (FETCH_STATE_CODE) |
| Gradual context growth | Conversation history accumulates | **Point D** (already handled by Archytas) |
| Large tool outputs | Code execution returns large data | **Point D** (loop summarization, 1000 char limit) |

---

## 9. Context Management Strategies

### Strategy 1: Truncation (Drop Oldest)

Remove the oldest messages from conversation history, keeping only the N most recent turns plus the system prompt.

**Pros:** Simple, deterministic, no LLM calls needed.
**Cons:** Loses important early context (task description, initial data exploration).

**Implementations:**
- LangChain `ConversationBufferWindowMemory` (keeps last k turns)
- Strands Agents `SlidingWindowConversationManager`

### Strategy 2: Summarization (Compress History)

Use the LLM itself to summarize older conversation turns into a compact representation.

**Pros:** Preserves semantic content, context-aware compression.
**Cons:** Costs LLM calls, may lose details, adds latency.

**Implementations:**
- Archytas built-in `default_history_summarizer` (already present)
- LangChain `ConversationSummaryBufferMemory` (hybrid: summary + recent raw)
- LlamaIndex `ChatSummaryMemoryBuffer`
- Strands Agents `SummarizingConversationManager`

### Strategy 3: Middle-Out (Drop Middle, Keep Edges)

Remove content from the middle of the prompt, keeping the system prompt + first turns and the most recent turns. Exploits the "lost in the middle" phenomenon where LLMs attend less to middle content.

**Pros:** Preserves both initial instructions and recent state.
**Cons:** Lossy, may miss critical mid-conversation decisions.

**Implementations:**
- OpenRouter's `transforms: ["middle-out"]` parameter
- For Anthropic models: keeps first half + last half of messages (up to 1000-message limit)

### Strategy 4: Retrieval-Augmented Context (RAG)

Store all conversation history externally, retrieve only relevant portions per query using semantic similarity.

**Pros:** Scales to unlimited history, retrieves what's relevant.
**Cons:** Complex infrastructure, retrieval may miss important context.

**Implementations:**
- LlamaIndex `VectorMemory`
- MemGPT/Letta archival memory tier

### Strategy 5: Virtual Context Management (MemGPT)

Inspired by OS memory hierarchies: fast "core memory" (in-context) + slow "archival memory" (external storage). The LLM decides what to keep in-context and what to archive.

**Pros:** Self-managed, adaptive, theoretically unbounded context.
**Cons:** Complex, requires LLM to learn memory management, adds overhead.

**Implementations:**
- MemGPT/Letta (`letta-ai/letta` on GitHub)

### Strategy 6: Prompt Compression (LLMLingua)

Use a smaller model to compress the prompt tokens, removing redundant or low-information tokens while preserving semantics.

**Pros:** High compression ratios (up to 20x), works on any content.
**Cons:** Requires separate model, may distort structured data (JSON, code).

**Implementations:**
- Microsoft LLMLingua / LLMLingua-2 (`microsoft/LLMLingua` on GitHub)

### Strategy 7: State Serialization Budget (Custom — For Beaker)

Cap the serialized kernel state at a fixed byte/token budget. Drop or placeholder large variables. This is specific to the Beaker architecture where kernel state is injected into context.

**Pros:** Directly addresses the root cause for Beaker-specific explosions.
**Cons:** May lose important state info. Requires careful threshold tuning.

**Implementations:** None existing — needs custom implementation in FETCH_STATE_CODE or at the auto-context layer.

### Strategy 8: Adaptive Focus Memory

Assign each past message to a fidelity level (FULL, COMPRESSED, or PLACEHOLDER) based on relevance to the current task.

**Pros:** Flexible, preserves important messages in full.
**Cons:** Requires relevance scoring, adds complexity.

**Reference:** arXiv:2511.12712 (Adaptive Focus Memory for Language Models)

---

## 10. References

### Frontier Model Provider Documentation

- [Context Windows - Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/context-windows) — Context window sizes, context rot phenomenon, premium pricing above 200K tokens
- [Context Summarization with Realtime API (OpenAI Cookbook)](https://cookbook.openai.com/examples/context_summarization_with_realtime_api) — Two strategies: context trimming and context summarization with Python implementation
- [Context Engineering - Short-Term Memory Management (OpenAI Agents SDK)](https://cookbook.openai.com/examples/agents_sdk/session_memory) — Session memory management including `/responses/compact` endpoint
- [Long Context | Gemini API](https://ai.google.dev/gemini-api/docs/long-context) — Gemini's up to 2M token context, context caching for static content
- [Message Transforms | OpenRouter](https://openrouter.ai/docs/guides/features/message-transforms) — "Middle-out" transform: compresses by removing from middle of prompt

### Academic Papers

- [LLMLingua: Compressing Prompts for Accelerated Inference](https://arxiv.org/abs/2310.05736) — Up to 20x prompt compression with minimal performance loss (EMNLP 2023)
- [LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios](https://arxiv.org/abs/2310.06839) — Extension for long contexts, 21.4% performance boost with 4x fewer tokens (ACL 2024)
- [LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression](https://arxiv.org/abs/2403.12968) — BERT-level encoder for 3–6x faster compression (ACL 2024)
- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) — Virtual context management with two-tier memory hierarchy
- [ACON: Optimizing Context Compression for Long-Horizon LLM Agents](https://arxiv.org/abs/2510.00615) — 26–54% memory reduction for multi-step agent tasks
- [Recursively Summarizing Enables Long-Term Dialogue Memory in LLMs](https://arxiv.org/abs/2308.15022) — Recursive dialogue summarization
- [Leave No Context Behind: Efficient Infinite Context Transformers with Infini-attention](https://arxiv.org/abs/2404.07143) — Google's compressive memory in vanilla attention
- [Adaptive Focus Memory for Language Models](https://arxiv.org/abs/2511.12712) — FULL/COMPRESSED/PLACEHOLDER fidelity levels per message
- [A Survey on the Memory Mechanism of LLM-based Agents](https://dl.acm.org/doi/10.1145/3748302) — Comprehensive survey: retrieval-based, summarization-based, KV cache compression
- [Sliding Window Attention Training for Efficient LLMs](https://arxiv.org/abs/2502.18845) — SWAT: sigmoid + ALiBi + RoPE for sliding window compression

### GitHub Repositories

- [letta-ai/letta (formerly MemGPT)](https://github.com/letta-ai/letta) — Virtual context management with core + archival memory tiers
- [microsoft/LLMLingua](https://github.com/microsoft/LLMLingua) — Prompt compression (LLMLingua, LongLLMLingua, LLMLingua-2)
- [jataware/beaker-kernel](https://github.com/jataware/beaker-kernel) — Beaker kernel with FETCH_STATE_CODE
- [jataware/archytas](https://github.com/jataware/archytas) — Agent framework with ReAct loop and summarization
- [LangChain ConversationSummaryBufferMemory](https://python.langchain.com/api_reference/langchain/memory/langchain.memory.summary_buffer.ConversationSummaryBufferMemory.html) — Hybrid summary + buffer memory
- [LlamaIndex Memory Module](https://docs.llamaindex.ai/en/stable/module_guides/deploying/agents/memory/) — ChatMemoryBuffer, ChatSummaryMemoryBuffer, VectorMemory

### Ollama Documentation

- [Ollama FAQ — Context Window](https://docs.ollama.com/faq) — Default 4096, configurable via `num_ctx` or `OLLAMA_CONTEXT_LENGTH` env var
- [Ollama Issue #8099 — Silent Prompt Truncation](https://github.com/ollama/ollama/issues/8099) — Documents silent truncation when prompt exceeds num_ctx
- [Ollama Issue #14259 — Silent Chat History Truncation](https://github.com/ollama/ollama/issues/14259) — Truncation without user-visible indication
- [Ollama Issue #10829 — OLLAMA_CONTEXT_LENGTH vs num_ctx](https://github.com/ollama/ollama/issues/10829) — Disconnect between env var and runtime behavior

### General Overviews

- [LLM Powered Autonomous Agents (Lil'Log — Lilian Weng)](https://lilianweng.github.io/posts/2023-06-23-agent/) — Foundational post on agent architectures including memory components
- [Context Window Management Strategies (Maxim)](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/) — Overview of truncation, summarization, RAG, sliding windows, hybrid approaches
- [Conversational Memory for LLMs with LangChain (Pinecone)](https://www.pinecone.io/learn/series/langchain/langchain-conversational-memory/) — Tutorial covering all LangChain memory types
