# Agent Architectures for LLM-Based Scientific Data Processing: From Coding Agents to Multi-Agent Orchestration

**A Comprehensive Research Report for the Harmonia/BDI-Kit Metadata Harmonization Project**

---

## Conceptual Overview

Metadata harmonization — mapping heterogeneous biomedical data tables to a controlled vocabulary like the Genomic Data Commons (GDC) schema — is a task that sits at a specific and instructive point on the agent architecture complexity spectrum. It requires sequential reasoning over structured relationships (parsing source schemas, matching columns to targets, transforming values), domain knowledge (ontology constraints, biomedical terminology), and iterative refinement (validating mappings, handling ambiguity). This combination makes it a natural testbed for comparing single-agent, multi-agent, and frontier coding agent approaches.

The core tension in this space is between **architectural sophistication** (multi-agent orchestration, hierarchical delegation, parallel fan-out) and **context engineering** (curating what tokens the model sees at each decision point). Three independent lines of evidence — Google DeepMind's 180-configuration scaling study, Cemri et al.'s 1,600-trace failure analysis, and Kapoor et al.'s cost-accuracy Pareto evaluation — converge on the same finding: for sequential reasoning tasks, simpler architectures with better context consistently outperform more complex multi-agent systems. The question for Harmonia is not "which framework?" but "what is the simplest architecture that achieves acceptable harmonization quality, and does it outperform a frontier coding agent given the same data?"

This report synthesizes 50+ sources from 2024–2026, the provided Harmonia codebase documentation, SRAgent pattern analysis, and context materials on Recursive Language Models and the Kosmos AI Scientist to lay out a concrete, phased architecture. It covers nine agent paradigms (from direct prompting to recursive multi-agent hierarchies), observability infrastructure, deterministic reproducibility, sandboxed execution on HPC, and human-in-the-loop escalation patterns — all grounded in what the evidence actually supports rather than what is architecturally fashionable.

## Key Takeaways

1. **CodeAct dominates ReAct for data processing.** Executable Python as the action space yields up to 20% higher success rates than structured JSON tool calls (Wang et al., ICML 2024), with native control flow, library access, and self-debugging via error messages.

2. **Multi-agent is the wrong default for metadata harmonization.** Multi-agent coordination degrades sequential reasoning tasks by 39–70% (Google DeepMind, Kim et al., 2026), and multi-agent systems fail 41–86.7% of the time across 7 frameworks (Cemri et al., NeurIPS 2025). Schema matching is fundamentally sequential.

3. **Context engineering matters more than architecture choice.** A focused 300-token context often outperforms an unfocused 113,000-token context (Anthropic, 2025). Investment in curated prompts, retrieval-augmented schema context, and observation masking yields more improvement than architectural changes.

4. **Test the frontier baseline first.** Before building bespoke infrastructure, run Claude Code headless or Codex CLI on the benchmark with a well-crafted CLAUDE.md. If it achieves acceptable quality, stop. This "Kapoor test" prevents months of wasted engineering (Kapoor et al., 2024).

5. **Structured pipelines compensate for model weakness.** Matchmaker's compositional LM program with GPT-3.5 matches simpler architectures with GPT-4 (Seedat & van der Schaar, NeurIPS 2024). DSPy-compiled pipelines with bootstrapped few-shot examples outperform hand-crafted prompts by 25–65%.

6. **For large tables, use Recursive Language Models, not more agents.** RLMs process inputs 100× beyond context windows by treating data as an external environment accessed via code, achieving dramatic improvements without multi-agent coordination overhead (Zhang et al., 2025).

7. **Reproducibility requires defense in depth.** Temperature=0 does not guarantee determinism. Layer four mechanisms: exact-match LLM call caching, configuration snapshots, prompt versioning (Langfuse), and materialized intermediate outputs.

---

## 1. Terminology and Key Concepts

**ReAct** (Reason + Act): An agent loop where the LLM alternates between generating a thought (reasoning about what to do), selecting an action (invoking a tool via structured JSON), and observing the result. Implemented in Harmonia via the Archytas framework's `ReActAgent`. The action space is constrained to predefined tools.

**CodeAct**: An agent paradigm where the LLM writes executable Python code as its action, which is then run in a sandboxed environment. The key advantage is access to Python's native control flow (loops, conditionals, variables) and the entire package ecosystem. Implemented in Harmonia via `CodeActAgentLoop` with `litellm.acompletion()`.

**Frontier Coding Agent**: A production coding agent (Claude Code, OpenAI Codex CLI) used as-is with minimal customization — a CLAUDE.md or system prompt describing the task, the data files, and installed libraries. The "simplest possible agent" baseline.

**Compositional LM Program**: A fixed multi-stage pipeline of distinct LLM calls — not an agent loop. Each stage (e.g., candidate generation → refinement → scoring) has its own prompt and can be independently optimized. The Matchmaker system and DSPy framework exemplify this pattern.

**Context Engineering**: The disciplined practice of curating exactly which tokens the model sees at each decision point. Encompasses writing information to external storage, selecting relevant context via retrieval, compressing prior observations, and isolating context across specialized stages.

**Recursive Language Model (RLM)**: A paradigm where the LLM treats its input data as an external environment variable rather than in-context text. The model writes code to inspect, partition, and recursively process chunks of the data by invoking sub-LLM calls, enabling processing of inputs far exceeding the context window.

**GDC (Genomic Data Commons)**: The NCI's harmonized data repository with a 736-column target schema defining standardized metadata fields for cancer genomics. Harmonization means mapping arbitrary source metadata tables to GDC's controlled vocabulary.

**BDI-Kit / Harmonia**: The published BDI-Kit toolkit (Lopez et al., Patterns 2026; Santos et al., 2025) provides a human-in-the-loop LLM agent with 5 domain-specific tools (`match_schema`, `rank_schema_matches`, `match_values`, `materialize_mapping`, `get_gdc_acceptable_values`). The Harmonia research fork extends it with Apptainer sandboxing, CodeAct execution, Phoenix/OTel tracing, a 20-class failure taxonomy, automated experiment orchestration, and 100+ model support via litellm.

**OpenTelemetry (OTel) / OpenInference**: OTel is the industry-standard observability framework for distributed tracing. OpenInference extends it with AI-specific semantic conventions defining span kinds for `LLM`, `CHAIN`, `TOOL`, `RETRIEVER`, and `AGENT` operations, enabling structured tracing of agent execution.

---

## 2. Agent Architecture Taxonomy

### 2.1 Architecture A: ReAct + Domain Tools

