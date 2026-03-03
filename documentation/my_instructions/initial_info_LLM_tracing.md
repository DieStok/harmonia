# Frameworks for Visualizing & Comparing LLM Agent Traces

## The Big Players (by popularity/adoption)

### 1. LangSmith (by LangChain)

One of the largest communities in LLM tooling, with over 100k members. LangSmith is a tracing tool built into LangChain, so no adjustments are required if you're a LangChain user. It offers trace visualization, a prompt playground for side-by-side model/prompt comparison, dataset management, and LLM-as-a-judge evaluations. The main trade-off is ecosystem lock-in — the best experience is locked to the LangChain ecosystem, and other frameworks get basic support but miss native features. LangSmith doesn't offer a self-hosting option in the self-serve module, and the free tier caps at 5k traces per month.

- **Docs:** https://docs.smith.langchain.com
- **GitHub (SDKs only):** https://github.com/langchain-ai/langsmith-sdk
- **License:** Commercial (free tier available)

---

### 2. Langfuse

Langfuse is an open source LLM engineering platform that provides LLM call tracking and tracing, prompt management, evaluation, datasets, and more. It claims to be the most-used open LLMOps platform. Its pricing page lists 78 features from session tracking to batch exports to SOC2 compliance. It's MIT-licensed, self-hostable via Docker Compose or Kubernetes, and acts as an OpenTelemetry backend. The architecture relies on PostgreSQL, which is simpler to deploy but may face scaling challenges at very high volumes compared to distributed systems.

- **Docs:** https://langfuse.com/docs
- **GitHub:** https://github.com/langfuse/langfuse (6k+ stars)
- **License:** MIT

---

### 3. Arize Phoenix

Arize Phoenix is an open-source LLM tracing and evaluation platform — transparent, framework-agnostic, and vendor-lock-in free. Built on OpenTelemetry and the OpenInference standard. It supports popular frameworks like OpenAI Agents SDK, LangGraph, Vercel AI SDK, CrewAI, LlamaIndex, and DSPy. A standout feature is its embedding-based dataset clustering and visualization using 2D UMAP to uncover semantically similar questions and responses. It runs locally, in notebooks, in Docker/Kubernetes, or in the cloud.

- **Docs:** https://arize.com/docs/phoenix
- **GitHub:** https://github.com/Arize-ai/phoenix (8.7k+ stars)
- **License:** ELv2

---

### 4. Opik (by Comet)

Opik is an open-source platform designed to streamline the entire lifecycle of LLM applications, providing comprehensive tracing of LLM calls, conversation logging, and agent activity. What distinguishes it is its breadth of integrations (including low-code platforms like Dify and Flowise), a dedicated Agent Optimizer SDK for automated prompt tuning, and built-in guardrails. It's designed for scale at 40M+ traces per day. As the newest major entrant, the community is still growing.

- **Docs:** https://www.comet.com/docs/opik/
- **GitHub:** https://github.com/comet-ml/opik
- **License:** Apache 2.0

---

### 5. W&B Weave (by Weights & Biases)

Weave is a framework for tracking, experimenting with, evaluating, deploying, and improving LLM-based applications. Its key strength is deep integration with the broader W&B experiment tracking ecosystem, which is already widely used in ML. It uses a simple `@weave.op` decorator for tracing and offers a playground, leaderboard comparisons, and evaluation scorers. The flip side is commitment to the W&B ecosystem, and it doesn't focus as heavily on step-by-step tracing as dedicated platforms.

- **Docs:** https://docs.wandb.ai/weave
- **GitHub:** https://github.com/wandb/weave
- **License:** Open source (Apache 2.0), cloud is commercial

---

### 6. Braintrust

Focused on closing the loop from observing a failure to fixing it. Automatic trace capture logs LLM duration, time to first token, prompt tokens, cached tokens, completion tokens, reasoning tokens, estimated cost, tool calls, and errors — all with no configuration. It features timeline replay for visual debugging and the ability to convert failed traces into CI test cases in minutes. Pricing starts at a free tier with 1M trace spans, but tracing is primarily positioned for debugging and introspection during development rather than full production monitoring.

- **Docs:** https://www.braintrust.dev/docs
- **GitHub:** https://github.com/braintrustdata/braintrust-sdk
- **License:** Commercial (free tier)

---

### 7. Helicone

A proxy-based platform — instead of adding SDKs, you route LLM API calls through the Helicone proxy and it logs everything automatically. It provides purpose-built tools for improving LLMs, like its prompt playground, prompt management, evaluation scoring, and feedback. It also features built-in response caching to save costs. Helicone uses a distributed architecture with ClickHouse and Kafka for high-volume scaling. Setup takes as little as 15 minutes.

- **Docs:** https://docs.helicone.ai
- **GitHub:** https://github.com/Helicone/helicone (1k+ stars)
- **License:** Open source (Apache 2.0)

---

### 8. TruLens (by TruEra / Snowflake)

