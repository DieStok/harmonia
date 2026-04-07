# SRAgent: Reusable Design Patterns

## Pattern 1: Agent-as-Tool Factory

**Purpose**: Create an LLM agent that can be used standalone or composed as a tool within a supervisor agent.

**Where used**: All 15 agent files in `agents/`

**Code example** (from `agents/esearch.py`, lines 20-62):

```python
def create_esearch_agent(model_name: str = None) -> Callable:
    # 1. Create model with per-agent config
    model = set_model(model_name=model_name, agent_name="esearch")

    # 2. Create ReAct agent with tools and prompt
    agent = create_react_agent(
        model=model,
        tools=[esearch],
        prompt="...",
    )

    # 3. Wrap as @tool for composability
    @tool
    async def invoke_esearch_agent(
        message: Annotated[str, "Message to the esearch agent"],
        config: RunnableConfig
    ) -> Annotated[str, "Response from the esearch agent"]:
        """Invoke the esearch agent to perform a task."""
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]}, config=config
        )
        return {
            "messages": [
                AIMessage(content=result["messages"][-1].content, name="esearch_agent")
            ]
        }

    return invoke_esearch_agent
```

**Key properties**:
- Dual-mode return (tool wrapper or bare agent via `return_tool` parameter)
- Per-agent model configuration via `set_model(agent_name=...)`
- Named AIMessage output for attribution
- Config passthrough for concurrency control

---

## Pattern 2: Centralized Model Factory with Per-Agent Config

**Purpose**: Create LLM instances with settings resolved from a hierarchical config, with automatic provider detection and fallback.

**Where used**: `agents/utils.py:set_model()` (lines 162-315)

**Code example** (abbreviated):

```python
def set_model(model_name=None, temperature=None, reasoning_effort=None,
              agent_name="default", max_tokens=None, service_tier=None):
    settings = load_settings()  # Dynaconf with env switching

    # Cascade: explicit param -> agent-specific setting -> default setting
    if model_name is None:
        try:
            model_name = settings["models"][agent_name]
        except KeyError:
            model_name = settings["models"]["default"]

    # Provider detection by model name prefix
    if model_name.startswith("claude"):
        # Handle thinking tokens for reasoning effort
        model = ChatAnthropic(model=model_name, thinking=thinking, ...)
    elif re.search(r"(^o[0-9]|^gpt-5)", model_name):
        # Use FlexTierChatOpenAI for automatic fallback
        model = FlexTierChatOpenAI(model_name=model_name, reasoning_effort=reasoning_effort, ...)
    elif model_name.startswith("gpt-4"):
        model = FlexTierChatOpenAI(model_name=model_name, temperature=temperature, ...)

    return model
```

**Key properties**:
- Three-level config cascade (explicit -> per-agent -> default)
- Automatic Claude vs OpenAI routing by model name prefix
- Thinking token budget management for Claude
- Reasoning effort for o-series/GPT-5
- Flex tier timeout fallback wrapper

---

## Pattern 3: Flex Tier Automatic Fallback

**Purpose**: Transparently retry on cheaper "flex" service tier, falling back to standard tier on timeout.

**Where used**: `agents/utils.py:FlexTierChatOpenAI` (lines 137-159)

```python
class FlexTierChatOpenAI(ChatOpenAI):
    def __init__(self, *args, service_tier=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._service_tier = service_tier
        if service_tier == "flex":
            fallback_kwargs = kwargs.copy()
            fallback_kwargs.pop("service_tier", None)
            self._fallback_model = ChatOpenAI(**fallback_kwargs)

    @async_retry_on_flex_timeout
    async def ainvoke(self, *args, **kwargs):
        return await super().ainvoke(*args, **kwargs)
```

The decorator `async_retry_on_flex_timeout` (lines 37-84) catches `TimeoutError` and `APITimeoutError`, then retries with the pre-created fallback model.

---

## Pattern 4: Structured Output with Retry on Refusal

**Purpose**: Extract structured data from LLM responses, with graceful degradation when the model refuses.

**Where used**: `workflows/metadata.py` (lines 286-321), `workflows/convert.py` (lines 99-120), `workflows/find_datasets.py` (lines 100-125)

