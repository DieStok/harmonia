# SRAgent Patterns Transferable to Harmonia

**Date:** 31-03-2026 | **Analyst:** Comparative Architecture Analysis

---

## Pattern 1: Agent-as-Tool Factory for Sub-Agent Composition

### Description
A factory function creates an LLM agent that can be used standalone (for testing) or wrapped as a tool within a supervisor agent. This enables hierarchical delegation where a supervisor LLM decides which specialist to invoke and what instructions to give.

### How SRAgent Implements It
Every agent follows the same signature (`SRAgent/agents/esearch.py` lines 20-62):
```python
def create_esearch_agent(model_name=None, return_tool=True) -> Callable:
    model = set_model(model_name=model_name, agent_name="esearch")
    agent = create_react_agent(model=model, tools=[esearch], prompt=state_mod)
    if not return_tool:
        return agent  # For standalone CLI use
    @tool
    async def invoke_esearch_agent(message, config):
        result = await agent.ainvoke({"messages": [HumanMessage(content=message)]}, config)
        return {"messages": [AIMessage(content=result["messages"][-1].content, name="esearch_agent")]}
    return invoke_esearch_agent
```

The supervisor agent (e.g., `SRAgent/agents/entrez.py`) composes specialist agents as tools:
```python
tools = [create_esearch_agent(), create_esummary_agent(), create_efetch_agent(), create_elink_agent()]
agent = create_react_agent(model=model, tools=tools, prompt=supervisor_prompt)
```

### Why It Would Benefit Harmonia
Harmonia currently uses a single flat agent that must handle the entire harmonization workflow in one conversation. This leads to:

1. **Long, unfocused system prompts**: The `main.j2` system prompt must cover schema matching, value mapping, materialization, GDC knowledge, and interaction guidelines in a single prompt.
2. **No delegation**: If the agent makes a wrong schema match, it cannot delegate to a specialist that has deeper knowledge of GDC column semantics.
3. **Context window pressure**: A single conversation accumulates all intermediate state, requiring the `context_management/kernel_state_budget.py` and CodeAct summarization workarounds.

A sub-agent architecture could have, for example:
- A **Schema Expert** agent with focused GDC column knowledge and the `match_schema`/`rank_schema_matches` tools
- A **Value Mapping Expert** agent with `match_values` and `get_gdc_acceptable_values` tools
- A **Materialization Agent** with `materialize_mapping` and output validation
- A **Coordinator** that delegates to the above and synthesizes results

### Implementation Sketch for Harmonia
This would require moving away from the Beaker/Archytas single-agent model toward a multi-agent orchestration layer. Two approaches:

