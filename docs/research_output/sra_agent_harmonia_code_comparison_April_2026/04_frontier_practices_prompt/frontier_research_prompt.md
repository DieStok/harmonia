# Frontier Research Prompt: Advanced Practices for Scientific Metadata Extraction Agents

**Date:** 01-04-2026 | **Version:** 1.0

---

## How to Use This Prompt

This is a self-contained deep research prompt designed to be submitted to a frontier LLM (Claude Opus 4.6 recommended) with web search and document retrieval capabilities. Copy the entire content below the line into a new conversation. The prompt follows Claude Best Practices (XML structuring, clear role, examples, self-check, structured output) and Yunque Deep Research methodology (hierarchical sub-goals, dynamic depth allocation, evidence chains, anomaly awareness).

**Recommended configuration:**
- Model: Claude Opus 4.6 (or equivalent frontier model)
- Thinking: `{type: "adaptive"}`
- Effort: `high`
- Max tokens: 64,000+
- Tools: Web search, document retrieval

---

## THE PROMPT

<system>
You are a frontier AI systems researcher specializing in agentic architectures for scientific data processing. You have deep expertise in LLM agent orchestration, prompt engineering, context window optimization, and evaluation methodology for autonomous systems operating on biomedical data.

Your task is to conduct deep research on frontier practices that can improve scientific metadata extraction and harmonization agents. You will produce a comprehensive, evidence-based research report structured around specific sub-goals.
</system>

<context>
<context_description>
The following context describes two real systems that motivate this research. Use this context to ground your findings in concrete architectural decisions rather than abstract principles.
</context_description>

<system_a name="SRAgent">
SRAgent is a multi-agent LLM pipeline for extracting metadata from the NCBI Sequence Read Archive. Architecture: 3-tier agent hierarchy (supervisor -> specialist -> tool) built with LangGraph. 15 ReAct agents, each with independent model/temperature/reasoning_effort settings. Uses agents-as-tools pattern where sub-agents are wrapped as LangChain @tool functions. Structured output via 11 Pydantic models with enum constraints. Context management via XML/JSON truncation and message history windowing (last 4 messages). Error handling: structured output retry on OpenAIRefusalError with progressive prompt softening, flex-tier fallback, multi-source cascades. Processed 208,939 datasets at $17,000 total cost ($0.08/dataset, 80 seconds mean). Limitations: no quantitative evaluation metrics reported, no hallucination detection, no confidence calibration, no cross-run learning.
</system_a>

<system_b name="Harmonia">
Harmonia is a single-agent metadata harmonization platform using Beaker (Jupyter-protocol kernel) with either Archytas ReAct or custom CodeAct agent loops. 5 BDI-Kit tools for schema matching, value mapping, and materialization. Three agent paradigms (ReAct + domain tools, ReAct + run_code, true CodeAct). Jinja2 prompt templates with per-experiment overrides. Kernel state budget enforcement limits Python variable serialization. Context management: CodeAct summarize/truncate strategies. Comprehensive evaluation pipeline: Pydantic MetricsResult schema with precision/recall/F1/hallucination rate/error categorization (whitespace-only, case-only, genuine). Dashboard for cross-experiment comparison. Failure taxonomy with 16 error classes. Container-based execution on HPC with SLURM. Limitations: flat single-agent architecture, no sub-agent delegation, no structured output validation during execution, no mid-conversation anomaly detection.
</system_b>

<known_gaps>
From prior analysis, the following gaps have been identified as highest priority:
1. Neither system produces calibrated confidence estimates for its outputs
2. Neither system learns from past runs to improve future performance
3. Context window management is the binding constraint in both architectures
4. Error recovery is coarse (retry entire turns or structured extraction) rather than root-cause-targeted
5. No system has been ablated to determine the minimum effective agent architecture for the task
6. The cost-performance Pareto frontier for agent complexity is unmapped
7. Hallucination detection and prevention in metadata extraction is ad-hoc
8. No automated feedback loop from evaluation metrics to prompt/architecture improvement
</known_gaps>
</context>

<research_instructions>

## Research Methodology

Conduct this research following these principles:

1. **Sub-goal-driven investigation**: The research areas below are organized as sub-goals. For each sub-goal, pursue it to completion before moving on. When you complete a sub-goal, produce a structured summary before starting the next.

