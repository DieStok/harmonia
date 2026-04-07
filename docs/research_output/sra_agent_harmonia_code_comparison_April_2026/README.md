# Research Output: SRAgent Analysis and Frontier Practices for Harmonia

**Date:** 01-04-2026

This directory contains the results of a multi-phase research investigation into the SRAgent codebase, its companion paper (scBaseCount), comparative architecture analysis against Harmonia, and frontier practices for scientific metadata extraction agents.

---

## Suggested Reading Order

For a full understanding, read in this order:

1. **Start here** -- `02_paper_analysis/paper_summary_and_findings.md` (understand the problem and system)
2. **Architecture overview** -- `01_sragent_codebase_analysis/full_codebase_overview.md` (how SRAgent is built)
3. **How it runs** -- `01_sragent_codebase_analysis/flow_diagrams.md` (execution flows)
4. **Comparison** -- `03_comparative_architecture/sragent_vs_harmonia_comparison.md` (side-by-side with Harmonia)
5. **What to adopt** -- `03_comparative_architecture/patterns_for_harmonia.md` (actionable patterns)
6. **What to preserve** -- `03_comparative_architecture/harmonia_strengths.md` (Harmonia's advantages)
7. **Synthesis** -- `04_frontier_practices_prompt/synthesis_of_findings.md` (prioritized recommendations)
8. **Next step** -- `04_frontier_practices_prompt/frontier_research_prompt.md` (ready-to-use deep research prompt)

For targeted reference, the remaining documents can be read independently as needed.

---

## Document Index

### 01_sragent_codebase_analysis/ (6 files)

| File | Summary | Key Findings |
|------|---------|--------------|
| `full_codebase_overview.md` | Complete analysis of SRAgent v0.6.0: all 63 Python source files, 4-layer package architecture (cli/agents/tools/workflows/db), configuration via Dynaconf settings.yml, and all external integrations (NCBI, BigQuery, GCP, ChromaDB). | SRAgent has a clean 4-layer dependency graph. 20 named agent slots enable per-agent model/temperature/reasoning configuration. FlexTierChatOpenAI provides automatic flex-to-standard tier fallback. |
| `flow_diagrams.md` | ASCII flow diagrams for all 8 CLI subcommands, all 4 LangGraph workflow graphs, the ReAct agent loop, and the complete data flow from input to output. | The SRX-Info workflow is the most complex (convert -> fan-out to parallel metadata extraction -> aggregate). LangGraph `Send()` enables parallel processing. Hard limits prevent infinite loops (2 attempts in convert, 3 retries for structured output). |
| `prompt_and_context_management.md` | Complete catalog of all 18 agent system prompts, 7 workflow prompts, 10 Pydantic structured output models, 5 enum types, 4 prompt assembly patterns, and all truncation/context window management strategies. | Prompts are hardcoded Python strings (no templating engine). Context is managed via XML/JSON truncation (500-1000 chars), message windowing (last 4 messages), and per-agent max_tokens. Structured output agents are excluded from Claude thinking mode to ensure schema compliance. |
| `subagent_architecture.md` | Analysis of the 3-tier, 15-agent hierarchy: factory pattern, communication protocol, 5 work division patterns (supervisor-worker, sequential pipeline, router loop, fan-out/fan-in, workflow-wrapping-agent), concurrency controls, and full configuration matrix. | Maximum nesting depth is 4 levels. All agents follow the same factory signature. Only final results pass between agent levels, reducing token consumption. The configuration matrix shows 20 agent slots with specific model/temperature/reasoning/service_tier settings. |
| `reusable_patterns.md` | 16 design patterns extracted from the codebase with code examples: agent-as-tool factory, centralized model factory, flex tier fallback, structured output retry, LangGraph state machine, parallel fan-out, rate-limited batching, multi-source fallback, ontology resolution pipeline, regex-first with LLM fallback, web scraping, Dynaconf switching, Rich progress display, database upsert, credential rotation, graph visualization. | The agent-as-tool factory (Pattern 1) is the most broadly reusable. Regex-first with LLM fallback (Pattern 10) saves cost and improves reliability. The ontology resolution pipeline (Pattern 9) combines three complementary strategies (embedding, graph, API). |
| `code_organization_practices.md` | Quality assessment covering directory structure, naming conventions, separation of concerns, abstractions, code duplication, error handling, type annotations, documentation, anti-patterns, and testing. | 6 anti-patterns identified: settings loaded per model creation, quadratic agent instantiation, god prompt in sragent, mixed sync/async, typo in class name (`Acessions`), unused code. High duplication between tissue/disease ontology (350+ lines each, nearly identical). Testing covers deterministic helpers but not LLM-dependent behavior. |

### 02_paper_analysis/ (3 files)

| File | Summary | Key Findings |
|------|---------|--------------|
| `paper_summary_and_findings.md` | Structured summary of the scBaseCount paper (bioRxiv 2025.02.27.640494): problem statement, SRAgent + scRecounter approach, 5 key contributions, experimental setup, main results, ablation studies, and author-acknowledged limitations. | 502 million cells across 27 organisms. SRAgent processed 208,939 datasets at $17,000 ($0.08/dataset, 80s mean). AI models trained on scBaseCount outperform CZ CELLxGENE-trained models: +23.9% perturbation classification, +10.2% AUROC for DEG prediction. No formal ablation studies. |
| `methodology_deep_dive.md` | Step-by-step analysis of the agentic loop, LLM configuration (from both paper and codebase), all tools, all 4 evaluation approaches (metadata accuracy, silhouette scores, AI probing, marker genes), computational cost tables, and reproducibility assessment with 7 specific gaps. | The paper does not state which LLM was used for production runs. The implied token cost ($1.29/M tokens) suggests budget-tier models. LangSmith traces exist but are not shared. ChromaDB construction parameters are unspecified. Reproducibility is rated "partial." |
| `paper_critique.md` | Adversarial review structured as: 5 methodological gaps, 5 evaluation weaknesses, 5 unaddressed questions, 4 missing comparison categories, 5 reproducibility concerns, plus 7 acknowledged strengths and 3 most promising aspects. | The most critical gap: no quantitative metadata accuracy metrics (precision/recall/F1). The AI model comparison confounds dataset size with quality. No comparison to simpler baselines (regex, keyword matching, pysradb). The unspecified LLM model is the single biggest reproducibility concern. Balanced by genuine strengths in scale, open data/code, and architectural design. |

### 03_comparative_architecture/ (3 files)

| File | Summary | Key Findings |
|------|---------|--------------|
| `sragent_vs_harmonia_comparison.md` | Side-by-side comparison across 10 axes: overall architecture, agent orchestration, prompt management, context/memory, tool integration, error handling, configuration, code modularity, testing/evaluation, and documentation. Each axis has a "Key insight" summary. | SRAgent is a multi-agent production tool; Harmonia is a single-agent experimentation platform. SRAgent has better internal code organization; Harmonia has better modular boundaries at the system level. Harmonia's evaluation pipeline, experiment configuration, and documentation are significantly more sophisticated. SRAgent's agent orchestration and error handling are more granular. |
| `patterns_for_harmonia.md` | 8 transferable patterns from SRAgent to Harmonia, each with: SRAgent reference implementation, Harmonia gap analysis, implementation sketch with code, effort estimate, and risk assessment. 5 excluded patterns with rationale. Cross-pattern dependencies mapped. | Patterns ranked by impact: (1) Agent-as-tool factory for sub-agent composition, (2) Centralized model factory, (3) Structured output with retry, (4) Parallel fan-out, (5) Regex-first with LLM fallback, (6) Per-agent model config, (7) Rich progress display, (8) Graph visualization. Effort ranges from Small to Large. Patterns 1/4/6 are synergistic; Pattern 5 is prerequisite for Pattern 6. |
| `harmonia_strengths.md` | 8 genuine Harmonia strengths relative to SRAgent: experiment-first configuration, comprehensive evaluation pipeline, three-paradigm agent architecture, prompt version control, observability stack, container-based execution, kernel state budget management, versioned codebase documentation. Includes honest weakness assessment (5 items) and patterns worth preserving (8 items). | Harmonia's error categorization (whitespace-only, case-only, genuine) is a significant analytical contribution with no SRAgent equivalent. The three-paradigm support (ReAct + tools, ReAct + code, CodeAct) enables controlled experiments comparing structured tool use vs free-form code generation. The observability stack (tracing + dashboard + failure taxonomy + log analysis CLI) is far more developed. |

### 04_frontier_practices_prompt/ (4 files)

| File | Summary | Key Findings |
|------|---------|--------------|
| `best_practices_analysis.md` | Analysis of Claude Prompting Best Practices documentation mapped to SRAgent and Harmonia. Identifies practices already followed, practices not followed (gaps with severity ratings), and practices specifically relevant to deep research prompt design. | Highest-severity gaps for SRAgent: no hallucination guardrails. Highest-severity gaps for Harmonia: no few-shot examples, no self-check instructions, no anti-hallucination guidance, no sub-agent orchestration. Both systems lack XML tag structuring in prompts. Key prompt design techniques identified: adaptive thinking, structured research approach, self-correction chaining, grounding in quotes. |
| `yunque_deep_research_analysis.md` | Technical analysis of the Yunque DeepResearch framework (Cai et al., 2026): 4-module architecture, sub-goal-driven memory with dynamic folding, supervisor anomaly detection with 3-stage recovery, specialized sub-agents, and ablation evidence. Extracts 6 structural elements for deep research prompts and maps to Harmonia. | Key quantitative finding: removing structured memory causes -10.4 on BrowseComp; removing supervisor causes -8.7 on GAIA. Memory management and supervision are more impactful than specialized agents. Sub-goal-driven memory reduces context from O(t) rounds to O(n) sub-goals. 4 transferable insights for Harmonia identified: sub-goal context management, mid-execution anomaly detection, dynamic depth allocation, evidence chain tracking. |
| `synthesis_of_findings.md` | Cross-source synthesis combining all 12 prior documents plus 2 external sources. Identifies 4 architectural lessons, 5 critical paper gaps with implications, 11 transferable patterns ranked in 3 tiers, 5 frontier capability gaps, 10 open research questions, and improvement areas for both systems with a priority matrix. | Tier 1 (immediate, low risk): regex-first parsing, rich progress display, self-check prompts, few-shot examples. Tier 2 (significant, medium risk): structured output validation, sub-goal context compression, per-phase model settings, anomaly detection. Tier 3 (high value, high effort): multi-agent architecture, parallel fan-out, agent-as-tool factory. Five frontier gaps neither system addresses: confidence calibration, cross-run learning, adaptive error recovery, automated prompt optimization, dynamic context budget allocation. |
| `frontier_research_prompt.md` | Self-contained deep research prompt designed for frontier LLM execution. 10 research sub-goals (6 deep, 4 survey) covering orchestration, prompts, context, tools, calibration, cost, evaluation, safety, emerging patterns, and domain-specific improvements. Includes system context, quality criteria, good/bad examples, and output structure specification. | The prompt follows Claude Best Practices (XML structure, role, examples, self-check) and Yunque methodology (sub-goals, evidence chains, anomaly awareness, dynamic depth). Ready-to-use with recommended configuration (Claude Opus 4.6, adaptive thinking, high effort, 64K+ max tokens). |

### 05_meta/ (3 files)

| File | Summary | Key Findings |
|------|---------|--------------|
| `agent_execution_log.md` | Record of what each phase investigated, key decisions, obstacles encountered, scope/effort, and cross-references between outputs. | 5 phases produced 16 documents totaling approximately 5,900 lines. Each phase built on prior phases with increasing synthesis. Phase 1 was the heaviest by volume (6 documents, ~2,800 lines). |
| `quality_checklist.md` | Per-document quality assessment: completeness, specificity, actionability, cross-referencing, quality score (1-5), and improvement suggestions. | Overall mean quality: 4.94/5. All documents scored 5/5 except `best_practices_analysis.md` (4/5, gap severity ratings could be better justified). No documents contain platitudes or generic advice. Actionability increases across phases. |
| `README.md` | This file. Index of all outputs with summaries, key findings, and suggested reading order. | -- |