```python
max_retries = 3
for attempt in range(max_retries):
    try:
        response = await model.with_structured_output(
            AllMetadataEnum, strict=True
        ).ainvoke(prompt)
        extracted_fields = get_extracted_fields(response)
        break
    except Exception as e:
        if "OpenAIRefusalError" in str(type(e).__name__) and attempt < max_retries - 1:
            # Append permissive instruction
            prompt.append(HumanMessage(
                content="If you cannot determine certain fields, use 'unsure' or 'other'."
            ))
            continue
        else:
            # Fall back to safe defaults
            extracted_fields = {
                "is_illumina": "unsure",
                "is_single_cell": "unsure",
                ...
            }
```

**Key properties**:
- Uses `with_structured_output(Model, strict=True)` for schema enforcement
- Catches `OpenAIRefusalError` specifically
- Progressive prompt softening on retry
- Hard fallback to defaults on final failure

---

## Pattern 5: LangGraph State Machine with TypedDict

**Purpose**: Define multi-step workflows as state machines with typed, accumulating state.

**Where used**: All files in `workflows/`

```python
class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]  # accumulate
    entrez_id: Annotated[str, "Entrez ID"]                    # overwrite
    SRX: Annotated[List[str], operator.add]                    # accumulate

workflow = StateGraph(GraphState)
workflow.add_node("node_a", node_a_func)
workflow.add_node("node_b", node_b_func)
workflow.add_edge(START, "node_a")
workflow.add_edge("node_a", "node_b")
workflow.add_edge("node_b", END)
graph = workflow.compile()
```

**Key properties**:
- `Annotated[..., operator.add]` makes fields accumulate across parallel nodes
- Simple `Annotated[str, "desc"]` fields are overwritten
- Conditional edges via functions returning node names or `Send()` objects
- Subgraphs can be embedded as nodes

---

## Pattern 6: Parallel Fan-Out via Send()

**Purpose**: Process a list of items in parallel through the same subgraph.

**Where used**: `workflows/srx_info.py:continue_to_metadata()` (lines 81-134), `workflows/find_datasets.py:continue_to_srx_info()` (lines 162-176)

```python
from langgraph.types import Send

def continue_to_metadata(state: GraphState, config: RunnableConfig):
    responses = []
    for SRX_accession in state["SRX"]:
        input = {
            "database": state["database"],
            "entrez_id": state["entrez_id"],
            "SRX": SRX_accession,
            "messages": [HumanMessage(prompt.format(SRX_accession=SRX_accession))],
        }
        responses.append(Send("metadata_graph_node", input))
    return responses

# In graph definition:
workflow.add_conditional_edges(
    "convert_graph_node", continue_to_metadata, ["metadata_graph_node"]
)
```

**Key properties**:
- Each `Send()` creates an independent subgraph execution
- Results accumulate into shared state via `operator.add`
- Concurrency controlled by `max_concurrency` in config

---

## Pattern 7: Entrez API Rate-Limited Batching

**Purpose**: Batch Entrez API calls respecting NCBI rate limits with retry.

**Where used**: `tools/esearch.py`, `tools/esummary.py`, `tools/efetch.py`, `tools/elink.py`

```python
from SRAgent.tools.utils import batch_ids, set_entrez_access

set_entrez_access()  # Random credential rotation
batch_size = 200
records = []

for id_batch in batch_ids(entrez_ids, batch_size):
    time.sleep(0.34)  # 3 req/sec limit
    id_str = ",".join(id_batch)
    handle = None
    try:
        handle = Entrez.esummary(db=database, id=id_str, retmode="xml")
        batch_record = handle.read()
    except Exception as e:
        batch_record = f"Error: {e}"
    finally:
        if handle is not None:
            try:
                handle.close()
            except:
                pass
    # Process: decode -> truncate -> xml2json -> append
    batch_record = truncate_values(batch_record, max_length=500)
    batch_record = xml2json(batch_record)
    records.append(batch_record)
```