2. **Evidence-based findings**: Every recommendation must cite at least one specific source (paper, codebase, documentation, benchmark result). Do not make claims based solely on general knowledge. If you cannot find evidence for a claim, say so explicitly and label it as a hypothesis.

3. **Competing approaches**: For each research area, identify at least 2 competing approaches or frameworks. Evaluate the evidence for each before recommending one.

4. **Confidence tracking**: For each finding, assign a confidence level:
   - **High**: Multiple corroborating sources, empirical evidence, or formal analysis
   - **Medium**: Single strong source or logical extrapolation from established principles
   - **Low**: Plausible but based on limited or indirect evidence
   - **Speculative**: Hypothesis without direct evidence

5. **Anomaly awareness**: If you encounter contradictory evidence, flag it explicitly. If a research thread is not yielding useful results, say so and redirect rather than fabricating.

6. **Self-check**: Before finalizing each section, verify: (a) claims cite specific evidence, (b) recommendations are actionable for the specific systems described above, (c) gaps are explicitly acknowledged.

## Research Sub-Goals

### Sub-Goal 1: Advanced Agent Orchestration Patterns (2024-2026)

<research_area id="1" depth="deep">
<question>What are the most effective multi-agent orchestration patterns for scientific data processing tasks, and how should orchestration complexity scale with task complexity?</question>

<specific_questions>
- What orchestration patterns have emerged beyond the basic supervisor-worker model? Search for: hierarchical planning, dynamic task graphs, agent markets, blackboard architectures.
- What evidence exists for the optimal number of agents in a multi-agent system? Is there a complexity threshold below which a single agent outperforms multi-agent?
- How do LangGraph, CrewAI, AutoGen, and other frameworks compare for scientific data processing orchestration?
- What patterns exist for graceful degradation when sub-agents fail?
</specific_questions>

<grounding>SRAgent uses a 3-tier supervisor-worker hierarchy with LangGraph. Harmonia uses a flat single-agent model. The Yunque DeepResearch framework (2026) uses a Main Agent + Atomic Capability Pool + Supervisor + Context Manager architecture that outperforms both single-agent and simpler multi-agent systems on GAIA, BrowseComp, and HLE benchmarks.</grounding>
</research_area>

### Sub-Goal 2: State-of-the-Art Prompt Engineering for Multi-Step Workflows

<research_area id="2" depth="deep">
<question>What prompt engineering techniques yield the largest improvements for multi-step scientific data processing agents, and how should prompts be structured for maximum reliability?</question>

<specific_questions>
- What is the current evidence on few-shot vs. zero-shot prompting for tool-using agents?
- How should system prompts be structured for agents that must maintain state across 10+ tool calls?
- What techniques prevent prompt drift (gradual deviation from instructions) in long conversations?
- How effective are chain-of-thought, tree-of-thought, and graph-of-thought for structured data extraction?
- What role do negative examples ("do NOT do X") play vs. positive examples in agent prompts?
</specific_questions>

<grounding>SRAgent uses static string prompts with procedural few-shot examples (workflow descriptions, not input/output pairs). Harmonia uses Jinja2 templates with per-experiment overrides but no few-shot examples. Claude Best Practices recommend 3-5 diverse examples wrapped in XML tags, and advise "prefer general instructions over prescriptive steps" for thinking-enabled models.</grounding>
</research_area>

### Sub-Goal 3: Context Window Optimization and Long-Horizon Memory

<research_area id="3" depth="deep">
<question>What are the most effective strategies for managing context windows in long-running agent sessions, particularly for tasks involving structured scientific data?</question>

<specific_questions>
- What is the state of the art in context compression for agent trajectories? Search for: MemAgent, AgentFold, MeM1, Memory-as-Action, ReSum.
- How does Yunque's sub-goal-driven memory compare to simpler truncation/summarization approaches?
- What are effective strategies for managing large structured data (dataframes, schema definitions) within context windows?
- How do RAG-based approaches compare to in-context approaches for providing domain knowledge to agents?
- What is the empirical relationship between context utilization and task performance in agent systems?
</specific_questions>

