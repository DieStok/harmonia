# Best Practices Analysis: Claude Prompting for Agentic Scientific Metadata Systems

**Date:** 01-04-2026 | **Source:** Claude Prompting Best Practices (Anthropic official documentation, current for Claude 4.6)

---

## 1. Key Principles Extracted

### 1.1 Clarity and Directness

The documentation's golden rule: "Show your prompt to a colleague with minimal context on the task and ask them to follow it. If they'd be confused, Claude will be too."

Core techniques:
- Be specific about desired output format and constraints
- Provide instructions as sequential steps using numbered lists when order matters
- Frame instructions with modifiers that encourage quality ("Go beyond the basics to create a fully-featured implementation")
- Explain the *why* behind instructions -- Claude generalizes from motivation

### 1.2 Structured Prompts with XML Tags

XML tags reduce misinterpretation when prompts mix instructions, context, examples, and variable inputs:
- Use consistent, descriptive tag names
- Nest tags when content has natural hierarchy
- Wrap examples in `<example>` / `<examples>` tags

### 1.3 Few-Shot Examples

3-5 well-crafted examples dramatically improve accuracy and consistency. Examples should be:
- **Relevant**: Mirror actual use case
- **Diverse**: Cover edge cases
- **Structured**: Wrapped in `<example>` tags to distinguish from instructions

### 1.4 Long Context Prompting

For 20K+ token inputs:
- **Put longform data at the top**, query/instructions at the bottom (up to 30% improvement)
- **Structure documents with XML tags** including metadata and content subtags
- **Ground responses in quotes** -- ask Claude to extract relevant quotes before answering

### 1.5 Role Assignment

A single role-setting sentence in the system prompt focuses behavior and tone. SRAgent uses this extensively ("helpful senior bioinformatician"); Harmonia uses it in Jinja2 templates.

### 1.6 Adaptive Thinking

Claude 4.6 uses adaptive thinking (`thinking: {type: "adaptive"}`) which dynamically decides when and how much to think. Key guidance:
- "Prefer general instructions over prescriptive steps" -- "think thoroughly" often produces better reasoning than hand-written step-by-step plans
- Multishot examples work with thinking -- use `<thinking>` tags in few-shot examples
- Ask Claude to self-check before finishing

### 1.7 Agentic System Patterns

**Long-horizon reasoning:**
- Claude 4.6 excels at state tracking across extended sessions
- For multi-context-window workflows: use first window for setup (tests, scripts), then iterate on a todo-list
- Structure state data in JSON/structured formats; use freeform text for progress notes
- Use git for state tracking across sessions

**Subagent orchestration:**
- Claude 4.6 naturally recognizes when tasks benefit from subagent delegation
- Watch for *overuse* -- the model may spawn subagents when direct approaches suffice
- Guide with: "Use subagents when tasks can run in parallel, require isolated context, or involve independent workstreams"

**Research and information gathering:**
- Provide clear success criteria
- Encourage source verification across multiple sources
- Use structured approach: develop competing hypotheses, track confidence levels, self-critique, update hypothesis tree

**Self-correction chaining:**
- Generate draft -> review against criteria -> refine based on review
- Each step as separate API call for logging and branching

### 1.8 Anti-Patterns to Avoid

- **Overeagerness**: Claude 4.6 tends to overengineer. Add: "Avoid over-engineering. Only make changes that are directly requested."
- **Test-focused hard-coding**: "Write a high-quality, general-purpose solution... Do not hard-code values"
- **Hallucination in agentic coding**: "Never speculate about code you have not opened... investigate before answering"
- **Excessive parallel tool calling**: Can bottleneck system performance; steer with explicit guidance

---

## 2. Practices Already Followed

### 2.1 In SRAgent

| Practice | How SRAgent Follows It | Quality |
|----------|----------------------|---------|
| Role assignment | Every agent has "expert in bioinformatics" or "helpful senior bioinformatician" role | Good |
| Step-by-step instructions | Agent prompts describe specific workflows with numbered steps | Good |
| Structured output | 11 Pydantic models with enum constraints enforce output format | Excellent |
| Subagent orchestration | 3-tier hierarchy with supervisor-worker pattern | Excellent |
| Retry with progressive softening | OpenAIRefusalError handling adds permissive instructions | Good |
| Reasoning effort per agent | Per-agent reasoning_effort in settings.yml (low/medium/high) | Good |

### 2.2 In Harmonia

| Practice | How Harmonia Follows It | Quality |
|----------|------------------------|---------|
| Role assignment | System prompt in main.j2 defines agent role | Good |
| Structured prompts | Jinja2 templates with clear sections | Good |
| Context management | Kernel state budget, CodeAct summarize/truncate | Good |
| Long-horizon state tracking | trace.json and conversation.md persist state | Good |
| Multi-context workflows | Experiment configs with scripted message sequences | Partial |

---

## 3. Practices NOT Followed (Gaps)

### 3.1 In SRAgent