**Key properties**:
- `batch_ids()` generator yields chunks of configurable size
- `set_entrez_access()` randomly selects from numbered EMAIL/API_KEY env vars
- 0.34s sleep for rate limiting
- Handle cleanup in `finally` block
- XML -> truncated XML -> JSON conversion pipeline

---

## Pattern 8: Multi-Source Fallback Download

**Purpose**: Try multiple sources sequentially until one succeeds.

**Where used**: `tools/papers.py:download_paper_by_doi()` (lines 274-442)

```python
errors = []

# 1. Try preprint server
if is_preprint:
    result = _download_from_preprint_server(doi, output_path)
    if result["success"]:
        return f"Successfully downloaded from {result['source']}"
    errors.append(f"Preprint server: {result['message']}")

# 2. Try CORE
core_info = _get_core_info(doi, api_key)
if core_info and core_info.get("download_url"):
    # download...
    return "Successfully downloaded from CORE"
errors.append("CORE: ...")

# 3. Try Europe PMC
# 4. Try Unpaywall
# ...

# All failed
error_summary = "\n".join([f"  - {err}" for err in errors])
return f"ERROR: Failed to download {doi} from all sources:\n{error_summary}"
```

**Key properties**:
- Sequential cascade (not parallel)
- Each source has its own API client/logic
- Error messages accumulated for diagnostic reporting
- Cloudflare bypass via `cloudscraper` for bioRxiv/medRxiv

---

## Pattern 9: Ontology Resolution Pipeline

**Purpose**: Map free-text descriptions to ontology IDs using vector search + graph traversal + API lookup.

**Where used**: `tools/tissue_ontology.py`, `tools/disease_ontology.py`

```
1. query_vector_db(query)
   -> ChromaDB semantic search using OpenAI embeddings
   -> Returns top-k ontology terms with descriptions
   -> Auto-downloads ChromaDB tarball from GCS if missing

2. get_neighbors(ontology_id)
   -> Load OBO file (obonet library, cached via @lru_cache)
   -> NetworkX graph traversal (predecessors + successors)
   -> Returns adjacent terms with names and definitions

3. query_<ontology>_ols(search_term)
   -> EBI Ontology Lookup Service REST API
   -> Returns matching terms with descriptions and synonyms
```

**Key properties**:
- Three complementary resolution strategies (embedding, graph, API)
- Lazy download and caching of ontology data
- `@lru_cache(maxsize=1)` for ontology graph (expensive to load)
- `appdirs.user_cache_dir("SRAgent")` for platform-appropriate caching

---

## Pattern 10: Regex-First with LLM Fallback

**Purpose**: Extract structured data using fast regex, falling back to LLM only when regex fails.

**Where used**: `workflows/convert.py:create_get_accessions_node()` (lines 60-122)

```python
def create_get_accessions_node():
    model = set_model(agent_name="accessions")

    async def invoke_get_accessions_node(state):
        # Try regex first (fast, deterministic)
        accessions = extract_accessions(state["messages"][-1].content)
        if accessions:
            return {"SRX": accessions}

        # Fallback to LLM structured output (slower, flexible)
        response = await model.with_structured_output(
            Acessions, strict=True
        ).ainvoke(prompt)
        return {"SRX": response.srx}
```

Also used in: `workflows/metadata.py:invoke_SRX2SRR_sragent_agent_node()` where SRR accessions are extracted via `re.findall(r"(?:SRR|ERR)\d{4,}", content)` from the agent's response.

---

## Pattern 11: NCBI Web Scraping with BeautifulSoup

**Purpose**: Extract structured data from NCBI web pages when Entrez API is insufficient.

**Where used**: `tools/ncbi_fetch.py` (lines 12-362)

```python
def _fetch_ncbi_record(term, database="sra"):
    url = f"https://www.ncbi.nlm.nih.gov/{database}/?term={term}"
    for attempt in range(3):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                break
            time.sleep(2**attempt)
        except Exception:
            time.sleep(2**attempt)

    soup = BeautifulSoup(response.text, "html.parser")
    section = soup.find("p", class_="details expand e-hidden")
    # ... extract and format data
```

Five specialized scrapers: `fetch_ncbi_record`, `fetch_geo_record`, `fetch_pubmed_record`, `fetch_biosample_record`, `fetch_bioproject_record`

