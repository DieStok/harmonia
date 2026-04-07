# SRAgent: Sub-Agent Architecture

## 1. Agent Hierarchy

SRAgent has a 3-tier agent hierarchy:

```
Tier 1: Supervisor Agents (orchestrate Tier 2)
  +-- SRAgent agent
  +-- Entrez agent
  +-- Entrez Convert agent
  +-- Papers agent

Tier 2: Specialist Agents (each wraps 1-3 tools)
  +-- esearch agent
  +-- esummary agent
  +-- efetch agent
  +-- elink agent
  +-- ncbi_fetch agent
  +-- bigquery agent (also has Tier 1 role: wraps entrez_convert)
  +-- sequences agent
  +-- tissue_ontology agent
  +-- disease_ontology agent
  +-- find_datasets agent

Tier 3: Tools (deterministic functions)
  +-- esearch, esummary, efetch, elink (Entrez API)
  +-- which_entrez_databases
  +-- fetch_ncbi_record, fetch_geo_record, fetch_pubmed_record, etc.
  +-- get_study_metadata, get_experiment_metadata, etc. (BigQuery)
  +-- sra_stat, fastq_dump (CLI wrappers)
  +-- query_vector_db, get_neighbors, query_uberon_ols / query_mondo_ols
  +-- download_paper_by_doi
```

### Nesting relationships:

```
SRAgent agent
  +-- Entrez agent (as tool)
  |    +-- esearch agent (as tool)
  |    |    +-- esearch (tool)
  |    +-- esummary agent (as tool)
  |    |    +-- esummary, which_entrez_databases (tools)
  |    +-- efetch agent (as tool)
  |    |    +-- efetch, which_entrez_databases (tools)
  |    +-- elink agent (as tool)
  |         +-- elink, which_entrez_databases (tools)
  +-- ncbi_fetch agent (as tool)
  |    +-- fetch_geo_record, fetch_ncbi_record, fetch_pubmed_record,
  |         fetch_biosample_record, fetch_bioproject_record (tools)
  +-- bigquery agent (as tool)
  |    +-- get_study_experiment_run, get_study_metadata,
  |    |    get_experiment_metadata, get_run_metadata (tools)
  |    +-- entrez_convert agent (as tool)
  |         +-- esearch agent, esummary agent, elink agent (as tools)
  |         +-- fetch_geo_record, fetch_ncbi_record (tools)
  +-- sequences agent (as tool)
       +-- sra_stat, fastq_dump (tools)
```

Maximum nesting depth: **4 levels** (SRAgent -> BigQuery -> entrez_convert -> esearch -> esearch tool)

## 2. Agent Definition Pattern

Every agent follows the same factory pattern defined in the agents/ directory:

```python
def create_<name>_agent(
    model_name: Optional[str] = None,
    return_tool: bool = True,
) -> Callable:
    # 1. Create LLM model
    model = set_model(model_name=model_name, agent_name="<name>")

    # 2. Define tools (other agents-as-tools + deterministic tools)
    tools = [create_sub_agent(), tool_function, ...]

    # 3. Define system prompt
    state_mod = "\n".join([...])

    # 4. Create ReAct agent
    agent = create_react_agent(
        model=model,
        tools=tools,
        prompt=state_mod,
        response_format=OptionalPydanticModel,  # for structured output
    )

    # 5. Return bare agent or wrap as tool
    if not return_tool:
        return agent

    @tool
    async def invoke_<name>_agent(
        message: Annotated[str, "Message to the agent"],
        config: RunnableConfig = None,
    ) -> Annotated[dict, "Response from the agent"]:
        """Docstring describing what the agent does."""
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]}, config=config
        )
        return {
            "messages": [
                AIMessage(content=result["messages"][-1].content, name="<name>_agent")
            ]
        }

    return invoke_<name>_agent
```