The canonical Thought→Action→Observation loop, as implemented by Archytas (Jataware's lightweight Python framework powering the Beaker kernel). The LLM selects from predefined tools via structured JSON calls — in Harmonia's case, the five BDI-Kit primitives: `match_schema`, `rank_schema_matches`, `match_values`, `materialize_mapping`, and `get_gdc_acceptable_values`. Archytas auto-generates tool usage prompts from Python function signatures via its `@tool` decorator pattern and includes a built-in `PythonTool` for code execution.

**Strengths for harmonization:** Constrained action space makes behavior predictable and traceable. Each tool invocation maps to a discrete span in the OTel trace. Domain-specific tools abstract away BDI-Kit's internal complexity — the LLM doesn't need to know how embedding-based schema matching works, only that `match_schema` returns candidate column mappings.

**Weaknesses:** Single-point-of-failure: if a tool produces incorrect results, the LLM has no recourse but to retry with different parameters. LangChain's February 2025 benchmark revealed a critical scaling limit: both more context and more tools degrade single ReAct agent performance, with customer support tasks (averaging 2.7 tool calls) degrading faster than simpler tasks. Archytas lacks checkpointing, streaming, prompt caching, and the production observability hooks that become essential for reproducible scientific experiments.

**Archytas vs. LangChain's ReAct:** Archytas (~11 GitHub stars) is far simpler than LangChain's enterprise-grade `create_react_agent` with its `StateGraph`, `ToolNode`, and extensive provider integrations. This simplicity is simultaneously its strength (easy to modify for research) and its ceiling (no built-in support for multi-agent, structured output, or state persistence).

### 2.2 Architecture B: True CodeAct

Wang et al. (ICML 2024, "Executable Code Actions Elicit Better LLM Agents") demonstrated that letting LLMs write executable Python instead of structured tool calls yields **up to 20% higher success rates** across 17 LLMs on API-Bank and M3ToolEval, while requiring fewer interaction turns. OpenHands (ICLR 2025) adopted CodeAct as its default agent architecture. The advantage is structural: Python's native control flow (loops, conditionals, variable reuse) lets agents compose multiple operations in a single action, and error messages provide automatic self-debugging feedback.

Harmonia's `CodeActAgentLoop` implements this pattern: the LLM writes Python in markdown fences, the loop extracts and executes it in the Beaker kernel, and the output feeds back as the next observation. This bypasses Archytas entirely, using `litellm.acompletion()` directly. For metadata harmonization, a CodeAct agent can write a pandas transformation, call BDI-Kit's API as importable library functions (`bdi_kit.match_schema()`, `bdi_kit.top_matches()`), inspect the resulting dataframe, and iteratively refine — all within a single code block.

**Key tradeoff:** Traceability. A 50-line Python script is harder to decompose into individual traced actions than five sequential tool calls. Each code block is a single span; understanding what happened inside requires parsing the code itself.

### 2.3 Architecture C: Frontier Coding Agent

Claude Code's headless mode (`claude -p "prompt" --output-format json`) and Codex CLI's `codex exec --full-auto --json` represent the minimal-architecture extreme. Give the agent the source CSV, the target schema, BDI-Kit as an installed library, and a well-crafted CLAUDE.md describing the harmonization task. Let the agent figure out the approach.

Mario Zechner's pi-coding-agent (November 2025, 14K+ GitHub stars) crystallized this philosophy: **only 4 tools (read, write, edit, bash)**, a system prompt under 1,000 tokens, and competitive performance on Terminal-Bench. The argument: frontier models, having been extensively RL-trained for coding, don't need elaborate scaffolding. Claude Code already implements sophisticated context engineering via CLAUDE.md files, compaction (summarization at context limits), and glob/grep for just-in-time retrieval. Zechner's rationale: "10–20K tokens of tool descriptions per session is highway robbery" and "context engineering is paramount." Armin Ronacher (Sentry/Flask creator) summarized: "What's not in Pi matters most."

**This is the most important baseline.** If a frontier coding agent with a well-crafted CLAUDE.md achieves acceptable harmonization quality at lower development cost, all bespoke pipeline work is premature optimization. Claude Code supports batch processing (`/batch` command, v2.1.63+) with Git worktree isolation, and `--max-turns` / `--max-budget-usd` for resource control. Codex CLI offers equivalent sandboxed execution via Bubblewrap + seccomp on Linux.

### 2.4 Architecture D: Compositional LM Program (Matchmaker Pattern)

A fundamentally different paradigm from agent-based approaches: a fixed multi-stage pipeline of distinct LLM calls — no agent loop, no iterative refinement within a single run. **Matchmaker** (Seedat & van der Schaar, NeurIPS 2024 TRL Workshop) decomposes schema matching into: (1) candidate generation via dual retrieval (vector similarity + LLM reasoning with chain-of-thought), (2) candidate refinement (LLM narrows combined candidates), and (3) confidence scoring (MCQ format with an abstain option). It self-improves without labeled data via synthetic in-context demonstrations selected from high-scoring traces — DSPy bootstrapping.

The critical finding: **GPT-3.5 with Matchmaker's pipeline design matched simpler architectures using GPT-4**, suggesting pipeline design compensates for model weakness. **SCHEMORA** (2025) further improved on Matchmaker by ~4% at HitRate@3, adding metadata enrichment. **Magneto** (Liu et al., VLDB 2025) — already integrated into BDI-Kit — implements a related pattern: SLM-based candidate retrieval (fast, cheap) followed by LLM-based reranking (accurate, more expensive), and provides the GDC-SM benchmark with real tumor study datasets against GDC's 736-column schema.

**Key advantage for Harmonia:** Deterministic pipeline structure — each run follows the same stages. Each stage's prompts can be independently optimized via DSPy's MIPRO optimizer. **Key limitation:** No adaptability within a run. If candidate generation fails, there is no recovery mechanism. The pipeline also handles schema matching only — it does not cover value mapping, which is a separate and equally important step in GDC harmonization. Matchmaker's entropy-based deferral — using confidence score entropy to identify uncertain matches and escalate to humans — is directly applicable to Harmonia's human-in-the-loop requirements.

### 2.5 Architecture E: Direct Prompting

A single LLM call with the full source schema, target schema, and mapping instructions. No agent loop, no iterative refinement. The simplest possible approach and an essential lower-bound baseline. SCHEMORA's "Needle-in-the-Stack" experiment tested whether all candidate matches could fit in a single prompt with large context windows — this baseline **underperformed multi-stage methods by 10–20%**, confirming that single-call approaches are insufficient for complex schema matching even with frontier models. A 2025 study comparing direct prompting vs. agentic approaches for automotive software model querying found accuracy was comparable but the agentic approach was more token-efficient for large inputs. For small GEO datasets (<50 columns), direct prompting may be sufficient. For larger schemas, context limits force agentic or pipeline approaches.

### 2.6 Architecture F: Hierarchical Supervisor

A supervisor/orchestrator agent delegates to specialist sub-agents, each with focused knowledge and tools. The exemplar is **SRAgent** (Arc Institute, bioRxiv 2025), which built a hierarchical LangGraph workflow for mining the Sequence Read Archive. SRAgent's "agent-as-tool-factory" pattern wraps each lower-level agent as a callable tool for the supervisor:

```python
def create_esearch_agent(model_name=None, return_tool=True):
    model = set_model(model_name=model_name, agent_name="esearch")
    agent = create_react_agent(model=model, tools=[esearch], prompt=state_mod)
    if not return_tool:
        return agent  # Standalone CLI testing
    @tool
    async def invoke_esearch_agent(message, config):
        result = await agent.ainvoke({"messages": [HumanMessage(content=message)]}, config)
        return {"messages": [AIMessage(content=result["messages"][-1].content)]}
    return invoke_esearch_agent
```

This enables per-agent model configuration (gpt-4o for complex reasoning, gpt-4o-mini for routine tasks), standalone testing of each sub-agent, and hierarchical composition. SRAgent processed **208,939 SRA experiments** to build scBaseCount with 502+ million cells. For Harmonia, a supervisor pattern could delegate to a Schema Expert (with `match_schema`/`rank_schema_matches`), a Value Mapper (with `match_values`/`get_gdc_acceptable_values`), a Validator, and a Materializer. LangGraph's June 2025 benchmark on τ-bench showed supervisor patterns use more tokens than swarm patterns due to "translation" overhead, but both remain stable as distractor domains increase — unlike single agents, which degrade sharply.

**Estimated overhead:** 2–4× LLM calls compared to a single agent. Implementation effort is large — requires refactoring from Beaker's single-session model to a multi-session orchestration layer. Risk of over-engineering for the current Dou 2020 benchmark (17 columns, 190 rows), where a single agent can handle the full workflow.

### 2.7 Architecture G: Fan-Out/Fan-In Parallel Agents

For multi-table harmonization: spawn N parallel agents, each harmonizing one source table independently against the target schema, then fan results into a merge agent. LangGraph's `Send()` API implements this cleanly:

```python
def fan_out_tables(state):
    return [Send("harmonize_table", {"table": t}) for t in state["tables"]]
```

State fields use `Annotated[List[dict], operator.add]` to accumulate results from parallel nodes. One benchmark demonstrated **137× speedup** (61s → 0.45s) for parallel research queries. Concurrency is controlled by `max_concurrency` in LangGraph config or `asyncio.Semaphore` at the application level.

**For Harmonia:** This pattern becomes valuable with the 10-table CPTAC dataset (`ten_metadata_tables_harmonize/`). Each table's harmonization is independent — parallel processing is natural and carries no coordination risk. The main danger is cross-table consistency: different parallel agents may map the same concept differently. A lightweight post-merge validation step addresses this. Google ADK's `ParallelAgent` offers an alternative implementation.

### 2.8 Architecture H: Recursive Language Models

Zhang, Kraska, and Khattab (MIT CSAIL, arXiv:2512.24601, December 2025) proposed RLMs as a general inference paradigm that treats long prompts as an **external environment** rather than feeding them into the context window. The data is loaded as a Python variable in a sandboxed REPL, and the LLM writes code to inspect, partition, grep, and transform it, recursively invoking sub-LLMs on arbitrary snippets via a `llm_query()` function.

Performance gains are dramatic. On the OOLONG benchmark at 132K tokens, **RLM(GPT-5-mini) outperformed vanilla GPT-5 by 34+ raw accuracy points** (~114% improvement) at comparable cost. On BrowseComp-Plus with 1,000 documents (10M+ tokens), RLM(GPT-5) achieved **perfect accuracy** where GPT-5 alone could not fit the input. On the quadratic-complexity OOLONG-Pairs task, vanilla GPT-5 scored F1 = 0.04 (essentially useless) while full RLM achieved F1 = 58.00. RLMs handle inputs up to 100× beyond model context windows with no retraining.

**For Harmonia:** The RLM pattern maps directly to large-table harmonization. Load the source metadata table and GDC target schema into the REPL environment. The root LM writes Python to partition columns into semantically related groups (e.g., demographic columns, treatment columns, sample type columns). Sub-LMs perform matching on each group against the relevant GDC schema subset. Results aggregate programmatically. This is architecturally simpler than multi-agent fan-out — it is a single agent with recursive self-delegation — and avoids the coordination failures documented by Cemri et al.

The complementary **Chain-of-Agents** approach (Zhang et al., Google Research, NeurIPS 2024) showed that sequential worker agents processing chunks outperformed both full-context and RAG approaches on **all 8 datasets tested** with improvements up to 10%. A March 2026 paper ("Coding Agents are Effective Long-Context Processors," Cao et al.) demonstrated that placing massive text corpora into directory structures and delegating to coding agents achieves **88.5% on BrowseComp-Plus at 750M tokens** — outperforming published SOTA by 17.3% on average and scaling to 3 trillion tokens.

### 2.9 Architecture I: Critic/Verifier Pattern

A primary agent produces a mapping; a separate critic agent evaluates it against domain constraints. If the critic identifies errors, the primary agent is re-invoked with feedback, creating a cyclic improvement loop. The **Asymmetric Actor-Critic** pattern (arXiv:2604.00304) is particularly apt for harmonization: a powerful frontier LLM generates column mappings while a smaller, cheaper model validates them. This exploits the "generation-verification asymmetry" — generating correct mappings requires strong reasoning, but checking whether a mapping is plausible against GDC's controlled vocabulary is far easier. A Claude Sonnet/GPT-4o actor producing column mappings with a GPT-4o-mini/Haiku critic checking semantic plausibility creates a cost-effective quality gate.

**CellAtria** (Nouri et al., npj AI 2026) implements a variant using LangGraph's multi-actor architecture for scRNA-seq standardization, achieving production-scale ingestion on AWS EC2 — the closest published system to what Harmonia would build with a critic pattern.

### 2.10 Where Does GEO Metadata Harmonization Sit on the Complexity Spectrum?

GEO metadata harmonization occupies a **medium-complexity zone**: too complex for direct prompting (the GDC schema is too large for a single context window), well-suited for structured pipelines (the task decomposes naturally into schema matching → value mapping → validation), and generally not complex enough to warrant multi-agent orchestration for single-table tasks. The Dou 2020 benchmark (17 columns, 190 rows) is at the simpler end — a single CodeAct agent with good context engineering should handle it. The 10-table CPTAC dataset pushes toward fan-out parallelism. The GDC's full 736-column schema pushes toward RLM-style decomposition.

The spectrum, ordered by increasing complexity: **(E) Direct prompting** → **(D) Matchmaker pipeline** → **(B) CodeAct agent** → **(A) ReAct + domain tools** → **(C) Frontier coding agent** → **(I) Critic/verifier** → **(H) RLM decomposition** → **(G) Fan-out parallel** → **(F) Hierarchical supervisor**. For Harmonia's benchmark experiments, the sweet spot is architectures B–D with architecture C as the mandatory baseline.

---

## 3. The Case Against Multi-Agent as Default

### 3.1 Empirical Failure Analysis

Three independent lines of evidence converge on the same conclusion: multi-agent systems fail frequently and predictably for sequential reasoning tasks.

**Cemri et al. (UC Berkeley/Stanford, NeurIPS 2025)** conducted the first systematic failure analysis of multi-agent systems, annotating **1,600+ traces across 7 MAS frameworks** with 6 expert annotators (Cohen's κ = 0.88). They identified 14 failure modes in 3 categories: specification/design issues (ambiguous roles, poor decomposition), inter-agent misalignment (conflicting interpretations, coordination failures), and task verification/termination failures (premature termination, weak quality control). Failure rates ranged from **41% to 86.7%** across frameworks. The most damaging finding: attempted interventions (improved role specifications, enhanced orchestration) **failed to resolve fundamental coordination problems**, suggesting the failures are architectural, not tunable.

**Google DeepMind's scaling study** (Kim et al., "Towards a Science of Scaling Agent Systems," January 2026) tested **180 configurations across 5 architectures and 3 LLM families**. The results are stark: parallelizable tasks (e.g., simultaneously analyzing revenue trends, cost structures, market comparisons) saw centralized multi-agent coordination improve performance by **+80.9%**. But sequential reasoning tasks (e.g., multi-step planning) saw every multi-agent variant **degrade performance by 39–70%**, because communication fragmented the reasoning process, leaving insufficient "cognitive budget" for the actual task. Unstructured multi-agent networks amplified errors up to **17.2×**; centralized orchestrators contained this to 4.4×. Coordination gains plateau beyond 4 agents. A decision-theoretic analysis (arXiv:2603.26993) proves formally that multi-agent adds value only when agents access genuinely new exogenous information, not when they share the same context and model.

**Kapoor et al. (Princeton, "AI Agents That Matter," TMLR 2024)** demonstrated that current agent benchmarks create perverse incentives by optimizing solely for accuracy. Simple retry strategies with GPT-4 achieved **93.2% accuracy on HumanEval at $2.45 mean cost**, outperforming several SOTA multi-agent systems. Their five recommendations center on cost-controlled evaluation, joint accuracy-cost optimization, and preventing benchmark shortcuts.

### 3.2 The Simplicity vs. Capability Tradeoff

The pi-coding-agent philosophy (Zechner, November 2025) provides a practical existence proof: **4 tools, a system prompt under 1,000 tokens**, and competitive Terminal-Bench performance against heavyweight agent harnesses. Gao et al. (May 2025, "Single-agent or Multi-agent Systems? Why Not Both?") show that MAS advantages diminish as model capability improves, and recommend a **hybrid cascade** — try single-agent first, escalate to multi-agent on failure — which improved accuracy by 1.1–12% while reducing costs by up to 20%.

The AlphaCodium study (Ridnik et al., January 2024) demonstrates the power of "flow engineering": structured pipelines boosted GPT-4 accuracy on CodeContests from **19% to 44%** — a 2.3× improvement using only 15–20 LLM calls per problem, with 95% of development time spent on pipeline design rather than prompt engineering. This directly supports the Matchmaker/DSPy approach: invest in pipeline structure, not agent complexity.

For the Harmonia team, the hierarchy of investment should be: (1) context engineering, (2) pipeline design (DSPy/Matchmaker), (3) model selection, (4) single-agent sophistication (CodeAct), (5) critic/verifier patterns, and only then (6) multi-agent orchestration.

### 3.3 When Multi-Agent Does Earn Its Overhead

Multi-agent is not universally wrong — it is specifically wrong as a *default*. It earns its overhead under three conditions, all supported by the DeepMind study:

**Genuinely parallelizable sub-tasks:** Processing 10 independent source tables simultaneously. Each table's harmonization is independent; fan-out eliminates sequential bottlenecks. Cap at ≤4 parallel agents (the DeepMind plateau).

**Heterogeneous tool landscapes:** SRAgent's success reflects genuinely different tools and APIs (NCBI Entrez, ontology services, database writes). Metadata harmonization has a narrower tool landscape (5 BDI-Kit tools), which may not warrant the coordination overhead.

**Verification asymmetry:** The Asymmetric Actor-Critic pattern works because generation and verification require different capabilities. A frontier model generating mappings + a cheap model checking against GDC vocabulary constraints is a cost-effective architecture with minimal coordination complexity (only 2 agents, deterministic interaction).

---

## 4. Context Engineering

### 4.1 Why Context Matters More Than Architecture

The 2025–2026 consensus from Anthropic, LangChain, Cognition AI, and practitioners is that **"most agent failures are not model failures — they are context failures."** Andrej Karpathy framed it memorably: "LLMs are a new kind of operating system — the LLM is the CPU and its context window is the RAM." Anthropic's engineering team demonstrated that **a focused 300-token context often outperforms an unfocused 113,000-token context** in conversation tasks. This finding reframes multi-agent systems as a context management strategy (partitioning context across specialists) rather than a coordination strategy — and suggests that better context engineering within a single agent may achieve the same benefit without coordination overhead.

### 4.2 The Four Strategies: Write, Select, Compress, Isolate

Anthropic's framework (September 2025) identifies four core strategies for context engineering:

**Write:** Persist critical information outside the context window using scratchpads, files, or structured state. For Harmonia, this means maintaining a running "harmonization state" document tracking completed column mappings, confidence scores, and unresolved ambiguities — persisted to disk, not held in the conversation.

**Select:** Retrieve only relevant context via just-in-time retrieval rather than pre-loading everything. Rather than dumping the full GDC 736-column schema into the prompt, retrieve only the relevant column group for the current matching step. BDI-Kit's Magneto already implements this via SLM-based candidate retrieval.

**Compress:** Summarize or trim older context to preserve budget. JetBrains Research (NeurIPS 2025) found that **observation masking** — simply removing verbose intermediate outputs from prior steps while retaining decisions and reasoning — matched LLM summarization in cost savings while maintaining problem-solving performance. For Harmonia, early schema matching observations shouldn't clutter the context during later value mapping. Cognition AI uses fine-tuned models specifically for agent-agent boundary summarization.

**Isolate:** Partition context across specialized agents or tools. This is the one strategy that connects to multi-agent — but it can also be achieved with a single agent using stage-specific system prompts or tool-scoped context injection.

### 4.3 Context Engineering for Harmonia Specifically

For the Harmonia fork, context engineering translates to concrete design decisions:

The system prompt should contain **5–10 curated examples of difficult GDC mappings** (e.g., "Ca." → "Neoplasm", "Rad" → "Radiation Therapy (NCIT:C15313)"), not exhaustive ontology dumps. The GDC target schema should be provided as **retrievable context** — Magneto narrows candidates before the LLM reasons about them, ensuring only relevant columns enter the context. Prior-step observations should be **masked or summarized** before entering subsequent steps, preserving the context budget for the current task. The pi-coding-agent's "12-Factor Agent" principle applies: own your context window, and treat every token as a scarce resource.

---

## 5. Schema Matching Pipeline Design

### 5.1 The Matchmaker Compositional Pattern

Matchmaker (Seedat & van der Schaar, NeurIPS 2024 TRL Workshop) represents the state of the art in LLM-based schema matching via compositional program design. Its three-stage pipeline — candidate generation via dual retrieval, refinement via LLM narrowing, confidence scoring with an abstain option — achieves competitive performance without any agent loop. The key architectural insight is that each stage can be independently optimized: retrieval parameters, refinement prompts, and scoring thresholds are separate tuning knobs.

Matchmaker's self-improvement via DSPy bootstrapping is particularly relevant: it generates synthetic in-context examples from high-scoring traces, enabling zero-shot self-improvement without labeled data. This means the pipeline gets better with use, accumulating effective demonstrations from successful harmonization runs.

The entropy-based deferral mechanism — routing low-confidence matches to human reviewers based on confidence score entropy — outperforms random deferral and directly addresses Harmonia's human-in-the-loop requirement. Matches where the model is genuinely uncertain (high entropy across candidate scores) are escalated; matches with clear winners are auto-approved.

### 5.2 Magneto: SLM + LLM Retrieval-Reranking

Magneto (Liu et al., VLDB 2025), already integrated into BDI-Kit, implements a two-phase pattern: a small language model (SLM) performs fast candidate retrieval via embedding similarity, then a large language model performs expensive reranking of the top candidates. This retrieve-then-validate approach is computationally efficient — the SLM processes all O(n×m) source-target column pairs cheaply, while the LLM only evaluates the top-k candidates.

Magneto's GDC-SM benchmark — matching real tumor study datasets against GDC's 736-column schema — provides the most directly relevant performance reference for Harmonia. It outperforms all baselines on this benchmark, confirming the SLM+LLM pattern's effectiveness for exactly the domain Harmonia targets.

### 5.3 DSPy Compilation for Systematic Optimization

DSPy (Khattab et al., ICLR 2024) provides the optimization framework for these pipelines. Rather than hand-crafting prompts, DSPy compiles declarative program specifications into optimized prompt chains via its MIPRO bootstrapping optimizer. Published results show **25–65% improvements over hand-crafted prompts** and performance rivaling expert demonstrations.

For Harmonia, the compilation strategy would be: define the matching pipeline as a DSPy program (candidate retrieval → refinement → scoring), use the GDC-SM benchmark's ground-truth mappings as the optimization target, and let MIPRO bootstrap few-shot examples from high-scoring traces. The resulting compiled pipeline has deterministic structure with optimized prompts — each stage runs the same code path with systematically selected demonstrations.

**Open question:** Neither report fully specifies the concrete DSPy compilation strategy for GDC — what training signal to use (exact match? F1? human ratings?), how many bootstrapped examples to retain, and which optimizer variant (MIPRO vs. BootstrapFewShot vs. newer alternatives). This is a critical implementation detail the Harmonia team will need to resolve experimentally.

---

## 6. Long-Context Processing for Large Tables

### 6.1 Recursive Language Models

Zhang, Kraska, and Khattab's RLM framework (MIT CSAIL, arXiv:2512.24601, December 2025) provides the most principled solution to context window limitations. Instead of truncating, summarizing, or partitioning data across agents, the RLM loads the full dataset as a Python variable in a sandboxed REPL. The root LM writes code to inspect the data structure, partition it into manageable chunks, and invoke sub-LM calls via a `llm_query()` function on each chunk. Results aggregate programmatically.

The performance improvements across benchmarks are substantial: RLM using GPT-5-mini outperformed vanilla GPT-5 by **34+ raw accuracy points** on OOLONG, achieved **perfect accuracy** on BrowseComp-Plus where GPT-5 alone could not even fit the input, and improved OOLONG-Pairs F1 from 0.04 to 58.00. All at comparable cost and with no retraining — RLMs work as a drop-in replacement for standard LLM calls. The post-trained RLM-Qwen3-8B model demonstrates that native recursive capability can be baked into smaller models, outperforming base Qwen3-8B by 28.3% on average.

### 6.2 Chain-of-Agents and Coding Agents as Long-Context Processors

Two complementary approaches extend the RLM insight. **Chain-of-Agents** (Zhang et al., Google Research, NeurIPS 2024) uses sequential worker agents that each process a chunk of the input and pass a condensed summary to the next worker. The final aggregator synthesizes all summaries. This outperformed both full-context and RAG approaches on **all 8 datasets tested**, with improvements up to 10%.

**"Coding Agents are Effective Long-Context Processors"** (Cao et al., March 2026) takes this further: place massive text corpora into directory structures and let a coding agent navigate them via file operations (read, grep, list). This achieves **88.5% on BrowseComp-Plus at 750M tokens**, outperforming published SOTA by 17.3% on average, and scales to **3 trillion tokens**. The key insight: coding agents already have the infrastructure for long-context processing — they just need to treat documents as files rather than in-context text.

### 6.3 Application to GDC's 736-Column Schema

For harmonizing against GDC's full 736-column target schema, the RLM pattern maps directly: load source metadata and GDC schema into the REPL, let the root LM partition source columns into semantically related groups (demographic, treatment, sample type, etc.), invoke sub-LMs to match each group against the relevant GDC schema subset, and aggregate results. This avoids loading the full 736-column schema into a single prompt (which would consume most of the context budget) while maintaining coherence through programmatic aggregation.

For the Dou 2020 benchmark (17 columns), RLM is unnecessary — the input fits comfortably within modern context windows. RLM becomes valuable with the 10-table CPTAC dataset or when processing GEO datasets with hundreds of columns against the full GDC schema.

---

## 7. Observability, Tracing, and Experiment Infrastructure

### 7.1 Platform Comparison

The LLM observability landscape has stratified by 2026. For Harmonia's HPC environment, the relevant platforms are:

**Phoenix/Arize** (7,800+ GitHub stars, Elastic License 2.0): Fully open-source, self-hostable with no feature gates, built natively on OpenTelemetry + OpenInference. Supports auto-instrumentation for LangChain, LlamaIndex, DSPy, OpenAI, and Anthropic. Runs as a single container, accepts traces via standard OTLP protocol, includes built-in LLM-based evaluation. The strongest choice for academic/HPC environments that need on-premises deployment with no cloud dependencies.

**Langfuse** (19,000+ GitHub stars, MIT license): Fully self-hostable with the strongest open-source prompt version control — auto-assigned version IDs, custom labels (production/staging/experiment-v1), protected labels, prompt diffs, and environment bindings. Its SDK v3 is a thin OTel wrapper and can operate as an OTLP backend. Best for teams needing rigorous prompt versioning and A/B testing of prompt variants.

**LangSmith** (LangChain): Deepest LangGraph integration, handles 1B+ traces, but requires Enterprise tier for self-hosting and charges per-trace — problematic for 100+ model experiments generating millions of traces.

**W&B Weave** (Weights & Biases): Extends the mature ML experiment tracking platform to LLM observability. Academic free licenses available (25GB/month, 100 seats). Best for teams already in the W&B ecosystem.

**OpenLLMetry** (Traceloop, Apache 2.0): A pure instrumentation library that generates standard OTel data exportable to any backend (Datadog, Grafana, Jaeger, or Phoenix). Not a platform but a connector layer — worth using when you need backend flexibility.

### 7.2 OpenTelemetry Span Hierarchy for Agent Systems

The emerging convention for agent tracing structures spans as: root `agent.execute` span → child `agent.llm_step` spans (one per reasoning iteration) → `agent.tool.{name}` spans for tool executions → `sub-agent-{id}` spans for delegated sub-agents. The OTel GenAI semantic conventions (experimental in OTel 1.37+) standardize attributes: `gen_ai.request.model`, `gen_ai.usage.prompt_tokens`, `gen_ai.response.finish_reasons`.

For Harmonia's existing Phoenix/OTel integration (span hierarchy: AGENT → CHAIN → LLM → TOOL), extending to multi-agent requires: (1) propagating Trace IDs across agent boundaries via OTel context propagation, (2) descriptive span naming (`schema_matcher:gdc_column_match` rather than generic `tool_call`), and (3) capturing key attributes (model name, temperature, token counts, prompt version hash, cost) on every span. AG2's February 2026 implementation demonstrates this working in practice with Jaeger visualization.

For the 20-class failure taxonomy already in the system, each failure class should map to a span event with structured attributes: `failure.taxonomy_class`, `failure.agent_id`, `failure.recovery_attempted`. This enables aggregating failure distributions across experiments via standard OTel queries.

### 7.3 Recommended Observability Stack for HPC

The recommended stack for Harmonia: **OpenLLMetry instrumentors** generating OpenInference-compliant traces → exported via **OTLP to self-hosted Phoenix** for trace visualization and analysis → **Langfuse** handling prompt versioning with experiment-specific labels (e.g., "codeact-v2.1-dou2020", "react-v1.0-cptac") → exact-match LLM response caching integrated with the tracing layer. Phoenix server managed by the existing `scripts/ensure_phoenix_server.py`. All traces, cache databases, and prompt versions stored as immutable experiment artifacts alongside code commits.

---

## 8. Deterministic Reproducibility

### 8.1 Why Temperature=0 Is Not Enough

A persistent misconception in LLM-based science is that `temperature=0` guarantees deterministic outputs. **It does not.** Floating-point non-associativity means `(a + b) + c ≠ a + (b + c)`, so changing operation order — which varies with GPU parallelism, kernel scheduling, and co-batched requests — changes the final token selection even with greedy decoding. Mixture-of-Experts architectures (used by GPT-4, Mixtral) introduce additional batch-dependent non-determinism via expert routing. OpenAI's `seed` parameter is explicitly "best effort"; Anthropic does not offer a seed parameter.

An alarming 2025 audit of 85 LLM-centric papers from ICSE/ASE 2024 found that of 18 with artifacts using OpenAI models, **none could be fully reproduced** — highlighting how widespread and consequential this problem is.

### 8.2 The Four-Layer Reproducibility Strategy

Practical reproducibility demands defense in depth — four complementary mechanisms:

**Layer 1 — Exact-match LLM call caching:** Hash the full prompt string (SHA-256) + model ID + generation parameters (temperature, top_p, max_tokens) as the cache key. Store the first successful response. Serve cached responses for identical subsequent requests. This makes the application deterministic at the interface boundary without requiring model-level determinism. AutoGen's cache system is exemplary: `cache_seed=42` creates a named cache guaranteeing identical replay, while `cache_seed=None` disables caching for fresh generation. For Harmonia, cache ALL LLM calls during each experiment run.

**Layer 2 — Configuration snapshots:** Capture model name/version, temperature, top_p, seed (if available), system prompt text, tool definitions, API version, and `system_fingerprint` (OpenAI) for every run. The existing `config_snapshot.yaml` should be extended to include the prompt template version hash and litellm model string.

**Layer 3 — Prompt versioning:** Semantic versioning (major.minor.patch) for all prompts: major bumps for model or output schema changes, minor for new features, patch for typo fixes. Langfuse provides built-in versioning with environment bindings (dev → "latest", prod → "v1.2.0"). Each experiment run records the exact prompt version used.

**Layer 4 — Materialized intermediate outputs:** Save the output of every pipeline stage (candidate retrieval results, refinement scores, final mappings) as versioned artifacts keyed by `(prompt_version + input_hash + model_params)`. This enables restarting from any checkpoint, comparing intermediate results across experiments, and diagnosing exactly where two experiment runs diverge.

### 8.3 The Materialize-Mapping Pattern

BDI-Kit's `materialize_mapping` tool produces a deterministic Python script that applies the discovered mapping without any LLM calls. This cleanly separates the **LLM-assisted discovery phase** (non-deterministic, expensive, requiring human oversight) from the **deterministic execution phase** (reproducible, cheap, automatable). For scientific experiments, this separation is essential: the discovery phase is what you compare across architectures, while the execution phase is what you deploy in production. Every experiment should produce both the mapping decisions and the materialized script as paired artifacts.

---

## 9. Sandboxed Execution Environments

### 9.1 Cloud Sandboxes vs. HPC Reality

The sandboxing landscape divides sharply between cloud-native and HPC-compatible solutions. **E2B** (Firecracker microVMs, ~150ms cold start, used by ~88% of Fortune 100) provides strong isolation but requires cloud infrastructure with KVM support. **Modal** ($1.1B valuation, sub-second cold starts, serverless GPU, gVisor isolation) scales to 20,000 concurrent containers but is a managed cloud service with no self-hosting. **Daytona** ($24M Series A, sub-90ms creation, Docker-based) offers self-hosting but lacks native SLURM integration. **None of these work on traditional HPC compute nodes**, which typically lack outbound internet access and KVM virtualization capabilities.

**Docker + gVisor** provides meaningful security isolation without requiring KVM — gVisor's user-space kernel intercepts all syscalls, exposing only ~70 host syscalls vs. hundreds for standard containers. This is the strongest isolation option for HPC nodes that support it, but requires administrator cooperation to install. **Firecracker microVMs** boot in ~28ms from snapshots but require KVM — rarely available on shared HPC compute nodes.

### 9.2 Apptainer: The HPC-Native Choice

**Apptainer** (formerly Singularity) remains the only container runtime natively compatible with HPC. It runs unprivileged (no root daemon), uses portable single-file `.sif` images, and integrates directly with SLURM (`srun apptainer exec --nv container.sif command`). The `--nv` flag passes through GPUs for local model inference via Ollama. HPC centers universally support it.

Harmonia's existing architecture packages the agent runtime in `harmonia_beaker_LLM_agent_environment_apptainer.sif` (Python 3.11, litellm, BDI-Kit 0.9.0). Bind mounts provide: `workspace_mount/` → `/workspace` (writable), per-file data mounts from config → `/workspace/data/` (read-only overlay), and results → `/workspace/results/` (writable, experiment-specific). This layered mount scheme — with Apptainer providing process-level containment and the Beaker kernel's proxy architecture providing an additional abstraction layer between agent-generated code and the host filesystem — is appropriate for a research environment where the threat model is "protect against buggy agent code" rather than "protect against adversarial untrusted code."

### 9.3 Running Frontier Coding Agents in Containers

**Claude Code** supports headless automation via `-p` (print mode) with `--dangerously-skip-permissions` for isolated environments, `--output-format json` for structured output, and `--max-turns`/`--max-budget-usd` for resource control. It can run inside Apptainer containers on SLURM with only an `ANTHROPIC_API_KEY` and outbound HTTPS access. For batch processing of multiple datasets, Claude Code's `/batch` command (v2.1.63+) decomposes work into 5–30 independent units with Git worktree isolation — directly applicable to parallel harmonization of independent source tables.

**Codex CLI** offers equivalent functionality via `codex exec --json --full-auto`. It uses Bubblewrap + seccomp on Linux for its own internal sandboxing but should rely on container-level isolation when running inside Apptainer. Both tools treat the host filesystem as their working environment, making container bind mounts the natural integration point.

For the frontier baseline experiment (Architecture C), the setup is: Apptainer `.sif` with Python, BDI-Kit, pandas, and the relevant Claude/OpenAI CLI installed. SLURM job script allocates resources, starts the container, runs the agent with `--max-turns 30 --max-budget-usd 5.00`, and captures the output. Network access from login/gateway nodes routes API calls.

---

## 10. Human-in-the-Loop Patterns

### 10.1 Confidence-Based Routing and Entropy Deferral

Human-in-the-loop escalation should be driven by quantified uncertainty, not arbitrary thresholds. Two complementary frameworks address this:

The **LLM Performance Predictors** framework (Bachar et al., AAMAS 2026) combines gray-box features (token-level log-probabilities, entropy) with black-box features (verbalized confidence) to train a meta-model predicting when the LLM will be wrong. This enables cost-aware routing between LLM and human judgment — auto-approve when the predictor is confident, escalate when it is not.

For simpler implementation, the **"Think Just Enough"** framework (arXiv:2510.08146) uses Shannon entropy at the reasoning-step level to determine when confidence is sufficient, achieving **25–50% cost reduction** while preserving accuracy. Threshold calibration requires only 5–10 examples, making it practical for Harmonia's benchmark.

Matchmaker's entropy-based deferral — using the entropy of confidence scores across candidate matches to identify uncertain cases — provides a domain-specific implementation of the same principle. High entropy means the model is genuinely uncertain between candidates; low entropy means one candidate dominates. This consistently outperforms random deferral.

### 10.2 The Magentic-UI Reference Architecture

**Magentic-UI** (Microsoft Research, July 2025) demonstrates the state of the art in HITL agent interaction, implementing six mechanisms: (1) **co-planning** — users view and modify agent plans before execution; (2) **co-tasking** — users pause and provide feedback during execution; (3) **action guards** — approval required before irreversible actions; (4) **answer verification** — users validate outputs; (5) **long-term memory with plan learning** — successful plans are cached for reuse; (6) **multi-tasking** — users work on other things while the agent runs. With these mechanisms, autonomous task completion improved from **30.3% to 51.9%** — a 71% improvement — with help requested in only 10% of enhanced tasks.

### 10.3 HITL Design for Harmonia

For Harmonia, the most applicable patterns are:

**Progressive disclosure.** Show the domain expert a summary of proposed column mappings with confidence scores. On request, expand to show the agent's reasoning, alternative candidates, and source data context. The existing Plotly Dash dashboard's Trace Explorer tab provides the infrastructure for this.

**Co-planning for schema matching.** Before the agent begins value mapping, present the proposed column-to-GDC mapping for expert review. The expert can approve, reject, or modify individual mapping decisions. This catches systematic errors (e.g., mapping "Stage" to the wrong GDC stage concept) before they propagate to value mapping.

**Entropy-based auto-approval.** High-confidence matches (low entropy across candidate scores) are auto-approved. Ambiguous matches (e.g., "Column 'Stage' could map to either 'ajcc_pathologic_stage' or 'clinical_stage'") are escalated with the specific ambiguity stated.

**The Kosmos world model pattern** (Mitchener et al., November 2025): maintain a structured harmonization state — a queryable record of entities, relationships, mappings, confidence scores, and open questions — that persists across agent steps and serves as both coordination mechanism and audit trail. Kosmos demonstrated this pattern at scale: 200 agent rollouts, 42,000 lines of code, 1,500 papers per run, with independent scientists rating **79.4% of statements as accurate**. For Harmonia, a lighter version tracking column mapping status (mapped/ambiguous/unmapped) and confidence would provide the same structural benefit.

---

## 11. Architectural Recommendations for Harmonia

### 11.1 The Frontier Baseline Imperative

Before investing in bespoke pipeline infrastructure, **run Claude Code headless on the Dou 2020 benchmark.** Provide the source CSV, the GDC target schema, BDI-Kit as an installed library, and a well-crafted CLAUDE.md describing the harmonization task with 5–10 examples of difficult mappings. Measure accuracy (column mapping F1, value mapping F1), cost (total API spend), and failure modes. This establishes the cost-accuracy baseline that all subsequent architectures must beat — the "Kapoor test."

If the frontier agent achieves ≥85% column mapping accuracy at <$5 per dataset, the bespoke pipeline may not be worth the engineering investment for the first publication. If it struggles with GDC's complex vocabulary or multi-step value mapping, the structured pipeline approach is validated. Either outcome is scientifically valuable.

### 11.2 Proposed Four-Phase Architecture

**Phase 1 — Frontier Baseline (weeks 1–4):**
Deploy Claude Code headless in Apptainer on SLURM. Run on Dou 2020 benchmark with and without BDI-Kit as an available library. Instrument with Phoenix/OTel. Record cost, accuracy, and failure modes using the existing 20-class taxonomy. Run Codex CLI as a second data point. This phase requires minimal new infrastructure — the existing Apptainer setup, a CLAUDE.md file, and the evaluation pipeline.

**Phase 2 — CodeAct + Magneto Pipeline (months 2–3):**
Build the primary bespoke architecture: a CodeAct agent that writes Python using BDI-Kit's Magneto (SLM retrieval → LLM reranking) as library functions, with the agent handling orchestration, error recovery, and edge cases via generated code. Compile prompts via DSPy's MIPRO optimizer against the GDC-SM benchmark. Implement the four-layer reproducibility strategy (caching, config snapshots, Langfuse prompt versioning, materialized intermediates). Run head-to-head against Phase 1 baseline on identical benchmark.

**Phase 3 — Fan-Out for Multi-Table + Critic Verification (months 3–4):**
Only if Phase 2 validates the bespoke pipeline: add LangGraph's `Send()` pattern for parallel processing of the 10-table CPTAC dataset. Each parallel branch runs the Phase 2 pipeline independently. A lightweight aggregator merges results and checks cross-table consistency. Add the Asymmetric Actor-Critic pattern: the primary agent (frontier model) generates mappings, a cheaper critic model validates against GDC vocabulary constraints. Entropy-based confidence routing escalates ambiguous mappings to human review.

**Phase 4 — RLM for Large Schemas + HITL Interface (months 5–6):**
Implement the RLM pattern for datasets exceeding practical context limits: load source data as a Python variable in the agent's REPL, partition columns into semantic groups via code, process each group against the relevant GDC schema subset using recursive sub-LM calls, aggregate results. Build progressive disclosure HITL interface in the existing Plotly Dash dashboard. Implement co-planning for schema matching review.

### 11.3 What to Avoid

**Do not start with a hierarchical multi-agent supervisor.** Cemri et al.'s finding that multi-agent gains are minimal and failure modes are architectural argues against premature complexity. SRAgent's success was driven by a genuinely heterogeneous tool landscape (NCBI APIs, ontology services, databases); Harmonia's tool landscape is narrower.

**Do not build a LangGraph orchestration layer before validating the single-agent approach.** The coordination overhead (2–4× LLM calls) must be justified by measured performance gains on the actual benchmark, not by architectural fashion.

**Do not optimize for the 10-table CPTAC dataset before solving the 1-table Dou 2020 benchmark.** The first publication needs solid results on the primary benchmark. Fan-out and RLM can wait.

### 11.4 Phased Implementation Roadmap

| Phase | Timeline | Focus | Go/No-Go Gate | Deliverable |
|-------|----------|-------|---------------|-------------|
| 1 | Weeks 1–4 | Frontier baseline | If accuracy ≥85%: stop and publish | Baseline cost-accuracy numbers |
| 2 | Months 2–3 | CodeAct + Magneto pipeline | Must beat Phase 1 on Pareto frontier | Head-to-head comparison paper |
| 3 | Months 3–4 | Fan-out + critic verification | Only if multi-table needed | CPTAC 10-table results |
| 4 | Months 5–6 | RLM + HITL interface | Only for large-schema experiments | Full-schema harmonization |

Each phase has an explicit go/no-go gate. If Phase 1 proves the frontier sufficient, the publication shifts from "our bespoke pipeline beats the frontier" to "the frontier is surprisingly effective for metadata harmonization" — still a valid and publishable finding.

---

## 12. Gap Analysis and Open Questions

**Concrete DSPy compilation strategy for GDC.** The pipeline design sections recommend DSPy-compiled prompts but do not specify: what training signal to use (exact match? F1? human ratings?), how many bootstrapped examples to retain, which DSPy optimizer variant (MIPRO vs. BootstrapFewShot), or how to handle the cold-start problem (no prior successful traces to bootstrap from). This is the highest-priority implementation question.

**Local vs. cloud LLM performance.** Harmonia supports 100+ models via litellm and Ollama on HPC GPUs, but no systematic comparison exists of local model performance (Llama 3.1 70B, Mixtral 8x22B) vs. cloud model performance (Claude Sonnet, GPT-4o) on GDC harmonization tasks. The cost/latency/quality tradeoff is critical for determining the operating point.

**The existing failure taxonomy.** The 20-class failure taxonomy (v1.2) across 6 categories — Infrastructure, Model Config, LLM Behavioral, Data/Config, Output, Diagnostic — is a valuable research asset that neither source report deeply analyzes. Understanding the frequency distribution of failure modes across the existing experiment runs would directly inform which architectural changes matter most.

**GDC schema-specific challenges.** The 736-column target schema, GDC's acceptable values vocabulary, and the specific difficulties of biomedical metadata (ambiguous abbreviations like "Ca." for cancer, inconsistent unit conventions, multi-valued columns, free-text fields requiring ontology mapping) deserve dedicated analysis. The difficulty distribution across GDC columns is likely highly skewed — a few columns account for most harmonization errors.

**The patterns_for_harmonia.md analysis.** The 8 transferable SRAgent patterns with effort estimates and risk assessments (agent-as-tool factory, model factory, structured output with retry, parallel fan-out, regex-first extraction, per-agent config, Rich console display, graph visualization) are directly actionable but underutilized. Patterns 3 (structured output with retry) and 5 (regex-first with LLM fallback) are low-risk, high-value additions that don't require architectural changes.

**Value mapping as a distinct sub-problem.** Schema matching (column-to-column) and value mapping (value-to-vocabulary) are distinct sub-problems with different characteristics. Schema matching is a small-N classification problem (tens to hundreds of column pairs); value mapping is a large-N transformation problem (thousands of cell values). The optimal architecture for each may differ — Matchmaker addresses schema matching but not value mapping.

**Cross-model behavioral differences.** Different LLMs exhibit qualitatively different failure modes on harmonization tasks (as captured in the failure taxonomy). A systematic analysis of model-specific failure patterns would inform both model selection and architecture design.

---

## 13. Further Reading

**Agent Architecture Foundations**
- Wang et al. (2024). "Executable Code Actions Elicit Better LLM Agents." ICML 2024. The foundational CodeAct paper. [arXiv:2402.01030]
- Cemri et al. (2025). "Why Do Multi-Agent LLM Systems Fail?" NeurIPS 2025 Datasets Track. The definitive failure analysis — 1,600+ traces, 14 failure modes. [arXiv:2503.13657]
- Kapoor et al. (2024). "AI Agents That Matter." TMLR. Cost-accuracy Pareto evaluation methodology. [arXiv:2407.01502]
- Kim et al. (2026). "Towards a Science of Scaling Agent Systems." Google DeepMind. 180-configuration empirical study. [research.google]

**Schema Matching and Harmonization**
- Seedat & van der Schaar (2024). "Matchmaker: Self-Improving LLM Programs for Schema Matching." NeurIPS 2024 TRL Workshop. Compositional pipeline with DSPy bootstrapping. [arXiv:2410.24105]
- Liu et al. (2025). "Magneto: Combining Small and Large Language Models for Schema Matching." PVLDB. SLM+LLM retrieval-reranking with GDC benchmark. [arXiv:2412.08194]
- Lopez et al. (2026). "BDI-Kit: An AI-powered toolkit for biomedical data harmonization." Patterns. The system Harmonia extends. [Cell Press]

**Long-Context Processing**
- Zhang, Kraska & Khattab (2025). "Recursive Language Models." MIT CSAIL. Data as external environment, recursive sub-LM calls. [arXiv:2512.24601]
- Cao et al. (2026). "Coding Agents are Effective Long-Context Processors." 88.5% on BrowseComp-Plus at 750M tokens. [arXiv:2603.20432]
- Zhang et al. (2024). "Chain of Agents." Google Research, NeurIPS 2024. Sequential workers outperform RAG on all 8 datasets. [research.google]

**Context Engineering**
- Anthropic (2025). "Effective context engineering for AI agents." Write/Select/Compress/Isolate framework. [anthropic.com/engineering]
- JetBrains Research (2025). "Cutting Through the Noise: Smarter Context Management for LLM-Powered Agents." Observation masking. NeurIPS 2025. [blog.jetbrains.com/research]

**Scientific Agents**
- Mitchener et al. (2025). "Kosmos: An AI Scientist for Autonomous Discovery." Structured world model, 200 rollouts, 79.4% accuracy. [arXiv:2511.02824]
- SRAgent / scBaseCount (2025). Agent-as-tool-factory for single-cell RNA-seq. Arc Institute. [bioRxiv]

**Minimal Agent Philosophy**
- Zechner (2025). "What I learned building an opinionated and minimal coding agent." Pi-coding-agent: 4 tools, <1K system prompt. [mariozechner.at]
- Ridnik et al. (2024). "Code Generation with AlphaCodium: From Prompt Engineering to Flow Engineering." Pipeline design > prompt engineering. [arXiv:2401.08500]

**Observability and Reproducibility**
- OpenInference Specification. AI-specific OTel semantic conventions. [arize-ai.github.io/openinference]
- Langfuse Prompt Version Control. [langfuse.com/docs/prompt-management]

**Human-in-the-Loop**
- Microsoft Research (2025). "Magentic-UI: Towards Human-in-the-loop Agentic Systems." 6 HITL mechanisms, 30.3%→51.9% improvement. [microsoft.com/research]
- Bachar et al. (2026). "LLM Performance Predictors." Gray-box + black-box features for confidence routing. AAMAS 2026.

**Multi-Agent Frameworks**
- LangGraph multi-agent documentation. Supervisor, router, subagent-as-tool patterns. [docs.langchain.com]
- Gao et al. (2025). "Single-agent or Multi-agent Systems? Why Not Both?" Hybrid cascade approach. [arXiv:2505.18286]