---

## Pattern 12: Dynaconf Environment Switching

**Purpose**: Switch between configuration environments without code changes.

**Where used**: `agents/utils.py:load_settings()`, `db/connect.py:db_connect()`

```python
settings = Dynaconf(
    settings_files=[s_path],
    environments=True,
    env_switcher="DYNACONF"
)
# Access: settings["models"]["default"]
```

Environments: `test`, `prod`, `claude` -- each with independent model, temperature, reasoning, service_tier, and database settings.

---

## Pattern 13: Rich Console Progress Display

**Purpose**: Show streaming agent progress with spinners, step summaries, and formatted final output.

**Where used**: `agents/display.py` (lines 144-302)

```python
async def create_agent_stream(input, create_agent_func, config, summarize_steps, no_progress):
    console = Console(stderr=True)
    console.print(Panel.fit("[bold green]SRAgent Processing Request[/bold green]..."))

    if no_progress:
        async for step in agent.astream(input, stream_mode="values", config=config):
            if step_summary_chain:
                msg = await step_summary_chain.ainvoke({"step": step})
                console.print(f"Step {step_cnt}: {msg.content}")
    else:
        with Progress(SpinnerColumn(), TextColumn("..."), console=console):
            async for step in agent.astream(...):
                progress.update(task, description=f"Step {step_cnt}...")

    display_final_results(results)  # Markdown-aware Rich panel
```

---

## Pattern 14: Database Upsert with Unique Constraint Detection

**Purpose**: Insert-or-update records using database schema introspection.

**Where used**: `db/upsert.py:db_upsert()` (lines 15-74)

```python
def db_upsert(df, table_name, conn):
    unique_columns = get_unique_columns(table_name, conn)  # introspect schema
    insert_stmt = f"INSERT INTO {table_name} ({columns}) VALUES %s"
    insert_stmt += f"\nON CONFLICT ({unique_cols}) DO UPDATE SET {update_cols}"
    execute_values(cur, insert_stmt, values)
```

**Key properties**:
- Schema-driven: reads unique constraints from `pg_constraint`
- Handles composite unique keys
- Uses `psycopg2.extras.execute_values` for batch efficiency
- Transaction rollback on error

---

## Pattern 15: Credential Rotation for Rate Limit Distribution

**Purpose**: Distribute NCBI API calls across multiple credentials to increase effective rate limits.

**Where used**: `tools/utils.py:set_entrez_access()` (lines 129-151)

```python
def set_entrez_access():
    email_indices = []
    for i in range(11):
        if os.getenv(f"EMAIL{i}"):
            email_indices.append(i)
    if len(email_indices) == 0:
        Entrez.email = os.getenv("EMAIL")
        return
    n = random.choice(email_indices)
    Entrez.email = os.getenv(f"EMAIL{n}")
    Entrez.api_key = os.getenv(f"NCBI_API_KEY{n}")
```

Called before each Entrez API batch. Supports up to 10 numbered credential sets.

---

## Pattern 16: Graph Visualization Export

**Purpose**: Export workflow graphs to visual formats for documentation.

**Where used**: `workflows/graph_utils.py` (lines 1-109)

```python
def handle_write_graph_option(graph_creator, output_file):
    obj = graph_creator()
    if hasattr(obj, "get_graph"):
        write_workflow_graph(obj, output_file)  # .png, .svg, .pdf, .mermaid
    elif hasattr(obj, "compile"):
        compiled = obj.compile()
        write_workflow_graph(compiled, output_file)
```

Available on every CLI subcommand via `--write-graph`.

## Completeness Assessment

This document catalogs 16 reusable design patterns covering: agent composition (patterns 1, 5, 6), model management (2, 3, 12), output validation (4, 10), external API interaction (7, 8, 9, 11, 15), state management (5, 6), UI/UX (13, 16), and database operations (14). Each pattern includes the specific files and line numbers where it is implemented, along with representative code snippets. Minor utility patterns not covered: XML-to-JSON conversion pipeline, string truncation utilities, and subprocess command execution wrapper.