<grounding>Harmonia's kernel state budget limits Python variable serialization (max 20,000 chars/variable, 25% of context for state). SRAgent decomposes context across agents. Yunque's memory shifts context from O(t) total rounds to O(n) sub-goals, with ablation showing -10.4 on BrowseComp when memory is removed.</grounding>
</research_area>

### Sub-Goal 4: Tool Use Optimization

<research_area id="4" depth="survey">
<question>How should tools be designed, described, and orchestrated for maximum agent effectiveness in data processing tasks?</question>

<specific_questions>
- What is the evidence on optimal tool granularity (fine-grained atomic tools vs. coarse multi-step tools)?
- How should tool descriptions be written for best LLM comprehension? Search for recent benchmarks.
- What patterns exist for tool result summarization (full results vs. summarized results)?
- How does CodeAct (LLM writes code) compare to structured tool calling for data manipulation tasks?
- What is the current state of the art in tool selection and planning for multi-tool environments?
</specific_questions>

<grounding>SRAgent uses 12+ fine-grained tools (individual Entrez API wrappers). Harmonia offers 5 coarse domain tools plus CodeAct mode where the LLM writes arbitrary Python. Yunque uses an "Atomic Capability Pool" with specialized sub-agents for complex tasks and basic tools for simple operations.</grounding>
</research_area>

### Sub-Goal 5: Agent Self-Evaluation and Calibration

<research_area id="5" depth="deep">
<question>How can agents produce calibrated confidence estimates for their outputs, and how should self-evaluation be structured to catch errors before they propagate?</question>

<specific_questions>
- What methods exist for LLM confidence calibration in structured extraction tasks?
- How effective is agent self-critique (generate -> review -> refine) compared to external validation?
- What patterns exist for detecting hallucination in structured output (ontology terms, schema mappings)?
- How should verification be structured: per-step validation, checkpoint validation, or final validation?
- What is the evidence on using a separate "critic" model vs. self-critique with the same model?
</specific_questions>

<grounding>Neither SRAgent nor Harmonia produces calibrated confidence. SRAgent uses enum constraints and "unsure" defaults. Harmonia detects hallucinated output post-hoc via evaluation metrics. The paper critique identified cascading error propagation (tissue misclassification -> cell type misclassification) as an unanalyzed risk.</grounding>
</research_area>

### Sub-Goal 6: Cost-Performance Optimization

<research_area id="6" depth="survey">
<question>What strategies optimize the cost-performance tradeoff in agentic systems, and where are the diminishing returns?</question>

<specific_questions>
- What is the evidence on using different-capability models for different sub-tasks within a pipeline?
- How do routing/cascade approaches (try cheap model first, escalate to expensive model on failure) perform?
- What is the cost impact of context management strategies (compression saves input tokens)?
- What caching strategies are effective for recurring patterns in metadata extraction?
- How does the cost-accuracy curve vary across model families for structured data extraction?
</specific_questions>

<grounding>SRAgent processed 208,939 datasets at $17,000 total (~$1.29/M tokens, suggesting budget-tier models). Per-agent model selection in settings.yml enables cost optimization. Harmonia's model registry tracks pricing per model. Neither system implements caching of recurring patterns.</grounding>
</research_area>

### Sub-Goal 7: Evaluation Methodologies for Agentic Systems

<research_area id="7" depth="deep">
<question>What evaluation methodologies are most appropriate for agentic scientific metadata extraction systems, and what metrics are missing from current approaches?</question>

<specific_questions>
- What benchmarks exist for evaluating metadata extraction agents? Search for: schema matching benchmarks, ontology alignment evaluation, data harmonization benchmarks.
- How should agent trajectories (not just final outputs) be evaluated?
- What metrics capture the reliability/consistency of agent behavior across runs?
- How should evaluation handle legitimate ambiguity (multiple correct answers)?
- What is the state of the art in automated error analysis for agent systems?
</specific_questions>

<grounding>Harmonia has a comprehensive MetricsResult schema (precision, recall, F1, hallucination rate, omission rate, error categorization: whitespace-only/case-only/genuine, confusion matrices). SRAgent paper reports only qualitative heatmaps. Harmonia's failure taxonomy has 16 error classes across 5 categories. The paper critique identified the need for held-out evaluation sets and baseline comparisons.</grounding>
</research_area>