**Approach A: LangGraph orchestration outside Beaker** -- Build a LangGraph state machine (like SRAgent's `workflows/metadata.py`) that invokes the Beaker agent multiple times with focused prompts. The `ExperimentRunner` would be replaced by a LangGraph workflow where each node sends a targeted message to the Beaker agent, extracts structured results, and passes state to the next node. This preserves the existing Beaker infrastructure.

**Approach B: Multi-agent within Beaker** -- Create multiple Beaker contexts (e.g., `schema_context`, `value_context`) each with a focused agent, and build an orchestrator context that delegates. This is a deeper change but keeps everything inside the container.

### Effort Estimate
**Large.** Either approach requires significant refactoring of the experiment execution model. Approach A is more incremental (builds on existing `run_experiment.py`).

### Risk Assessment
- **High risk of over-engineering** for the current Dou 2020 benchmark (5 tools, 17 columns). Sub-agents add value primarily when the task space is large.
- **Beaker compatibility**: Approach B may conflict with how Beaker manages kernel state across contexts.
- **Evaluation pipeline**: Would need updating to handle multi-phase trace.json records.

---

## Pattern 2: Centralized Model Factory with Per-Agent Configuration

### Description
A single factory function creates LLM instances with a three-level configuration cascade: explicit parameter -> agent-specific setting -> default setting. Handles provider detection, reasoning effort, and fallback behavior.

### How SRAgent Implements It
`SRAgent/agents/utils.py:set_model()` (lines 162-315):
- Reads from `settings.yml` using Dynaconf with environment switching
- Each of 20 agent slots can have independent model, temperature, reasoning_effort, service_tier
- Automatic Claude vs OpenAI routing by model name prefix
- `FlexTierChatOpenAI` subclass for automatic flex-to-standard fallback on timeout

### Why It Would Benefit Harmonia
Harmonia currently has a **single LLM configuration per experiment** (`llm.provider` + `llm.model` in YAML). While `bdikit_models` in the config allows different models for BDI-Kit sub-operations (schema matching, value matching), the agent itself always uses one model.

Limitations this creates:
1. Cannot use a cheaper/faster model for simple steps (e.g., data loading, showing tables) and a more capable model for complex reasoning (e.g., correcting schema matches)
2. The `context_management.archytas.summarization_model` field exists but is marked "informational -- not in Archytas API" (`src/automation/config.py` line 107), indicating desire for this capability
3. Cannot mix providers within a single experiment (e.g., local Ollama for fast iteration + cloud model for final materialization)

### Implementation Sketch for Harmonia
Add a `model_factory.py` module to `src/`:
```python
def get_model(purpose: str, config: ExperimentConfig) -> str:
    """Resolve model string for a specific purpose.

    Cascade: purpose-specific override -> experiment default -> global default
    """
    purpose_models = config.llm.purpose_overrides or {}
    if purpose in purpose_models:
        return purpose_models[purpose]
    return config.llm.model
```

Extend the YAML config:
```yaml
llm:
  provider: openrouter
  model: anthropic/claude-sonnet-4.6
  purpose_overrides:
    summarization: openrouter/meta-llama/llama-3.1-8b
    schema_correction: anthropic/claude-sonnet-4.6
```

Wire into `CodeActAgentLoop._summarize_history()` and `BDIKitContext.__init__()`.

### Effort Estimate
**Small to medium.** The model factory itself is straightforward. The challenge is threading purpose-specific models through Archytas/Beaker, which has a single-model assumption. CodeAct mode (`litellm.acompletion()` calls) is easier to modify.

### Risk Assessment
- **Low risk.** This is additive -- the default behavior stays the same.
- **Provider key management**: Multiple providers may require multiple API keys in the `.env` file; `generate_env.py` would need updating.

---

## Pattern 3: Structured Output with Retry on Refusal

### Description
Use LLM structured output (Pydantic models) to extract typed data from agent responses, with progressive prompt softening on refusal and hard fallback to defaults.

### How SRAgent Implements It
`SRAgent/workflows/metadata.py` lines 286-321:
```python
for attempt in range(max_retries):
    try:
        response = await model.with_structured_output(AllMetadataEnum, strict=True).ainvoke(prompt)
        break
    except OpenAIRefusalError:
        prompt.append(HumanMessage(content="If you cannot determine certain fields, use 'unsure' or 'other'."))
        continue
    except Exception:
        extracted_fields = {field: "unsure" for field in fields}  # Safe defaults
```

11 Pydantic models enforce output structure across the codebase, including enum-constrained fields (`YesNo`, `Tech10XEnum`, `OrganismEnum`).

### Why It Would Benefit Harmonia
Harmonia currently has **no structured output extraction** from agent responses. The agent writes Python code to produce CSV files and JSON mappings, but:

1. **No validation of agent output format**: If the agent produces `column_mapping.json` with wrong structure, the evaluation pipeline discovers the error only at `calculate_all_metrics()` time
2. **No structured extraction of intermediate state**: The runner cannot programmatically inspect whether schema matching succeeded -- it pattern-matches on decision indicators (`runner.py` lines 369-381)
3. **Hallucinated outputs**: The failure taxonomy (`types_of_log_and_trace_problems.yaml`) includes "hallucinated output" as a known failure mode, suggesting the agent sometimes produces plausible-looking but incorrect artifacts

### Implementation Sketch for Harmonia
Add a post-turn validation step in `ExperimentRunner._run_turn_inner()`:

```python
# After receiving agent response
if self.config.output.save_artifacts:
    for artifact in self.config.output.save_artifacts:
        artifact_path = self.output_dir / artifact
        if artifact_path.exists():
            validator = get_artifact_validator(artifact)
            if validator:
                is_valid, errors = validator.validate(artifact_path)
                if not is_valid:
                    # Ask agent to fix
                    fix_msg = f"The file {artifact} has validation errors: {errors}. Please fix and re-save."
                    await self._send_with_retries(fix_msg, timeout=120.0)
```

For the column mapping specifically, define a Pydantic model:
```python
class ColumnMappingOutput(BaseModel):
    mapping: dict[str, str | None]  # source_col -> target_col or None
```

### Effort Estimate
**Medium.** The validation framework is new code. The main challenge is deciding *when* to validate (after which turn?) and how to communicate validation failures back to the agent without derailing the conversation.

### Risk Assessment
- **Medium risk.** Adding validation-and-retry loops to a conversational agent can create confusing interaction patterns. The agent may interpret validation feedback as a new task rather than a correction.
- **Benefit scales with experiment volume**: Most valuable when running 100+ experiments where manual inspection is infeasible.

---

## Pattern 4: Parallel Fan-Out via State Machine

### Description
Process a list of items in parallel through the same subgraph, with results accumulating into shared state.

### How SRAgent Implements It
`SRAgent/workflows/srx_info.py:continue_to_metadata()` (lines 81-134):
```python
from langgraph.types import Send

def continue_to_metadata(state, config):
    responses = []
    for SRX_accession in state["SRX"]:
        responses.append(Send("metadata_graph_node", {...}))
    return responses
```

State fields use `Annotated[List[str], operator.add]` to accumulate results from parallel nodes. Concurrency is controlled by `max_concurrency` in config and `asyncio.Semaphore` at the CLI level.

### Why It Would Benefit Harmonia
Harmonia currently processes experiments **sequentially** (one message at a time in `_run_experiment_loop`). For future datasets:

1. **Multi-table harmonization** (`two_metadata_tables_harmonize/`, `ten_metadata_tables_harmonize/`): Currently no support for parallel processing of multiple tables
2. **Per-column value matching**: Each column's value mapping is independent and could run in parallel
3. **Cross-model comparison**: Running the same experiment across multiple LLMs is done by launching separate SLURM jobs; a fan-out pattern could run multiple LLM variants within a single orchestration

### Implementation Sketch for Harmonia
For the multi-table use case, build a LangGraph workflow:
```python
class HarmonizationState(TypedDict):
    tables: list[str]  # Input table paths
    column_mappings: Annotated[list[dict], operator.add]  # Accumulated
    metrics: Annotated[list[dict], operator.add]

# Fan-out: one subgraph per table
def fan_out_tables(state):
    return [Send("harmonize_table", {"table": t}) for t in state["tables"]]
```

### Effort Estimate
**Large.** Requires building a LangGraph orchestration layer (see Pattern 1). The fan-out pattern is straightforward once the orchestration layer exists.

### Risk Assessment
- **Low technical risk** -- LangGraph's `Send()` is well-documented.
- **High integration risk** -- Requires moving from Beaker's single-session model to a multi-session or multi-message model.
- **Premature for current benchmark** -- The Dou 2020 dataset has one table. This pattern becomes valuable with the 10-table CPTAC dataset.

---

## Pattern 5: Regex-First with LLM Fallback

### Description
Extract structured data using fast deterministic regex, falling back to LLM structured output only when regex fails.

### How SRAgent Implements It
`SRAgent/workflows/convert.py:create_get_accessions_node()` (lines 60-122):
```python
# Try regex first (fast, deterministic)
accessions = extract_accessions(state["messages"][-1].content)
if accessions:
    return {"SRX": accessions}
# Fallback to LLM structured output
response = await model.with_structured_output(Acessions, strict=True).ainvoke(prompt)
```

### Why It Would Benefit Harmonia
Harmonia's `_is_decision_point()` in `runner.py` (lines 369-381) already uses regex to detect decision patterns. But there are more places where deterministic extraction could replace or augment LLM interpretation:

1. **Artifact detection**: After each turn, check if expected output files were created (currently done only at experiment end in `_resolve_required_artifacts()`)
2. **Error classification**: `_classify_retryable_error()` already does this for OpenRouter errors; extend to BDI-Kit tool errors
3. **Progress tracking**: Regex-extract which harmonization step the agent is on (schema matching, value mapping, materialization) from response content

### Implementation Sketch for Harmonia
Add a `response_parser.py` module to `src/automation/`:
```python
import re

STEP_PATTERNS = {
    "schema_matching": re.compile(r"match_schema|schema match|column mapping", re.I),
    "value_mapping": re.compile(r"match_values|value match|value mapping", re.I),
    "materialization": re.compile(r"materialize|harmonized table|final table", re.I),
}

def detect_current_step(response_content: str) -> str | None:
    for step, pattern in STEP_PATTERNS.items():
        if pattern.search(response_content):
            return step
    return None

def detect_produced_files(response_content: str) -> list[str]:
    return re.findall(r'(?:saved?|wrote?|created?)\s+(?:to\s+)?["\']?([^\s"\']+\.(?:csv|json))', response_content, re.I)
```

Wire into `TraceLogger.log_turn()` to add `detected_step` and `produced_files` fields to trace.json.

### Effort Estimate
**Small.** This is additive functionality with no risk to existing behavior.

### Risk Assessment
- **Very low risk.** Regex extraction is a read-only analysis layer. False positives are harmless (they only affect trace metadata, not experiment execution).

---

## Pattern 6: Per-Agent Model Configuration via Settings File

### Description
A centralized settings file maps agent names to model configurations, enabling fine-grained control over which model, temperature, and reasoning effort each agent uses.

### How SRAgent Implements It
`SRAgent/settings.yml` has 20 named agent slots:
```yaml
prod:
  models:
    default: gpt-5-mini
    sragent: gpt-5-mini
    esearch: gpt-5-mini
    metadata: gpt-5-mini
  temperature:
    default: 0.1
    get_entrez_ids: 0.0
  reasoning_effort:
    default: low
    sragent: medium
    tissue_ontology: medium
```

### Why It Would Benefit Harmonia
Currently, all Harmonia experiments use a single temperature and model. But different phases of the harmonization workflow have different characteristics:
- Schema matching requires **creative reasoning** (higher temperature might help explore alternatives)
- Value mapping requires **precision** (low temperature, high reasoning effort)
- Materialization requires **instruction following** (low temperature)
- Decision points require **conservative judgment** (low temperature)

### Implementation Sketch for Harmonia
Extend `ExperimentConfig` with phase-specific settings:
```yaml
llm:
  provider: openrouter
  model: anthropic/claude-sonnet-4.6
  temperature: 0.0
  phase_overrides:
    schema_matching:
      temperature: 0.2
    value_mapping:
      temperature: 0.0
    summarization:
      model: meta-llama/llama-3.1-8b-instruct
      temperature: 0.0
```

This requires the agent loop to know which phase it is in -- which connects to Pattern 5's step detection.

### Effort Estimate
**Medium.** Requires step detection (Pattern 5) plus dynamic model/temperature switching in the agent loop. Archytas does not natively support mid-conversation model changes, so this would be easier in CodeAct mode.

### Risk Assessment
- **Medium risk.** Switching models mid-conversation may disrupt the agent's internal state/style. Testing would be needed to ensure coherent behavior across model switches.

---

## Pattern 7: Rich Console Progress Display with Step Summaries

### Description
Show real-time streaming agent progress with spinners, per-step LLM-generated summaries, and formatted final output.

### How SRAgent Implements It
`SRAgent/agents/display.py` (lines 144-302):
- `create_agent_stream()` wraps `agent.astream()` with Rich progress bars
- Optional `step_summary_chain` uses a separate LLM call (max 45 tokens) to summarize each workflow step
- `display_final_results()` renders markdown-aware Rich panels

### Why It Would Benefit Harmonia
Harmonia's current progress display is minimal:
- `run_experiment.py:on_turn_complete()` prints a one-line status per turn (line 96-99)
- No real-time streaming of agent responses during automated experiments
- No per-step summaries -- the user must read `conversation.md` after the experiment

For long experiments (8+ turns, 30+ minutes), this makes it hard to diagnose issues in real-time.

### Implementation Sketch for Harmonia
Use `BeakerClient.send_message_stream()` (already implemented, line 422-447) to stream responses:
```python
from rich.console import Console
from rich.live import Live
from rich.panel import Panel

console = Console(stderr=True)
async for msg in client.send_message_stream(message):
    msg_type = msg.get("msg_type", "")
    if msg_type == "thought":
        console.print(f"  [dim]{msg['content'].get('thought', '')[:100]}[/dim]")
    elif msg_type == "llm_response":
        console.print(Panel(msg['content'].get('text', '')[:200]))
```

### Effort Estimate
**Small.** The streaming WebSocket interface already exists. This is primarily a display enhancement.

### Risk Assessment
- **Very low risk.** Display-only change. The `send_message_stream()` method is already implemented but unused in the automated runner.

---

## Pattern 8: Graph Visualization Export

### Description
Export workflow/agent graphs to visual formats (PNG, SVG, Mermaid) for documentation and debugging.

### How SRAgent Implements It
`SRAgent/workflows/graph_utils.py` (lines 1-109):
- `handle_write_graph_option()` detects compiled LangGraph objects
- `write_workflow_graph()` exports to PNG, SVG, PDF, or Mermaid format
- Available on every CLI subcommand via `--write-graph`

### Why It Would Benefit Harmonia
Harmonia has no visual representation of the experiment flow or agent interaction pattern. For debugging and documentation:
- The 8-turn automated experiment scripts define an implicit workflow that is not visualized
- The dashboard shows trace timelines but not the intended flow structure
- New team members must read YAML configs to understand experiment design

### Implementation Sketch for Harmonia
Add a `--visualize` flag to `manage_configs.py`:
```python
def visualize_experiment_flow(config: ExperimentConfig, output_path: str):
    """Generate a Mermaid diagram of the experiment message flow."""
    lines = ["graph TD"]
    for i, msg in enumerate(config.messages):
        label = msg.content[:50].replace('"', "'")
        lines.append(f'    T{i}["{label}..."]')
        if i > 0:
            lines.append(f"    T{i-1} --> T{i}")
        if msg.decision_mode:
            lines.append(f'    T{i} -->|decision: {msg.decision_mode}| T{i}')
    return "\n".join(lines)
```

### Effort Estimate
**Small.** This is a standalone utility with no dependencies on the core execution path.

### Risk Assessment
- **Very low risk.** Documentation-only feature.

---

## Completeness Assessment

This document identifies 8 transferable patterns from the SRAgent Phase 1 analysis. Patterns are ordered by potential impact, from highest (sub-agent composition) to lowest (graph visualization). Each pattern includes:
- Specific SRAgent code references (file, lines, code snippets)
- Specific Harmonia limitations it addresses (with file references)
- Concrete implementation sketch
- Effort estimate (2 small, 3 medium, 3 large -- though the 3 large patterns are interconnected)
- Risk assessment

**Patterns considered but excluded:**
- **Entrez API rate-limited batching** (Pattern 7 in SRAgent): Not applicable -- Harmonia does not call NCBI APIs
- **Ontology resolution pipeline** (Pattern 9): Not applicable -- Harmonia uses BDI-Kit for ontology-like mapping
- **Database upsert with schema introspection** (Pattern 14): Harmonia uses file-based storage; a database layer is not currently needed
- **Credential rotation** (Pattern 15): Not applicable -- Harmonia uses single API keys per provider
- **Dynaconf environment switching** (Pattern 12): Harmonia's per-experiment YAML approach is already more flexible than environments

**Cross-pattern dependencies:**
- Patterns 1, 4, and 6 are synergistic (sub-agent composition + fan-out + per-agent config)
- Pattern 5 is a prerequisite for Pattern 6 (phase-specific config requires step detection)
- Pattern 3 is independently valuable and lowest risk