TruLens is especially popular for agentic workflows and RAG, where understanding why the model produced an answer is as important as the answer itself. It provides built-in feedback functions for groundedness, context relevance, and answer relevance. It lets you compare different versions of your app side by side on various metrics and visualize experiment results using a metrics leaderboard. It's completely free and open source, now under Snowflake's stewardship.

- **Docs:** https://www.trulens.org/docs
- **GitHub:** https://github.com/truera/trulens (2k+ stars)
- **License:** MIT

---

### 9. DeepEval / Confident AI

DeepEval's biggest advantage is its developer-friendly, code-first approach, which integrates with existing software practices. It uses an `@observe` decorator for tracing and supports both end-to-end and component-level evals with typed span data (LLM, retriever, tool, agent). The core library is free, but the full visualization and debugging UI requires the associated Confident AI cloud service.

- **Docs:** https://deepeval.com/docs
- **GitHub:** https://github.com/confident-ai/deepeval
- **License:** Open source (core), commercial cloud UI

---

### 10. Traceloop / OpenLLMetry

Traceloop's SDK OpenLLMetry allows teams to transmit LLM observability data to 10+ various tools in OpenTelemetry format. Rather than being a full platform, it's a vendor-neutral instrumentation layer. Because it exports in standard OTEL format, you can pipe traces into any compatible backend (Jaeger, Grafana, Datadog, etc.). Best for teams wanting maximum portability.

- **Docs:** https://www.traceloop.com/docs
- **GitHub:** https://github.com/traceloop/openllmetry
- **License:** Apache 2.0

---

### 11. Lunary

Lunary is a toolkit for LLM chatbots, with conversation and feedback tracking, analytics, prompt management, and more. It's purpose-built for conversational AI with features like PII masking, access management, human reviewing, and multi-modal support. It integrates with destinations like Snowflake and Segment. The free tier offers 10k events/month.

- **Docs:** https://lunary.ai/docs
- **GitHub:** https://github.com/lunary-ai/lunary
- **License:** Open source (Apache 2.0)

---

### 12. Maxim AI

Maxim combines tracing, evaluation, and simulation into a single platform, letting you test agent behavior across thousands of scenarios before shipping. Best for teams building multi-agent systems who need visual tracing and pre-production testing. Timeline replay and chain-of-thought visualization are still maturing.

- **Docs:** https://docs.getmaxim.ai
- **Website:** https://www.getmaxim.ai
- **License:** Commercial (free tier, paid from $29/seat/month)

---

## Quick Comparison

| Tool | Open Source | Self-Host | Side-by-Side Comparison | OTEL Native | Best For |
|---|---|---|---|---|---|
| **LangSmith** | No (SDKs only) | Enterprise only | Yes (playground) | Yes | LangChain users |
| **Langfuse** | Yes (MIT) | Yes | Yes (experiments) | Yes | Broadest feature set, self-hosting |
| **Phoenix** | Yes (ELv2) | Yes | Yes (playground) | Yes | RAG debugging, embedding viz |
| **Opik** | Yes (Apache 2.0) | Yes | Yes (experiments) | Yes | Scale, agent optimization |
| **W&B Weave** | Yes (Apache 2.0) | Via W&B | Yes (leaderboard) | Yes | Teams already on W&B |
| **Braintrust** | No | No | Yes (timeline replay) | Yes | Trace-to-test-case workflow |
| **Helicone** | Yes (Apache 2.0) | Yes | Limited | No | Zero-code proxy setup, cost tracking |
| **TruLens** | Yes (MIT) | Yes | Yes (leaderboard) | Yes | RAG eval, feedback functions |
| **DeepEval** | Partial | No | Yes (via Confident AI) | No | Code-first testing, CI/CD |
| **OpenLLMetry** | Yes (Apache 2.0) | N/A (library) | Via backends | Yes | Vendor-neutral instrumentation |
| **Lunary** | Yes (Apache 2.0) | Yes | Limited | No | Chatbot-focused, PII masking |
| **Maxim** | No | No | Yes (simulation) | No | Pre-production agent simulation |

---

## What Distinguishes Them

The landscape roughly divides into a few categories:

- **Full platforms** (Langfuse, LangSmith, Opik, Phoenix) offer tracing + eval + prompt management in one place.
- **Gateway/proxy tools** (Helicone) prioritize zero-code integration and cost tracking.
- **Eval-first tools** (TruLens, DeepEval, Braintrust) focus on systematic quality measurement with tracing as a supporting feature.
- **Infrastructure layers** (OpenLLMetry/Traceloop) provide vendor-neutral instrumentation you can route anywhere.

For pure side-by-side trace comparison of agent runs, Langfuse, LangSmith, Phoenix, and Braintrust have the most mature UIs. For embedding-based visual clustering to find patterns across traces, Phoenix is uniquely strong. For teams wanting full open-source control with no feature gates, Langfuse (MIT) and Opik (Apache 2.0) are the cleanest choices.