### Key design decisions:
- `return_tool=True` (default): Returns a LangChain `@tool` wrapper. Used when the agent is a sub-agent of a supervisor.
- `return_tool=False`: Returns the raw LangGraph ReAct agent. Used when invoking directly from CLI.
- All tool wrappers are **async** (`async def`)
- All tools return `{"messages": [AIMessage(...)]}` with a `name` attribute for attribution

## 3. Agent Instantiation

Agents are instantiated at graph/workflow creation time (not per-request):

```python
# In supervisor agent creation:
tools = [
    create_esearch_agent(),     # returns @tool-wrapped agent
    create_esummary_agent(),    # returns @tool-wrapped agent
    create_efetch_agent(),      # returns @tool-wrapped agent
    create_elink_agent(),       # returns @tool-wrapped agent
]
agent = create_react_agent(model=model, tools=tools, prompt=state_mod)
```

This means:
- Sub-agent LLM models are initialized once at startup
- Sub-agent prompts are fixed at creation time
- The agent graph topology is static

### Exception: Metadata workflow
In `workflows/metadata.py`, `create_sragent_agent()` is called **inside** `invoke_SRX2SRR_sragent_agent_node()` (line 409), meaning a new SRAgent instance is created per SRX-to-SRR conversion. This appears to be a design choice for isolation.

## 4. Communication Protocol

### Message-based communication
All inter-agent communication uses LangChain message objects:

```python
# Supervisor sends to sub-agent:
result = await agent.ainvoke(
    {"messages": [HumanMessage(content=message)]}, config=config
)

# Sub-agent returns:
return {
    "messages": [
        AIMessage(content=result["messages"][-1].content, name="<agent>_agent")
    ]
}
```

### Information packaging:
- **Input**: Free-text string describing what the sub-agent should do
- **Output**: Free-text string with the sub-agent's findings
- **Attribution**: `name` field on AIMessage identifies which agent produced the response
- **No structured data passing** between agents (except via workflow state)

### Config propagation
`RunnableConfig` is passed through the chain for:
- `max_concurrency`: Controls parallel execution
- `recursion_limit`: Prevents infinite agent loops
- `configurable`: Custom parameters (organisms, use_database, etc.)
- BigQuery `client` object

## 5. Work Division Patterns

### Pattern A: Supervisor with Specialist Workers
Used by: `entrez`, `sragent`, `entrez_convert`, `papers`

The supervisor LLM decides which worker to call and what instructions to give:
```
Supervisor receives task
  -> Decides which specialist to invoke
  -> Formulates instructions for specialist
  -> Specialist executes and returns results
  -> Supervisor analyzes results, decides next action
  -> Repeat until task complete
```

### Pattern B: Sequential Pipeline
Used by: `metadata` workflow

Fixed sequence of nodes with no LLM routing:
```
sragent_agent -> get_metadata -> tissue_ontology -> SRX2SRR -> add2db -> final_state
```

### Pattern C: Pipeline with Router Loop
Used by: `convert` workflow

```
convert_agent -> get_accessions -> router
                                    |
                                    +-- CONTINUE -> convert_agent (loop)
                                    +-- STOP -> END
```

### Pattern D: Fan-Out/Fan-In
Used by: `srx_info` and `find_datasets` workflows

```
Single node produces list -> Send() for each item -> parallel subgraph execution -> aggregate
```

Implementation uses `langgraph.types.Send()`:
```python
def continue_to_metadata(state, config):
    responses = []
    for SRX_accession in SRX_filt:
        input = {"entrez_id": ..., "SRX": SRX_accession, ...}
        responses.append(Send("metadata_graph_node", input))
    return responses
```

### Pattern E: Workflow Wrapping Agent as Tool
Used by: `tissue_ontology_workflow`, `disease_ontology_workflow`

A supervisor ReAct agent wraps a specialist ReAct agent as a tool, with structured output:
```
Workflow (ReAct agent with UBERON_IDS response_format)
  -> For each tissue: invoke tissue_ontology_agent (ReAct with UBERON_ID response_format)
```