### Sub-Goal 8: Safety and Reliability Patterns

<research_area id="8" depth="survey">
<question>What safety and reliability patterns are most critical for autonomous scientific data processing agents?</question>

<specific_questions>
- What guardrails prevent agents from producing plausible but incorrect scientific metadata?
- How should agents handle genuinely ambiguous inputs (metadata that could map to multiple ontology terms)?
- What patterns exist for audit trails in agent decision-making?
- How do systems ensure that agent errors do not silently contaminate downstream analyses?
- What is the state of the art in anomaly detection for agent behavior?
</specific_questions>

<grounding>Yunque's Supervisor module performs active anomaly detection with a three-stage recovery protocol (diagnosis, trajectory pruning, re-generation). Removing it causes -8.7 on GAIA. SRAgent catches OpenAIRefusalError and uses multi-source fallback. Harmonia has retry_policy per error code and a failure taxonomy but no mid-execution detection.</grounding>
</research_area>

### Sub-Goal 9: Emerging Patterns from 2024-2026 Research

<research_area id="9" depth="survey">
<question>What new agent architecture patterns have emerged in 2024-2026 that are relevant to scientific data processing?</question>

<specific_questions>
- What patterns have emerged from Claude Code, Cursor, Devin, and other code agents that transfer to data processing?
- How have DSPy, TextGrad, and automated prompt optimization evolved for agentic systems?
- What new frameworks or papers address the specific problem of LLM agents operating on structured scientific data?
- What lessons have emerged from the scaling of agent systems to production (thousands of runs)?
- How has the agent reliability landscape changed with Claude 4.5/4.6, GPT-5, and Gemini 3 Pro?
</specific_questions>

<grounding>The Yunque paper (January 2026) represents current SOTA on agentic benchmarks. Claude 4.6 Best Practices introduce adaptive thinking, native subagent orchestration, and context awareness as new capabilities. The field is moving rapidly and patterns from early 2024 may already be superseded.</grounding>
</research_area>

### Sub-Goal 10: Specific Improvements for Scientific Metadata Extraction Agents

<research_area id="10" depth="deep">
<question>What specific techniques would most improve the accuracy, reliability, and efficiency of agents that extract and harmonize biomedical metadata?</question>

<specific_questions>
- How should agents leverage biomedical ontologies (UBERON, MONDO, GDC schema) -- as in-context knowledge, RAG, or tool-accessible databases?
- What is the evidence on LLM performance for schema matching and value mapping compared to traditional approaches (e.g., similarity flooding, embedding-based matching)?
- How should agents handle the long tail of rare metadata values (uncommon tissues, unusual perturbation types)?
- What strategies improve agent performance on tabular data understanding (column semantics, value distributions)?
- How can evaluation metrics from completed runs feed back into prompt/architecture improvements automatically?
</specific_questions>

<grounding>SRAgent uses ChromaDB vector search + OBO graph traversal + OLS API for ontology resolution (a 3-method pipeline). Harmonia uses BDI-Kit's schema matching algorithms. Neither system has been compared to traditional non-LLM schema matching baselines. The paper critique identifies the absence of this comparison as a critical gap.</grounding>
</research_area>

</research_instructions>

<output_structure>

## Required Output Structure

Produce your research report with the following structure:

```
# Frontier Practices for Scientific Metadata Extraction Agents
## Research Report

### Executive Summary
- 5-7 bullet points of the most important findings
- Top 3 actionable recommendations

### Sub-Goal 1: [Title]
#### Landscape
[2-3 paragraph overview of the current state]
#### Competing Approaches
[At least 2 approaches with evidence for/against]
#### Key Findings
[Numbered list with confidence levels]
#### Recommendations for SRAgent-Like Systems
[Specific, actionable]
#### Recommendations for Harmonia-Like Systems
[Specific, actionable]
#### Sources
[Numbered list of sources cited in this section]

[Repeat for Sub-Goals 2-10]

### Cross-Cutting Themes
[Patterns that appear across multiple sub-goals]

### Research Gaps and Future Directions
[What remains unknown and where should effort be directed]

### Methodology Notes
[How the research was conducted, what sources were consulted, what could not be found]
```

</output_structure>

<quality_criteria>

## Quality Criteria

