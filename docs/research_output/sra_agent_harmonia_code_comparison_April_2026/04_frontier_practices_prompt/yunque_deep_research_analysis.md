# Yunque Deep Research Analysis: Methodology for Deep Research with AI Agents

**Date:** 01-04-2026 | **Source:** Yunque DeepResearch Technical Report (Cai et al., Tencent BAC, arXiv:2601.19578v1, January 2026)

---

## 1. Core Methodology

Yunque DeepResearch is a hierarchical, modular multi-agent framework for autonomous deep research. It achieves state-of-the-art on GAIA (78.6), BrowseComp (62.5), BrowseComp-ZH (75.9), and Humanity's Last Exam (51.7), consistently outperforming both open-source frameworks (DeepAgent, AgentFold, MiroFlow) and closed-source systems (OpenAI Deep Research, Gemini Deep Research).

### 1.1 Architecture: Four Collaborative Modules

1. **Main Agent**: Central executive for intent recognition, dynamic planning, global orchestration, and result synthesis. Uses interleaved reasoning -- interprets feedback from each step to dynamically refine subsequent plans. Employs adaptive routing that synergizes lightweight tools with specialized sub-agents based on evolving context.

2. **Context Manager**: Dual-level memory structure balancing immediate operational precision with long-term strategic context. The core innovation: sub-goal-driven memory that partitions trajectories into semantic units rather than linear history.

3. **Atomic Capability Pool**: Hierarchical system with two layers:
   - Specialized sub-agents (Browser-Use GUI Agent, Data Analysis Agent)
   - Basic tools (search, read, code execution, visual grounding)

4. **Supervisor**: Active anomaly detection and self-correction mechanism. Monitors trajectory for failure signals, triggers preemptive interrupts, and executes a three-stage recovery protocol (diagnosis, pruning, re-generation).

### 1.2 Key Design Principles

- **Decoupled architecture**: Separate strategic planning from action execution
- **Adaptive routing**: Dynamically choose between direct tool invocation and sub-agent delegation based on task complexity
- **Structured memory over linear history**: Compress completed sub-goals into semantic summaries while retaining fine-grained traces for the active sub-goal
- **Proactive anomaly detection**: Continuous trajectory monitoring rather than rigid reflection schedules

---

## 2. Structured Memory Generation

This is the most transferable technical contribution for deep research prompt design.

### 2.1 Memory Unit Structure

Each memory unit is a 4-tuple: `m_i = (R_i, g_i, T_i, s_i)` where:
- `R_i`: List of global round indices contributing to the sub-goal
- `g_i`: Semantic description of the current sub-goal (short-term guidance)
- `T_i`: Persistent tool-use log (tool names, parameters, execution results)
- `s_i`: Incremental summary of key information extracted during execution

The complete memory list `M = [m_1, m_2, ..., m_n]` represents a macro-level planning pathway.

### 2.2 Dynamic Folding and Adding Mechanism

An end-to-end memory model `F_mem` processes each interaction round to produce:
- A binary indicator `delta_fold` (does the current round belong to the same sub-goal?)
- An updated memory unit `m_out`

When `delta_fold = 1` (same sub-goal): update the last memory unit in-place.
When `delta_fold = 0` (new sub-goal): append a new memory unit.

This compresses multi-round interactions into intentional units, reducing context redundancy while preserving decision-making history.

### 2.3 Dynamic Context Management

The context `C_t` is constructed adaptively:
- **Within a sub-goal** (`|R_n| > 1`): Append incremental ReAct traces to existing context (fine-grained)
- **At sub-goal boundary** (`|R_n| = 1`): Compression reset -- replace all historical round-by-round traces with serialized folded memory of completed sub-goals

This shifts context complexity from O(t) total rounds to O(n) sub-goals.

---

## 3. Supervisor Module: Adaptive Interrupt and Self-Correction

### 3.1 Problem Addressed