## 6. Result Aggregation

### State accumulation via operator.add
```python
class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]  # messages accumulate
    SRX: Annotated[List[str], operator.add]                   # lists concatenate
```
When parallel nodes write to the same field, values are concatenated.

### Final state filtering
`workflows/srx_info.py:final_state()` and `workflows/find_datasets.py:final_state()` filter accumulated messages to only those starting with `"# SRX accession: "`:
```python
messages = [x for x in state["messages"] if x.startswith("# SRX accession: ")]
```

### Metadata graph result packaging
`workflows/metadata.py:final_state()` combines all metadata fields into a formatted report:
```python
message = "\n".join([
    "# SRX accession: " + state["SRX"],
    " - SRR accessions: " + fmt(state["SRR"]),
] + [f" - {v}: {state[k]}" for k, v in metadata_items.items()])
```

## 7. Concurrency Control

### At workflow level
- `asyncio.Semaphore` in CLI handlers limits parallel entrez_id processing
- `--max-parallel` CLI argument (default 2-3)
- `--max-concurrency` limits LangGraph internal concurrency (default 3-6)

### At tool level
- Entrez API: `time.sleep(0.34)` between requests (3 req/sec limit)
- Random email/API key rotation via `set_entrez_access()` distributes across credentials
- HTTP retry with exponential backoff

### At NCBI async level
- `workflows/utils.py`: `asyncio.Semaphore(max_concurrent=5)` for async NCBI fetches
- 8 retries with exponential backoff + jitter

## 8. Agent Configuration Matrix

| Agent Name | Model (prod) | Temperature | Reasoning | Service Tier | Structured Output |
|------------|-------------|-------------|-----------|-------------|-------------------|
| esearch | gpt-5-mini | 0.1 | low | flex | No |
| esummary | gpt-5-mini | 0.1 | low | flex | No |
| efetch | gpt-5-mini | 0.1 | low | flex | No |
| elink | gpt-5-mini | 0.1 | low | flex | No |
| sequences | gpt-5-mini | 0.1 | low | flex | No |
| ncbi_fetch | gpt-5-mini | 0.1 | low | flex | No |
| bigquery | gpt-5-mini | 0.1 | low | flex | No |
| entrez | gpt-5-mini | 0.1 | low | flex | No |
| sragent | gpt-5-mini | 0.1 | medium | flex | No |
| tissue_ontology | gpt-5-mini | 0.1 | medium | flex | UBERON_ID |
| disease_ontology | gpt-5-mini | 0.1 | medium | flex | MONDO_ID |
| metadata | gpt-5-mini | 0.1 | medium | default | AllMetadataEnum |
| metadata_router | gpt-5-mini | 0.1 | medium | flex | (via metadata graph) |
| convert_router | gpt-5-mini | 0.1 | low | flex | Choice |
| accessions | gpt-5-mini | 0.1 | low | flex | Acessions |
| entrez_convert | gpt-5-mini | 0.1 | low | flex | No |
| find_datasets | gpt-5-mini | 0.1 | low | flex | No |
| get_entrez_ids | gpt-5-mini | 0.0 | low | flex | EntrezInfo |
| step_summary | gpt-5-mini | 0.1 | "" | flex | No |
| papers | gpt-5-mini | 0.1 | (default) | (default) | PublicationsResult |

Notable: `get_entrez_ids` uses temperature=0.0 for deterministic extraction. `step_summary` disables reasoning ("").

## Completeness Assessment

This document covers all 15 agents, their hierarchical relationships, the factory creation pattern, all 5 work division patterns (supervisor-worker, sequential pipeline, router loop, fan-out/fan-in, workflow-wrapping-agent), all communication mechanisms, result aggregation strategies, concurrency controls, and the full configuration matrix for all 20 agent slots. The only agents not individually profiled are the `papers` sub-agent composition (which reuses esearch/esummary/efetch/elink) and the Claude-specific configuration variants.