| Missing Practice | Impact | Severity |
|-----------------|--------|----------|
| **XML tag structuring** | Prompts use plain `\n`.join() strings without structural tags. Claude would parse tool descriptions and workflow steps more reliably with `<instructions>`, `<tools>`, `<examples>` tags | Medium |
| **Few-shot examples with input/output pairs** | SRAgent has procedural examples (which tools to call) but no input/output pair examples showing expected behavior | Medium |
| **Long data at top, query at bottom** | Not systematically applied -- message history and queries are interleaved | Low (mitigated by short contexts per agent) |
| **Self-check instructions** | No agent prompt asks the LLM to verify its answer before returning | Medium |
| **Thinking tag examples** | No `<thinking>` tags in few-shot examples to demonstrate reasoning patterns | Low |
| **Anti-overengineering guidance** | The sragent supervisor prompt is 50+ lines and could trigger over-exploration. No explicit scoping instructions | Medium |
| **Hallucination guardrails** | No "investigate before answering" or grounding instructions in any agent prompt | High |

### 3.2 In Harmonia

| Missing Practice | Impact | Severity |
|-----------------|--------|----------|
| **Few-shot examples** | No examples of good/bad harmonization steps in the system prompt. The agent must infer correct behavior purely from instructions | High |
| **XML tag structuring** | Jinja2 templates use markdown formatting, not XML structural tags | Medium |
| **Self-check instructions** | No instruction to verify output against gold standard schema before completing | High |
| **Structured research approach** | No "develop competing hypotheses" pattern for schema matching decisions | Medium |
| **Explicit success criteria** | The system prompt does not define what "successful harmonization" looks like quantitatively | Medium |
| **Anti-hallucination guidance** | No explicit "investigate before answering" for metadata fields | High |
| **Subagent orchestration** | Single flat agent with no delegation capability | High (architectural) |
| **Context awareness prompting** | No instruction about context window limits or when to save progress | Medium |

---

## 4. Practices Specifically Relevant to Deep Research Prompts

### 4.1 Structured Research Approach

The documentation's research prompt pattern is directly applicable to generating a frontier practices research prompt:
```
Search for this information in a structured way. As you gather data, develop several
competing hypotheses. Track your confidence levels in your progress notes to improve
calibration. Regularly self-critique your approach and plan. Update a hypothesis tree
or research notes file to persist information and provide transparency.
```

This maps to a deep research prompt that:
- Defines explicit research questions (not just topics)
- Requires competing hypotheses for each question
- Demands confidence calibration
- Structures output with evidence chains

### 4.2 Self-Correction Chaining

For multi-step research: generate draft -> review against criteria -> refine. This can be built into the prompt structure itself by requiring:
1. Initial findings per topic
2. Self-critique against quality criteria
3. Revised findings incorporating critique

### 4.3 Grounding in Quotes

For long-context research prompts that include multiple source documents: "Find quotes from [documents] that are relevant to [question]. Place these in `<quotes>` tags. Then, based on these quotes, [synthesize]."

### 4.4 Adaptive Thinking Guidance

For the research prompt: prefer general instructions ("think thoroughly about X") over prescriptive reasoning steps. Claude's internal reasoning frequently exceeds what a human would prescribe.

### 4.5 Multi-Window Workflow Design

The deep research prompt should be designed for potential multi-window execution:
- First window: establish research framework, write quality criteria
- Subsequent windows: iterate on findings per topic
- Progress tracked in structured format (JSON state file)

---

## 5. Mapping to Frontier Research Prompt Design

| Best Practice | How It Applies to the Research Prompt |
|--------------|--------------------------------------|
| Clear role | "You are a frontier AI systems researcher specializing in agentic architectures for scientific data processing" |
| XML structure | Wrap each research area in `<research_area>` tags; wrap context docs in `<document>` tags |
| Few-shot examples | Include an example of good vs bad research output for one topic |
| Success criteria | Define quantitative quality criteria (depth, evidence count, actionability) |
| Self-check | "Before finalizing each section, verify: (a) claims cite specific evidence, (b) recommendations are actionable, (c) gaps are explicitly acknowledged" |
| Long data at top | Place all prior analysis documents at the top of the prompt, research questions at the bottom |
| Adaptive thinking | Use `thinking: {type: "adaptive"}` with high effort for the research task |
| Structured research | "For each research area, develop 2-3 competing approaches, evaluate evidence for each, and select the best-supported one" |

---

## Completeness Assessment

This analysis covers all major sections of the Claude Prompting Best Practices document: General Principles (5 subsections), Output and Formatting (6 subsections), Tool Use (2 subsections), Thinking and Reasoning (2 subsections), Agentic Systems (8 subsections), Capability-Specific Tips (2 subsections), and Migration Considerations (4 subsections). Each principle is mapped to both SRAgent and Harmonia current practice with a gap assessment. The 8 practices identified as specifically relevant to deep research prompts form the design basis for the frontier research prompt (Document 4). Not covered: frontend design tips and LaTeX formatting guidance (irrelevant to the task).