In long-horizon tasks, agents suffer from "cognitive inertia" -- persisting in invalid behaviors despite failures. Symptoms: syntactic errors (malformed tool calls), semantic stagnation (repetitive outputs, recursive loops).

### 3.2 Three-Stage Recovery Protocol

1. **Anomaly Diagnosis**: Agent critically analyzes execution history to pinpoint root cause of failure
2. **Trajectory Pruning**: System explicitly prunes recent invalid interaction traces from the context window to prevent "memory pollution"
3. **Re-generation**: Agent synthesizes an alternative output (revised plan or corrected conclusion), breaking the local loop

### 3.3 Ablation Evidence

Removing the Supervisor causes the sharpest performance drops on GAIA (-8.7) and BrowseComp-ZH (-10.5). The paper attributes this to the module's role in preventing "error accumulation" -- ensuring subsequent attempts are not biased by previous failures.

---

## 4. Specialized Sub-Agents

### 4.1 Browser-Use GUI Agent

Modeled as a POMDP (Partially Observable Markov Decision Process):
- Observation `o_t = (c_t, b_t, x_t)`: textual context + browser state + screenshot
- Screenshots are ephemeral (not serialized into history) -- prevents context explosion
- One tool per turn constraint: decompose complex interaction into atomic decisions
- PDF paging mechanism: read long documents incrementally rather than injecting full text

### 4.2 Data Analysis Agent

Two-phase workflow:
1. **Data Profiling**: Route files to appropriate parsers, produce standardized context (metadata + schema + preview)
2. **Multi-step Reasoning and Self-refinement**: Iterative loop of code generation -> execution in sandbox -> feedback observation -> self-correction until objective met

---

## 5. Structural Elements of Effective Deep Research Prompts

Extracted from the Yunque methodology and its case studies:

### 5.1 Hierarchical Task Decomposition

Research prompts should decompose into:
- **Top-level research question** (the "user intent")
- **Sub-goals** (independently pursuable research threads)
- **Atomic operations** (individual searches, reads, analyses)

The prompt should make this hierarchy explicit rather than relying on the LLM to discover it.

### 5.2 Sub-Goal-Driven Organization

Structure the expected output around sub-goals, not around a flat list of topics. Each sub-goal should have:
- A clear semantic description (what are we trying to find out?)
- Expected tool/source strategy (where should we look?)
- Success criteria (how do we know we have enough?)
- Summary structure (what format should the findings take?)

### 5.3 Dynamic Depth Allocation

Not all sub-goals deserve equal depth. The prompt should specify:
- **Core areas** requiring deep investigation (2-3 competing approaches, evidence synthesis)
- **Survey areas** requiring breadth (landscape mapping, taxonomy)
- **Gap areas** where the prompt acknowledges uncertainty and requests exploratory treatment

### 5.4 Evidence Chain Requirements

Each finding should trace back to sources:
- Tool/method used to discover it
- Specific source (paper, codebase, API documentation)
- Confidence level
- Corroboration status (single source vs. multi-source confirmed)

### 5.5 Anomaly Awareness

The prompt should instruct the researcher to:
- Monitor for contradictory evidence
- Flag when sources disagree
- Explicitly note when a research thread is not yielding results (rather than fabricating)
- Prune dead-end investigations and redirect effort

### 5.6 Structured Memory Checkpoints

For long research tasks, the prompt should require:
- Periodic state summaries (what has been found so far, per sub-goal)
- Explicit tracking of open questions
- A "hypothesis tree" or equivalent that evolves as evidence accumulates

---

## 6. Techniques for Managing Scope, Thoroughness, and Quality

### 6.1 Scope Management

From Yunque's adaptive routing principle:
- **Light tasks**: Direct tool invocation (search, read) -- do not over-elaborate
- **Complex tasks**: Delegate to specialized sub-agent or multi-step reasoning
- **The prompt should explicitly define what is in-scope and what is not**

### 6.2 Ensuring Thoroughness

