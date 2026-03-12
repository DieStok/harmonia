# Platform Comparison: Beaker-dev vs Streamlit vs OpenWebUI

**Date:** 25 February 2026, 19:42
**Context:** Evaluating whether to stay with Beaker-dev, migrate to Streamlit (as bdi-kit v0.9 has done), or adopt OpenWebUI — with emphasis on REPL/code execution capabilities needed for CodeAct agents and recursive LLMs.

---

## Table of Contents

1. [Background: Why This Matters](#1-background-why-this-matters)
2. [BDI-Kit v0.9: The Streamlit Migration](#2-bdi-kit-v09-the-streamlit-migration)
3. [What Harmonia Currently Uses (Beaker-dev)](#3-what-harmonia-currently-uses-beaker-dev)
4. [Streamlit: Capabilities and Limitations](#4-streamlit-capabilities-and-limitations)
5. [OpenWebUI: Capabilities and Architecture](#5-openwebui-capabilities-and-architecture)
6. [CodeAct Agents and Recursive LLMs](#6-codeact-agents-and-recursive-llms)
7. [Alternative REPL/Sandbox Approaches](#7-alternative-replsandbox-approaches)
8. [Platform Comparison Matrix](#8-platform-comparison-matrix)
9. [Migration Cost Analysis](#9-migration-cost-analysis)
10. [Recommendation](#10-recommendation)

---

## 1. Background: Why This Matters

Harmonia needs a platform that supports two experimental paradigms:

| Paradigm | How it works | Execution needs |
|---|---|---|
| **Tool-calling agent** (ReAct) | LLM selects pre-defined tools via JSON, one at a time, with reasoning steps between | Tool dispatch layer, tool implementations, result formatting |
| **Code-only agent** (CodeAct) | LLM writes Python code that composes tools, processes data, handles errors | Persistent Python REPL with pre-loaded tools as importable functions |

Additionally, testing **recursive LLMs** ([Recursive Language Models paper](https://arxiv.org/html/2512.24601v1)) — where the LLM writes code that calls back to an LLM — requires a REPL that can make outbound API calls and capture results as Python objects.

The trigger for this investigation is that [bdi-kit v0.9](https://github.com/VIDA-NYU/bdi-kit) has completely dropped [Beaker-dev](https://github.com/jataware/beaker-kernel) in favour of [Streamlit](https://docs.streamlit.io/develop/concepts/architecture) + [MCP](https://modelcontextprotocol.io/), raising the question of whether Harmonia should follow suit or consider alternatives like [OpenWebUI](https://github.com/open-webui/open-webui).

---

## 2. BDI-Kit v0.9: The Streamlit Migration

BDI-Kit v0.9 (released 2025-11-17, [CHANGELOG](https://github.com/VIDA-NYU/bdi-kit/blob/main/CHANGELOG.md)) has **completely removed Beaker-dev** and replaced it with a Streamlit + [MCP](https://modelcontextprotocol.io/) architecture.

### New architecture

Two components:

1. **MCP Server** (`bdikit/mcp_server.py`): A [FastMCP](https://github.com/jlowin/fastmcp) server exposing 9 predefined tools:
   - `match_schema`, `rank_schema_matches`, `match_values`, `rank_value_matches`
   - `preview_domain`, `materialize_mapping`
   - `update_schema_matching`, `update_value_matching`
   - `get_available_schema_matching_algorithms`, `get_available_value_matching_algorithms`
   - Entry point: `bdikit-mcp --llm <model>`

2. **Streamlit Frontend** (`bdikit/chatbot.py`): A conversational UI using [LangGraph](https://langchain-ai.github.io/langgraph/) ReAct agents:
   - LangGraph agent runs in a background thread
   - Communicates with UI thread via Python `queue.Queue`
   - LLM (via [`ChatLiteLLM`](https://docs.litellm.ai/)) decides which MCP tools to call
   - Entry point: `bdikit-chatbot --llm <model>`

### Key design decisions in bdi-kit v0.9

- **The LLM never generates code.** It exclusively calls predefined MCP tools with typed parameters.
- **No sandbox needed.** Because the LLM can only invoke 9 predefined tools validated by Pydantic models, there is no arbitrary code execution.
- **No REPL.** Streamlit is used purely as a presentation layer for tool-call results.
- Dependencies: [`mcp[cli]`](https://modelcontextprotocol.io/), [`streamlit`](https://docs.streamlit.io/), [`langchain`](https://python.langchain.com/docs/introduction/), [`langchain-litellm`](https://docs.litellm.ai/), [`langchain-mcp-adapters`](https://github.com/langchain-ai/langchain-mcp-adapters)

### What this means for Harmonia

BDI-kit's migration to Streamlit makes sense for their use case (structured tool calling for data harmonization) but does **not** address Harmonia's need for a code execution environment. Their architecture is tool-calling only, with no provision for CodeAct or recursive agents.

---

## 3. What Harmonia Currently Uses (Beaker-dev)

### Architecture overview

[Beaker-dev](https://github.com/jataware/beaker-kernel) ([docs](https://jataware.github.io/beaker-kernel/)) provides a Jupyter-protocol agent runtime inside an [Apptainer](https://apptainer.org/docs/user/latest/) container:

```
User / run_experiment.py (WebSocket client)
        |
  Beaker Kernel (proxy layer, message inspection, AI agent via Archytas)
        |
  Python 3.11 Subkernel (actual code execution, persistent state)
```

### Startup and configuration

- **`exec_apptainer_harmonia.sh`** starts Beaker inside Apptainer via `beaker dev watch --ip 0.0.0.0 --port $PORT`
- Workspace bindings: `/workspace/data` (read-only datasets), `/workspace/results` (read-write output)
- Environment variables from `.env` file (LLM credentials, settings)
- WebSocket max message size increased from 4MB to 20MB for large model responses
- For local LLMs: dynamic per-job Ollama isolation (unique port `11434 + 1 + (SLURM_JOB_ID % 200)`, per-job `OLLAMA_HOME`)

### Two run modes

1. **Normal mode**: `beaker dev watch` runs interactively, user connects via browser
2. **Monitor mode**: `--monitor` flag starts Beaker in background + launches `run_manual_experiment.py` to passively capture all interactions

### Capabilities actually used

**Persistent Python REPL (subkernel):**
- LLM agent writes Python code
- Beaker executes in Python 3.11 subkernel
- Output captured as `code_cell` response type
- Access to pandas, numpy, bdi-kit libraries
- Variables, imports, and loaded dataframes persist across turns

**Tool use (via [Archytas](https://github.com/jataware/archytas)):**
- `match_schema()` — maps columns to target schema
- `top_matches()` — returns 10 alternative column mappings
- `match_values()` — finds value mappings between columns
- `materialize_mapping()` — creates harmonized output table
- `get_gdc_acceptable_values()` — lists valid values for GDC columns
- Each tool generates Python code from Jinja2 templates and executes via `agent.context.evaluate(code)`

**Two contexts (agent modes):**
- `bdikit_context` — full data harmonization context with domain tools
- `code_context` — minimal ReAct context with only the generic `run_code` tool (NOT CodeAct — the LLM still uses structured JSON tool calls via Archytas, not natural code blocks)

### LLM-Beaker interaction protocol

```
Client sends:     msg_type: "llm_request",  content: {"request": "..."}
                         |
Beaker processes:  LLM reads system prompt from auto_context()
                   LLM generates response (text or tool call)
                   If tool: execute tool code in Python kernel
                         |
Client receives:   llm_response (LLM text)
                   code_cell (Python code)
                   stream (stdout/stderr)
                   thought (agent reasoning)
                   error (exceptions)
                   execute_reply (final)
```

### Tracing and monitoring

- **`trace.json`**: Full message history with timestamps, per-turn user/agent messages, tool calls, raw Jupyter WebSocket messages, experiment metadata (LLM provider/model, timing, status)
- **`conversation.md`**: Human-readable conversation log
- **`.experiment_id`**: JSON metadata linking run_id to logs/config
- Results saved to `results/<experiment_name>_<timestamp>_<run_id>/`
- Post-hoc analysis via `read_and_analyze_logs_and_traces_cli.py` (13 failure-mode categories)

### Apptainer container contents

- Base: Python 3.11
- [`beaker-kernel`](https://github.com/jataware/beaker-kernel) >= 1.14.0 (Jupyter kernel + agent runtime)
- [`litellm`](https://docs.litellm.ai/) (100+ LLM provider support)
- [`langchain-core`](https://python.langchain.com/docs/introduction/) (message type compatibility)
- [`bdi-kit`](https://github.com/VIDA-NYU/bdi-kit) (data harmonization library)
- `bdikit_context` package (built from source, contains agent + tool definitions)
- Bind mounts: datasets (read-only), results (read-write), runtime contexts, source code

---

## 4. Streamlit: Capabilities and Limitations

### What Streamlit can render

Streamlit excels as a presentation layer ([API reference](https://docs.streamlit.io/develop/api-reference)):

- `st.dataframe()` — interactive tables
- `st.plotly_chart()`, `st.altair_chart()`, `st.pyplot()` — charts and plots
- `st.code()` — syntax-highlighted code blocks
- [`st.chat_message()`](https://docs.streamlit.io/develop/api-reference/chat) — conversational UI components
- `st.markdown()` — rich text
- Native support for Plotly, Altair, Matplotlib, Vega-Lite

### The REPL question: No

**Streamlit has no built-in code execution engine, no kernel, no REPL.**

Its [execution model](https://docs.streamlit.io/develop/concepts/architecture) is fundamentally different from Jupyter's:

- Every user interaction (button click, widget change) causes the **entire Python script to rerun from top to bottom**
- There is no persistent interpreter session between interactions
- No ZeroMQ-based message protocol, no execution queue, no cell-by-cell execution
- Variables do not persist unless explicitly stored in [`st.session_state`](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state) or caching mechanisms

### Can you hack a REPL into Streamlit?

**Via `exec()` — technically possible, practically problematic:**

```python
# The exec() pattern
namespace = {"df": st.session_state.df, "pd": pd, "np": np}
exec(llm_generated_code, namespace)
result = namespace.get("result")
st.dataframe(result)
```

Problems with this approach:
1. **No isolation**: Unlike Jupyter kernels (separate processes), `exec()` runs in the same process as the web server. A crash crashes the app. Malicious code has full server access.
2. **No output capture**: Jupyter captures stdout, stderr, display objects, and rich output through its messaging protocol. With `exec()`, you must manually redirect everything.
3. **No interruption**: Jupyter kernels can be interrupted (SIGINT). An infinite loop in `exec()` hangs the server with no way to stop it.
4. **Security**: [PandasAI](https://github.com/sinaptik-ai/pandas-ai) uses this pattern and has had **multiple CVEs** ([CVE-2024-23752](https://vulert.com/vuln-db/CVE-2024-23752)) for remote code execution via prompt injection.
5. **State management**: Across Streamlit reruns, the `exec()` namespace must be carefully persisted in `st.session_state`.

**Via Pyodide (streamlit-execute):**
- Runs Python client-side via WebAssembly in the browser
- Cannot access server-side dataframes, files, or Python packages
- Fundamentally unsuitable for data science workflows

**Via embedded Jupyter kernel:**
- Use [`jupyter_client.AsyncKernelManager`](https://jupyter-client.readthedocs.io/en/stable/) to manage a kernel process
- Streamlit sends code to the kernel and displays results
- This works but requires significant engineering — and at that point you're rebuilding Beaker

### Third-party components

- [**streamlit-code-editor**](https://github.com/bouzidanas/streamlit-code-editor): Syntax highlighting and editing, but does NOT execute code — purely a UI widget
- [**streamlit-jupyter**](https://github.com/ddobrinskiy/streamlit-jupyter): Lets you develop Streamlit apps inside Jupyter notebooks; does NOT give Streamlit access to a Jupyter kernel
- No production-quality project exists that embeds a Jupyter kernel inside a Streamlit app

### Bottom line

Streamlit is a **presentation layer**, not a code execution environment. If your use case requires an LLM to generate and execute arbitrary Python code against in-memory data (as CodeAct and recursive LLMs require), the architecturally sound options are:
1. Use Jupyter/Beaker directly (which already provides this)
2. Use Streamlit as the UI but delegate code execution to a Jupyter kernel running as a separate process

---

## 5. OpenWebUI: Capabilities and Architecture

[OpenWebUI](https://github.com/open-webui/open-webui) ([docs](https://docs.openwebui.com/features/), [getting started](https://docs.openwebui.com/getting-started/)) is a self-hosted AI chat platform (originally "Ollama WebUI") with extensive built-in capabilities. It is a significantly more serious contender than Streamlit for replacing Beaker.

### Code execution — three backends

| Backend | How it works | Isolation | State persistence | Library access | CodeAct viable? |
|---------|-------------|-----------|-------------------|---------------|-----------------|
| **Pyodide** | Python in browser via WebAssembly | Full sandbox | None across calls | Limited (WASM-compiled only) | No |
| **Jupyter** | Server-side IPython kernel | Process-level | Full kernel state | Everything | **Yes** |
| **Open Terminal** | Shell commands in Docker container | Container-level | Filesystem only | Full OS access | Partially |

### How LLMs trigger code execution

Two paradigms:
1. **Manual (button click)**: LLM generates code in a code block; user clicks "Run" to execute
2. **Autonomous (tool call)**: In Native Mode, the LLM has an `execute_code` built-in tool and can autonomously write and run Python code as part of its reasoning — essentially a CodeAct loop out of the box

Additionally, [**safe-code-execution**](https://github.com/EtiennePerot/safe-code-execution) (community project by EtiennePerot) provides [gVisor](https://gvisor.dev/docs/)-sandboxed execution for both Python and Bash. See also the [run_code tool on the OpenWebUI marketplace](https://openwebui.com/t/etienneperot/run_code).

### Tool system

Four categories of tools:

| Type | Description |
|------|-------------|
| **Native Features** | Built-in: `search_web`, `fetch_url`, `execute_code`, `generate_image`, memory, knowledge queries |
| **[Workspace Tools](https://docs.openwebui.com/features/extensibility/plugin/tools/)** | Community Python scripts running inside OpenWebUI |
| **[MCP Servers](https://modelcontextprotocol.io/)** | Standard Model Context Protocol servers |
| **OpenAPI Servers** | REST/OpenAPI web services (like [Open Terminal](https://docs.openwebui.com/features/extensibility/open-terminal/)) |

Two invocation modes:
- **Default Mode (Prompt-based)**: OpenWebUI injects a prompt telling the model what tools are available. Works with any model, including small local ones without native function calling. Slower and less reliable.
- **Native Mode (Agentic)**: Uses the model's built-in function-calling capability. Automatically injects ~30 system tools. Lower latency, higher accuracy. Requires frontier models (GPT-5, Claude 4.5 Sonnet, Gemini 3 Flash).

### Extensibility

- **[Pipe Functions](https://docs.openwebui.com/features/extensibility/plugin/)**: Create custom "models" that appear in the model selector — can combine multiple LLMs, query external APIs, integrate non-AI systems
- **Filter Functions**: Middleware with inlet (pre-process user input) and outlet (post-process LLM output)
- **Action Functions**: Custom clickable buttons beneath chat messages
- **[Pipelines](https://docs.openwebui.com/features/extensibility/pipelines/)** ([GitHub](https://github.com/open-webui/pipelines)): Separate service (Docker container) for heavy/complex processing middleware

### Artifacts

Inspired by Claude.ai's Artifacts ([docs](https://docs.openwebui.com/features/chat-conversations/chat-features/code-execution/artifacts/)):
- Single-page HTML websites (HTML + CSS + JS)
- SVG images
- ThreeJS visualizations, D3.js, Chart.js
- Tailwind CSS supported
- Rendered in sandboxed iframes alongside the conversation
- Versioned — users can navigate between edit versions

Not rendered as artifacts: markdown, plain text, raw code snippets. No native support for Python-based visualizations (Matplotlib) directly in artifacts.

### LLM backend integration

- **Ollama**: First-class integration. Automatic model discovery, management from UI.
- **OpenAI-compatible APIs**: Native support for any provider (OpenAI, Azure, Together AI, Groq, vLLM, LiteLLM)
- **Anthropic**: Native Messages API endpoint + OpenAI-compatible endpoint
- **Multi-backend routing**: Users see all models from all backends in a single dropdown

### Tracing, evaluation, and research features

- **[Langfuse](https://langfuse.com/docs) integration** ([OpenWebUI guide](https://langfuse.com/integrations/no-code/openwebui)): Traces, token usage, latencies, costs via filter pipeline
- **[OpenTelemetry](https://opentelemetry.io/docs/languages/python/getting-started/)**: Native OTLP support for traces, metrics, logs
- **[Arena Mode](https://docs.openwebui.com/features/access-security/evaluation/)**: Blind A/B testing — randomly selects models, users rate without knowing which responded
- **Elo Rating System**: Models ranked based on user ratings ([leaderboard](https://openwebui.com/leaderboard/))
- **Conversation export**: JSON, PDF, plain text; bulk export; import from ChatGPT/Claude/Grok
- **[REST API](https://docs.openwebui.com/getting-started/api-endpoints)**: `POST /api/chat/completions` (OpenAI-compatible) for programmatic automation
- **Headless deployment**: Environment variables for auto-admin creation

### HPC deployment considerations

OpenWebUI is Docker-native. Running on HPC requires:

- [Converting Docker image to Apptainer `.sif`](https://apptainer.org/docs/user/latest/docker_and_oci.html)
- Multi-service setup (OpenWebUI + Ollama + optionally Jupyter + Open Terminal)
- Network port management within SLURM jobs
- File system binding for datasets and results

---

## 6. CodeAct Agents and Recursive LLMs

### CodeAct: Core Concepts

**Paper:** ["Executable Code Actions Elicit Better LLM Agents"](https://arxiv.org/abs/2402.01030) (Wang et al., ICML 2024; [author blog post](https://xwang.dev/blog/2024/codeact/), [GitHub](https://github.com/xingyaoww/code-act))

Instead of JSON tool calls, CodeAct uses **executable Python code** as the unified action space:
1. LLM generates Python code
2. Interpreter executes it
3. Output (stdout, stderr, errors) returned to LLM as "observation"
4. LLM reasons about observation and emits more code
5. Loop repeats until task is solved

**Why it works better than tool calling:**
- **Composability**: Python natively supports control flow, data flow, and composition of multiple operations in a single action
- **Fewer actions needed**: ~30% fewer steps than JSON-based approaches (multiple operations per code block)
- **Higher success rate**: Up to 20% higher on complex multi-tool tasks (82 human-curated tasks on M3ToolEval)
- **Leverages pretraining**: LLMs are massively pretrained on Python code; forcing communication through synthetic JSON function signatures works against the grain

### REPL Requirements for CodeAct

| Requirement | Why | How implementations solve it |
|---|---|---|
| **Persistent state across turns** | Variables from turn N must be accessible in turn N+1 | [IPython](https://ipykernel.readthedocs.io/en/stable/) kernels ([OpenHands](https://github.com/OpenHands/OpenHands), [ipybox](https://github.com/gradion-ai/ipybox), [Beaker](https://github.com/jataware/beaker-kernel)) |
| **Library imports** | Agent needs pandas, numpy, domain packages; imports must persist | Pre-installed in container images |
| **Error feedback (stderr/traceback)** | Agent must see errors to self-debug | IPython captures both stdout and stderr |
| **Output capture (stdout + rich output)** | Agent needs to see print output, dataframe `.head()`, plots | Jupyter message protocol handles text and image output |
| **Dataframe/data access** | Agent must load and manipulate dataframes | File mounting, context injection, pre-loaded locals |
| **Isolation/sandboxing** | LLM-generated code is untrusted | Docker, gVisor, Firecracker microVMs, Apptainer |
| **Timeout mechanisms** | Prevent infinite loops | Container-level timeouts |

### Recursive LLMs

A recent paradigm (late 2025) where LLMs decompose and recursively interact with their input context:
- The user prompt is stored as a Python variable in a REPL
- The REPL can make calls back to the LLM itself (e.g., via litellm)
- This creates a recursive loop where the LLM writes code that calls the LLM
- Results from sub-calls are captured as Python objects in kernel memory
- The agent inspects and reasons about results, then writes more code

This requires everything CodeAct needs, plus the ability to make outbound LLM API calls from within the REPL.

### Major CodeAct Implementations

**[OpenHands](https://github.com/OpenHands/OpenHands) (formerly OpenDevin)** — [ICLR 2025 paper](https://arxiv.org/abs/2407.16741), [runtime architecture docs](https://docs.all-hands.dev/modules/usage/architecture/runtime):

- Docker-based sandbox with 3 execution channels: Bash shell, IPython kernel (persistent state), Chromium browser
- Event stream architecture for coordination
- Fresh container per task, workspace directory mounted
- 53% resolve rate on SWE-Bench Verified ([CodeAct 2.1 blog post](https://docs.all-hands.dev/modules/usage/agents), November 2025)

**[Freeact](https://gradion-ai.github.io/freeact/) (Gradion AI):**

- Code action agent that can save successful code actions as reusable tools
- Evolves its own tool library over time
- Built on [ipybox](https://github.com/gradion-ai/ipybox) for sandboxed IPython execution

**[CodeArkt](https://github.com/IlyaGusev/codearkt) (IlyaGusev):**

- Docker containers for secure execution
- MCP server integration for tool discovery
- Hierarchical manager/worker multi-agent pattern

**[Anthropic Programmatic Tool Calling (PTC)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)** ([engineering blog](https://www.anthropic.com/engineering/advanced-tool-use)):

- Beta feature in Claude API
- LLM writes Python code that `await`s tool function calls
- Code runs in Anthropic's managed sandbox
- Tool results from code don't count toward context tokens (10x reduction)
- Container expires after ~4.5 minutes of inactivity

### Beaker-dev's Suitability for CodeAct

**Strengths:**
- Already designed as an agent-code-execution bridge
- Jupyter-protocol compatible: state persistence built in
- Contexts system for injecting domain-specific tools and data loaders
- Supports undo/rollback to previous kernel states
- `BeakerContext.execute()` provides the code execution primitive needed for CodeAct (Jupyter `execute_request` to the subkernel)
- litellm already installed in the Apptainer container for direct LLM calls

**Limitations:**

- **Archytas enforces ReAct, not CodeAct**: The agent framework ([Archytas](https://github.com/jataware/archytas)) only handles structured JSON tool calls. If the LLM returns text without a tool call, Archytas tries to JSON-parse it and otherwise wraps it as `final_answer`. It does NOT parse code blocks from natural text. This means `code_context` today is ReAct+run_code, not CodeAct.
- **`run_code` is a Beaker-provided Archytas `@tool()`**: Defined in `beaker_kernel/lib/subkernel.py`, it's automatically registered for every `BeakerAgent`. The LLM must produce `{"name": "run_code", "args": {"code": "..."}}` — not natural code in markdown fences.
- Building true CodeAct requires a custom agent loop that bypasses Archytas entirely, calling litellm directly and extracting code blocks via regex. See the implementation plan: `docs/plans/25_02_2026_2053_implement_true_codeact_context_bypassing_archytas.md`.
- Primarily designed for interactive use, not headless automated experiments (though WebSocket API exists and is used by `run_experiment.py`)
- Smaller community/ecosystem compared to OpenHands or E2B

---

## 7. Alternative REPL/Sandbox Approaches

### [Jupyter Kernel Gateway](https://github.com/jupyter-server/kernel_gateway) / [Enterprise Gateway](https://github.com/jupyter-server/enterprise_gateway)

- Exposes Jupyter kernels via HTTP/WebSocket API without a notebook UI
- Can be containerized with Docker/Apptainer
- Enterprise Gateway extends to distributed clusters (Kubernetes, Spark)
- Mature, well-understood protocol; [IPython kernels](https://ipykernel.readthedocs.io/en/stable/) provide exactly the persistent-state REPL that CodeAct needs
- The [dida.do blog](https://dida.do/blog/setting-up-a-secure-python-sandbox-for-llm-agents) describes wrapping [`jupyter_client`](https://jupyter-client.readthedocs.io/en/stable/) behind a FastAPI service with [gVisor](https://gvisor.dev/docs/) sandboxing as a production approach for LLM agent code execution. See also [Murray Cole's blog post](https://murraycole.com/posts/ai-code-execution-environment) on building AI agent code execution environments.

### [E2B](https://e2b.dev/) ([GitHub](https://github.com/e2b-dev/E2B), [code interpreter SDK](https://e2b.dev/docs/code-interpreting))

- Purpose-built sandbox for AI agents using Firecracker microVMs
- ~150ms boot time, open source (Apache-2.0), self-hostable
- Pre-built "Code Interpreter" sandbox with Jupyter kernel inside
- Used by ~50% of Fortune 500 for agent workflows
- **Limitation for HPC**: Firecracker requires KVM support (problematic without root access)

### [Modal Sandboxes](https://modal.com/docs/guide/sandbox)

- Serverless container execution with GPU support
- Python-first API, clean SDK
- **Limitation**: Cloud-only, no self-hosting, not suitable for air-gapped HPC

### Docker-Based ([ipybox](https://github.com/gradion-ai/ipybox), [OpenHands](https://docs.all-hands.dev/modules/usage/architecture/runtime) pattern)

- IPython kernels inside Docker containers with REST API
- ipybox (Gradion AI): first-class MCP tool calling support, tool approval layer
- **Limitation**: Docker daemon not available on most HPC systems (Apptainer is the equivalent)

### [Apptainer](https://apptainer.org/docs/user/latest/) (current approach)

- Standard container runtime for HPC (no root access required)
- GPU passthrough via `--nv` flag
- Works with SLURM
- Can [build from Docker images](https://apptainer.org/docs/user/latest/docker_and_oci.html) (`.sif` files)
- Harmonia already uses this successfully

---

## 8. Platform Comparison Matrix

### Core capabilities

| Capability | Beaker-dev (current) | Streamlit | OpenWebUI |
|---|---|---|---|
| **Persistent Python REPL** | Built-in (Jupyter subkernel) | No (must embed kernel) | Yes (Jupyter backend) |
| **CodeAct agent loop** | Must build (bypass Archytas) | Must build from scratch | Native Mode + `execute_code` |
| **Tool-calling agent** | Archytas `@tool()` | Build with LangChain/LangGraph | Native tool system (4 categories) |
| **LLM-generated code execution** | Direct in subkernel | `exec()` hack (unsafe) | Jupyter or Open Terminal |
| **Recursive LLM support** | Yes (litellm in subkernel) | Yes (you write the loop) | Yes (litellm in Jupyter backend) |
| **Experiment automation** | `run_experiment.py` via WebSocket | Fully custom | REST API (`/api/chat/completions`) |
| **Trace/log capture** | `trace.json` + custom CLI analyzer | Fully custom | Langfuse / OpenTelemetry / export |
| **Multi-model comparison** | Config per experiment | Custom | Arena mode (blind A/B with Elo) |
| **HPC/SLURM integration** | Working (Apptainer) | Easy (just Python) | Needs Apptainer conversion |
| **Rendering richness** | Markdown in notebook cells | Excellent (charts, tables, Plotly) | Artifacts (HTML/JS/D3/ThreeJS) |
| **Multi-user support** | No | No (needs external proxy) | Built-in auth + RBAC |
| **Conversation persistence** | Custom (trace.json) | Must implement | Built-in database |
| **Community ecosystem** | Small | Large (Python data science) | Growing (tools, functions, pipes) |

### For CodeAct/recursive LLM experiments specifically

| Requirement | Beaker-dev | Streamlit | OpenWebUI |
|---|---|---|---|
| Persistent state across turns | Yes (subkernel) | No | Yes (Jupyter backend) |
| Library access (pandas, bdi-kit) | Yes (pre-installed in container) | N/A | Yes (if configured in Jupyter) |
| Error feedback to LLM | Yes (Jupyter protocol) | Manual redirect | Yes (Jupyter protocol) |
| Rich output capture | Yes (Jupyter protocol) | Manual | Yes (Jupyter protocol) |
| Sandboxing | Yes (Apptainer) | No | Yes (container-level) |
| LLM API calls from REPL | Yes (litellm available) | N/A | Yes (litellm installable) |
| Undo/rollback | Yes (Beaker feature) | No | No |

---

## 9. Migration Cost Analysis

### Option A: Stay with Beaker-dev (extend for CodeAct)

**Effort: Low (1-2 weeks)**

What to build:

- A new `codeact_context` Beaker context with a `CodeActAgentLoop` class (~200-400 lines) that bypasses Archytas entirely
- Direct litellm calls (no Archytas, no tool schemas)
- Regex extraction of code blocks from LLM natural text responses
- Execute extracted code via `BeakerContext.execute()` (same Jupyter protocol as `run_code` uses)
- System prompt instructing pure code execution (no tool schemas, no ReAct prelude)
- Config support for selecting context: `bdikit_context`, `code_context`, or `codeact_context`
- Full implementation plan: `docs/plans/25_02_2026_2053_implement_true_codeact_context_bypassing_archytas.md`

What you keep:

- Same Apptainer image, SLURM integration, per-job Ollama isolation
- Same tracing infrastructure (`trace.json`, `conversation.md`, log analysis CLI)
- Same evaluation pipeline (metrics)
- Same data access patterns
- Same subkernel execution path (`BeakerContext.execute()`)

**Advantage**: The only experimental variable is the agent paradigm — cleanest scientific design for comparing tool-calling vs code-only agents.

### Option B: Migrate to OpenWebUI

**Effort: High (4-6 weeks)**

What to build/convert:
1. Apptainer image from OpenWebUI's Docker image (multi-service: OpenWebUI + Ollama + Jupyter)
2. Reimplement Harmonia's 5 BDI-Kit tools as OpenWebUI Workspace Tools or MCP server
3. Reimplement experiment automation (REST API client replacing WebSocket-based `run_experiment.py`)
4. Adapt tracing (adopt Langfuse or write custom filter pipeline producing `trace.json`-compatible output)
5. Adapt log analysis CLI for new trace format (13 failure-mode categories)
6. Replace Beaker contexts (`auto_context()`, Jinja2 templates) with OpenWebUI system prompts or Pipe Functions
7. Replicate per-job Ollama isolation within OpenWebUI setup

What you gain:
- Arena mode for blind model comparison with Elo ratings
- Richer rendering (HTML artifacts, D3 visualizations)
- Built-in multi-model management (all backends in single dropdown)
- Community tool ecosystem
- Better UI for manual experiments
- Langfuse observability (token costs, latencies, traces with spans)
- Conversation export in multiple formats

### Option C: Streamlit as UI + Jupyter kernel as backend

**Effort: High (3-5 weeks)**

What to build:
1. Streamlit chat UI from scratch
2. `jupyter_client` integration for kernel management
3. Agent loop (both ReAct and CodeAct modes)
4. Tracing/logging system
5. Experiment automation framework
6. Tool dispatch layer

What you gain:
- Maximum flexibility (pure Python, you control everything)
- Excellent data visualization (Plotly, Altair, Matplotlib native)
- Simple deployment (just a Python process)

What you lose:
- Everything is custom — no community tools, no built-in evaluation, no conversation management

---

## 10. Recommendation

### For near-term experiments (CodeAct + recursive LLMs): Stay with Beaker

**Rationale:**

1. **The execution infrastructure is already there**: Beaker's subkernel provides persistent state, library access, error feedback, output capture — everything CodeAct and recursive LLMs need. `BeakerContext.execute()` is the same code execution primitive regardless of whether the agent loop is Archytas ReAct or a custom CodeAct loop.

2. **`code_context` is ReAct+run_code, not CodeAct** (corrected from earlier version of this document). The LLM uses Archytas' structured JSON tool-call format to invoke `run_code(code="...")`. True CodeAct requires a custom `CodeActAgentLoop` (~200-400 lines) that bypasses Archytas, calls litellm directly, and extracts code from markdown fences. See `docs/plans/25_02_2026_2053_implement_true_codeact_context_bypassing_archytas.md` for the full implementation plan.

3. **Three experimental conditions, one execution environment**: Using Beaker's subkernel for all three conditions — (a) ReAct+domain tools (`bdikit_context`), (b) ReAct+run_code (`code_context`), (c) true CodeAct (new `codeact_context`) — means the only variable is the agent strategy. Migrating to a different platform introduces confounding variables.

4. **Lowest engineering cost**: Build a `CodeActAgentLoop` rather than migrating an entire platform. See [LlamaIndex's "CodeAct agent from scratch" tutorial](https://developers.llamaindex.ai/python/examples/agent/from_scratch_code_act_agent/) for reference implementation patterns.

5. **Same tracing infrastructure**: `trace.json` format and the log analysis CLI work for all agent modes without modification.

### For future consideration: OpenWebUI as UI upgrade

If the manual experiment UI becomes a bottleneck (Beaker's notebook interface is functional but basic), [OpenWebUI](https://docs.openwebui.com/getting-started/) with a [Jupyter backend](https://tersesystems.com/blog/2025/03/10/jupyter-with-openwebui-code-interpreter/) would provide:

- A polished chat interface
- [Arena mode](https://docs.openwebui.com/features/access-security/evaluation/) for model comparison
- [Langfuse](https://langfuse.com/docs) observability ([integration guide](https://langfuse.com/integrations/no-code/openwebui))
- [Artifact](https://docs.openwebui.com/features/chat-conversations/chat-features/code-execution/artifacts/) rendering for results visualization

This could be pursued as a separate effort after the core CodeAct experiments are complete, treating it as a UI concern rather than an execution environment concern.

### What to avoid: Streamlit for this use case

Streamlit is the wrong tool for agent code execution. It has no REPL, no kernel, no persistent execution state. BDI-kit's migration to Streamlit makes sense for their tool-calling-only design, but it does not address the code execution requirements of CodeAct or recursive agents. Adopting Streamlit would mean rebuilding Beaker's execution capabilities from scratch.

---

## Sources

### CodeAct and agent architectures

- [CodeAct paper (Wang et al., ICML 2024)](https://arxiv.org/abs/2402.01030) — [author blog post](https://xwang.dev/blog/2024/codeact/), [GitHub](https://github.com/xingyaoww/code-act), [Apple ML Research page](https://machinelearning.apple.com/research/codeact)
- [OpenHands (formerly OpenDevin) — GitHub](https://github.com/OpenHands/OpenHands) — [ICLR 2025 paper](https://arxiv.org/abs/2407.16741), [runtime architecture](https://docs.all-hands.dev/modules/usage/architecture/runtime), [CodeAct 2.1 agents docs](https://docs.all-hands.dev/modules/usage/agents)
- [Freeact (Gradion AI)](https://gradion-ai.github.io/freeact/)
- [CodeArkt (IlyaGusev)](https://github.com/IlyaGusev/codearkt)
- [Anthropic Programmatic Tool Calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling) — [Advanced Tool Use engineering blog](https://www.anthropic.com/engineering/advanced-tool-use), ["Code as Action" pattern analysis](https://www.ikangai.com/code-as-action-the-pattern-behind-programmatic-tool-calling/)
- [Recursive Language Models paper](https://arxiv.org/html/2512.24601v1)
- [GoalAct — hierarchical CodeAct execution](https://github.com/cjj826/GoalAct)
- [LlamaIndex: CodeAct agent from scratch tutorial](https://developers.llamaindex.ai/python/examples/agent/from_scratch_code_act_agent/)

### LangChain / LangGraph / LiteLLM

- [LangChain Python documentation](https://python.langchain.com/docs/introduction/)
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/)
- [langchain-mcp-adapters — GitHub](https://github.com/langchain-ai/langchain-mcp-adapters)
- [LiteLLM documentation](https://docs.litellm.ai/) — [GitHub](https://github.com/BerriAI/litellm)
- [Model Context Protocol (MCP) specification](https://modelcontextprotocol.io/)
- [FastMCP Python library](https://github.com/jlowin/fastmcp)

### Streamlit

- [Streamlit architecture / execution model](https://docs.streamlit.io/develop/concepts/architecture)
- [Streamlit API reference](https://docs.streamlit.io/develop/api-reference)
- [Streamlit chat elements (st.chat_message, st.chat_input)](https://docs.streamlit.io/develop/api-reference/chat)
- [Streamlit session state](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)
- [Streamlit forum: exec() discussion](https://discuss.streamlit.io/t/exec-in-streamlit/34461)
- [Streamlit forum: safety issues with exec/subprocess](https://discuss.streamlit.io/t/safety-issues-with-exec-or-subproccess/44057)
- [streamlit-code-editor — GitHub](https://github.com/bouzidanas/streamlit-code-editor)
- [streamlit-execute (Pyodide) — GitHub](https://github.com/bouzidanas/streamlit-execute)
- [streamlit-jupyter — GitHub](https://github.com/ddobrinskiy/streamlit-jupyter)
- [PandasAI — GitHub](https://github.com/sinaptik-ai/pandas-ai) — [CVE-2024-23752](https://vulert.com/vuln-db/CVE-2024-23752)

### OpenWebUI

- [OpenWebUI — GitHub](https://github.com/open-webui/open-webui)
- [OpenWebUI features overview](https://docs.openwebui.com/features/)
- [Getting started / installation](https://docs.openwebui.com/getting-started/)
- [Code execution docs](https://docs.openwebui.com/features/chat-conversations/chat-features/code-execution/)
- [Artifacts docs](https://docs.openwebui.com/features/chat-conversations/chat-features/code-execution/artifacts/)
- [Tools / plugins docs](https://docs.openwebui.com/features/extensibility/plugin/tools/)
- [Pipelines docs](https://docs.openwebui.com/features/extensibility/pipelines/) — [Pipelines GitHub](https://github.com/open-webui/pipelines)
- [Open Terminal docs](https://docs.openwebui.com/features/extensibility/open-terminal/)
- [Arena evaluation docs](https://docs.openwebui.com/features/access-security/evaluation/)
- [API endpoints](https://docs.openwebui.com/getting-started/api-endpoints)
- [Community tools marketplace](https://openwebui.com/tools/)
- [Community leaderboard](https://openwebui.com/leaderboard/)
- [Safe code execution (gVisor sandbox) — GitHub](https://github.com/EtiennePerot/safe-code-execution) — [run_code tool](https://openwebui.com/t/etienneperot/run_code)
- [Jupyter with OpenWebUI Code Interpreter (tersesystems blog)](https://tersesystems.com/blog/2025/03/10/jupyter-with-openwebui-code-interpreter/)

### Observability / Tracing

- [Langfuse documentation](https://langfuse.com/docs) — [tracing overview](https://langfuse.com/docs/observability/overview), [data model](https://langfuse.com/docs/observability/data-model)
- [Langfuse Python SDK](https://langfuse.com/docs/observability/sdk/python/setup) — [GitHub](https://github.com/langfuse/langfuse-python)
- [Langfuse OpenWebUI integration](https://langfuse.com/integrations/no-code/openwebui)
- [Langfuse LangChain integration](https://langfuse.com/integrations/frameworks/langchain)
- [Langfuse evaluations / scoring](https://langfuse.com/docs/scores/overview)
- [OpenTelemetry Python getting started](https://opentelemetry.io/docs/languages/python/getting-started/)
- [Opik (Comet) — docs](https://www.comet.com/docs/opik/) — [GitHub](https://github.com/comet-ml/opik)

### Sandbox / REPL alternatives

- [E2B](https://e2b.dev/) — [GitHub](https://github.com/e2b-dev/E2B), [code interpreter SDK docs](https://e2b.dev/docs/code-interpreting)
- [ipybox (Gradion AI) — GitHub](https://github.com/gradion-ai/ipybox)
- [Modal sandboxes](https://modal.com/docs/guide/sandbox)
- [Jupyter Kernel Gateway — GitHub](https://github.com/jupyter-server/kernel_gateway) — [docs](https://jupyter-kernel-gateway.readthedocs.io/en/latest/)
- [Jupyter Enterprise Gateway — GitHub](https://github.com/jupyter-server/enterprise_gateway)
- [jupyter_client documentation](https://jupyter-client.readthedocs.io/en/stable/)
- [IPython kernel (ipykernel) documentation](https://ipykernel.readthedocs.io/en/stable/)
- [Setting up a secure Python sandbox for LLM agents (dida.do blog)](https://dida.do/blog/setting-up-a-secure-python-sandbox-for-llm-agents)
- [Building an AI Agent's Code Execution Environment (Murray Cole)](https://murraycole.com/posts/ai-code-execution-environment)
- [Code sandboxes for LLMs and AI agents survey (Amir Malik)](https://amirmalik.net/2025/03/07/code-sandboxes-for-llm-ai-agents)
- [gVisor documentation](https://gvisor.dev/docs/)
- [Apptainer documentation](https://apptainer.org/docs/user/latest/) — [building from Docker images](https://apptainer.org/docs/user/latest/docker_and_oci.html)

### BDI-Kit and Beaker-dev

- [BDI-Kit — GitHub (VIDA-NYU)](https://github.com/VIDA-NYU/bdi-kit) — [CHANGELOG / releases](https://github.com/VIDA-NYU/bdi-kit/releases)
- [Beaker Kernel — GitHub (Jataware)](https://github.com/jataware/beaker-kernel) — [documentation](https://jataware.github.io/beaker-kernel/)
- [Archytas (Jataware ReAct framework) — GitHub](https://github.com/jataware/archytas)
- [ASKEM Beaker (DARPA)](https://darpa-askem.github.io/askem-beaker/)
- [Harmonia paper — Interactive Data Harmonization with LLM Agents](https://arxiv.org/abs/2502.07132)