Your report will be evaluated against these criteria:

1. **Evidence density**: Each section must cite at least 3 specific sources (papers, frameworks, benchmarks, documentation). Generic claims without citations fail this criterion.

2. **Actionability**: Each recommendation must be specific enough that an engineer could begin implementation. "Use better prompts" fails; "Add 3-5 few-shot examples showing correct and incorrect schema matches wrapped in XML example tags, following the pattern in Claude Best Practices Section 2" passes.

3. **Grounding in context**: Recommendations must reference the specific architectural constraints of the two systems described above. Generic advice that ignores whether the system uses Beaker/LangGraph/etc. fails.

4. **Competing viewpoints**: Each research area must present at least one counterargument or alternative approach. One-sided analysis fails.

5. **Confidence calibration**: Findings labeled "High confidence" must have multiple corroborating sources. Findings labeled "Speculative" are acceptable and encouraged when clearly marked.

6. **Recency**: Prioritize 2024-2026 sources. Flag when findings are based on older work that may be superseded.

7. **Thoroughness per sub-goal**: "Deep" research areas (1, 2, 3, 5, 7, 10) must have at least 500 words per section. "Survey" areas (4, 6, 8, 9) must have at least 300 words.

8. **Honesty about gaps**: If a research area yields limited results, state this explicitly rather than padding with generic content. "We found limited published evidence on X" is a valid and valuable finding.

</quality_criteria>

<examples>

## Example: Good vs. Bad Research Finding

<example type="good">
**Finding**: Sub-goal-driven memory management reduces context window pressure more effectively than uniform summarization for long-horizon agent tasks.

**Evidence**: Yunque DeepResearch (Cai et al., 2026) ablation shows removing structured memory causes -10.4 on BrowseComp (browsing-heavy, long-horizon) but only -0.9 on GAIA (mixed, shorter-horizon), confirming the benefit scales with task length. AgentFold (2025) reports similar findings with adaptive compression granularity. In contrast, ReSum's uniform summarization loses critical details at compression boundaries.

**Confidence**: High (ablation evidence from two independent systems).

**Recommendation for Harmonia**: Implement sub-goal boundaries at the schema matching -> value mapping -> materialization transitions. When transitioning to value mapping, compress the schema matching conversation into a structured summary (columns mapped, confidence per mapping, tools used) rather than carrying the full conversation forward. This can be implemented in CodeActAgentLoop._summarize_history() by detecting phase transitions via regex (Pattern 5 from SRAgent analysis) and generating structured summaries instead of uniform truncation.
</example>

<example type="bad">
**Finding**: Multi-agent systems are better than single-agent systems.

**Evidence**: Many researchers have found that multi-agent systems improve performance.

**Recommendation**: Use multi-agent architecture.
</example>

The good example cites specific sources with quantitative evidence, assigns a confidence level, acknowledges where the benefit is largest, and provides an implementation-specific recommendation referencing the target system's actual code structure. The bad example is vague, uncited, and unactionable.

</examples>

---

BEGIN YOUR RESEARCH. Start with Sub-Goal 1 and proceed sequentially. Produce a structured summary after completing each sub-goal before moving to the next.

---

## Completeness Assessment

This prompt covers all 10 requested frontier topics with specific research questions grounded in the SRAgent/Harmonia context. It follows Claude Best Practices: clear role (system tag), XML structure throughout, diverse examples (good/bad), explicit quality criteria, self-check instructions, long context at top with query at bottom. It follows Yunque methodology: sub-goal organization, evidence chain requirements, anomaly awareness ("if a research thread is not yielding results, say so"), dynamic depth allocation (6 "deep" + 4 "survey" areas), structured output specification.

Design decisions:
- **10 sub-goals** with explicit depth tags (deep vs. survey) to manage scope while ensuring thoroughness
- **Specific questions per sub-goal** prevent the researcher from producing generic overviews
- **Grounding sections** tie each research area to the concrete systems being improved
- **Quality criteria are quantitative** where possible (word counts, citation counts, competing viewpoints)
- **Good/bad examples** demonstrate the expected level of specificity and evidence
- **Output structure is fully specified** with section headers and content expectations
- **Self-contained**: The prompt includes sufficient context about both systems that no external documents are needed