From Yunque's memory mechanism:
- Every sub-goal must have a summary before moving on
- The summary must capture tool-use strategy (what was tried), not just findings
- Incomplete sub-goals should be explicitly flagged, not silently dropped

From the ablation study:
- Memory removal caused the sharpest drops on browsing tasks (-10.4 BrowseComp), confirming that structured history management is critical for thoroughness in information-dense tasks

### 6.3 Quality Assurance

From the Supervisor module:
- **Self-correction is not optional** -- the research prompt should require a review pass
- **Trajectory pruning**: If a research thread produces contradictory or low-quality results, explicitly discard it and note why
- **Anomaly detection signals**: Repetitive findings across sources (indicating search saturation), contradictory evidence, inability to find corroboration

---

## 7. Relevance to Harmonia and Scientific Metadata Agents

### 7.1 Direct Parallels

| Yunque Concept | Harmonia Equivalent | Gap |
|---------------|--------------------|----|
| Main Agent orchestration | ExperimentRunner scripted messages | Harmonia's runner has no adaptive routing; messages are fixed |
| Dynamic Context Management | Kernel state budget + CodeAct summarize/truncate | Harmonia manages *data* context but not *reasoning* context structurally |
| Atomic Capability Pool | BDI-Kit tools (match_schema, match_values, etc.) | Harmonia has 5 domain tools but no specialized sub-agents |
| Supervisor anomaly detection | Failure taxonomy + retry_policy | Harmonia detects failures post-hoc; Yunque detects mid-execution |
| Memory units with sub-goal structure | trace.json per-turn records | trace.json records turns but does not organize them into sub-goal units |

### 7.2 Transferable Insights

1. **Sub-goal-driven context management** could replace Harmonia's linear turn-by-turn context accumulation. Schema matching, value mapping, and materialization are natural sub-goals; completed sub-goals should be compressed into structured summaries.

2. **Anomaly detection during execution** could enable mid-conversation recovery. Currently, Harmonia's runner can only retry entire turns; a supervisor pattern could detect when the agent is stuck in a loop (e.g., repeatedly calling `match_schema` with the same parameters) and intervene.

3. **Dynamic depth allocation** is relevant to Harmonia's multi-table future: some tables may need deep investigation (complex schema, many value mismatches) while others may be straightforward. The orchestration layer should allocate agent effort accordingly.

4. **Evidence chain tracking** aligns with Harmonia's evaluation needs: if each harmonization decision recorded which tools were consulted and what evidence was found, the evaluation pipeline could diagnose *why* errors occur, not just *that* they occur.

---

## 8. Quantitative Evidence from Yunque

| Component Removed | BrowseComp Impact | BrowseComp-ZH Impact | GAIA Impact | HLE Impact |
|-------------------|-------------------|---------------------|-------------|------------|
| Memory | -10.4 | -7.4 | -0.9 | 0.0 |
| Supervisor | -4.4 | -10.5 | -8.7 | -1.2 |
| Browser-Use GUI Agent | -0.8 | -- | -6.8 | -- |
| Data Analysis Agent | -- | -- | -2.9 | 0.0 |

Key takeaway: **Memory management and supervision are more impactful than specialized agents** on browsing-heavy and reasoning-heavy tasks. For a deep research prompt, this suggests investing more effort in structured context management and self-correction than in tool sophistication.

---

## Completeness Assessment

This analysis covers all 6 sections of the Yunque paper (Introduction, Related Work, Framework, Experiments, Limitations, Conclusion) plus the case study appendix. The four core modules are analyzed with their mechanisms and ablation evidence. Six structural elements for deep research prompts are extracted and three scope/quality techniques identified. The mapping to Harmonia identifies 5 direct parallels and 4 transferable insights. Not covered: the POMDP formalism details of the Browser-Use GUI Agent (Section 3.3.1) beyond the architectural overview, and the full experimental comparison tables (Tables 1-3 are summarized but not reproduced in full). The paper's limitations section acknowledges no systematic token consumption or latency analysis, which is relevant context for cost-performance considerations in Document 3.
