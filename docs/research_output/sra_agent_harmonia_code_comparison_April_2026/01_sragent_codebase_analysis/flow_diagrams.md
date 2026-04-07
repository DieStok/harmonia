# SRAgent: Flow Diagrams

## 1. CLI Entry Flow

```
User invokes: SRAgent <subcommand> <args>

cli/__main__.py:main()
  |
  +-- load_dotenv()
  +-- arg_parse()   # validates API key presence, parses subcommand
  +-- os.environ["DYNACONF"] = args.tenant   # set environment early
  +-- Entrez.email / Entrez.api_key set from env
  |
  +-- dispatch to <subcommand>_main(args)
       |
       +-- [Optional] handle --write-graph: create graph, export, exit
       +-- create agent/graph via factory function
       +-- asyncio.run(stream/invoke)
       +-- display results via Rich console
```

## 2. Simple Agent Flow (entrez, sragent subcommands)

These use `create_agent_stream()` from `agents/display.py`:

```
cli/entrez.py:entrez_agent_main(args)
  |
  +-- create_entrez_agent(return_tool=False)  # returns ReAct agent graph
  +-- asyncio.run(create_agent_stream(...))
       |
       +-- agent = create_agent_func(return_tool=False)
       +-- [Optional] step_summary_chain = create_step_summary_chain()
       +-- Rich console: print query header
       +-- async for step in agent.astream(input, stream_mode="values"):
       |    +-- step_cnt += 1
       |    +-- [If summarize_steps]: LLM summarizes step -> print
       |    +-- [Else]: display_step_simple() -> print
       |    +-- [If progress bar]: update spinner
       +-- extract final_step content
       +-- return final message string
  |
  +-- display_final_results(results)  # Rich panel with markdown rendering
```

### Internal ReAct Agent Loop (for entrez, sragent, etc.)

Each ReAct agent follows LangGraph's `create_react_agent` pattern:

```
START -> Agent (LLM with system prompt)
  |
  +-- LLM decides: call tool or respond
  |    |
  |    +-- [Call tool]: invoke sub-agent-as-tool
  |    |    |
  |    |    +-- Sub-agent runs its own ReAct loop
  |    |    +-- Returns AIMessage with name tag
  |    |    +-- Agent receives result, decides next action
  |    |
  |    +-- [Respond]: final AIMessage content
  |
  END
```

## 3. SRX-Info Workflow (Complex Multi-Stage Pipeline)

This is the most complex workflow. File: `workflows/srx_info.py`

```
cli/srx_info.py
  |
  +-- For each entrez_id (with semaphore-limited concurrency):
       |
       create_SRX_info_graph()
       |
       StateGraph(GraphState) with nodes:
       |
       START
         |
         v
       [convert_graph_node]  -- Convert Entrez ID to SRX accessions
         |                      (see Convert subgraph below)
         |
         v
       [continue_to_metadata]  -- CONDITIONAL: fan-out to parallel metadata
         |                        Uses langgraph.types.Send() for parallelism
         |                        Filters existing SRX if using database
         |
         +-- For each SRX accession:
         |    |
         |    v
         |  [metadata_graph_node]  -- Metadata extraction subgraph
         |                            (see Metadata subgraph below)
         |
         v
       [final_state_node]  -- Aggregate results, format messages
         |
         v
       END
```

### 3a. Convert Subgraph (`workflows/convert.py`)

```
START
  |
  v
[convert_agent_node]
  |  1. Try entrez_id_to_srx() -- async direct NCBI fetch (workflows/utils.py)
  |     Tries: efetch -> esummary -> elink across multiple databases
  |  2. If fails: fallback to sragent_agent (LLM-based conversion)
  |
  v
[get_accessions_node]
  |  1. Try regex extraction: r"(?:SRX|ERX)[0-9]{4,}+"
  |  2. If fails: LLM structured output (Acessions model)
  |     With retry on OpenAIRefusalError
  |
  v
[router_node]
  |  LLM-based decision: CONTINUE or STOP
  |  Uses structured output (Choice model)
  |  Checks if SRX/ERX accessions were found
  |  Max 2 attempts before forced exit
  |
  +-- CONTINUE -> back to [convert_agent_node]
  +-- STOP -> END
```

### 3b. Metadata Subgraph (`workflows/metadata.py`)

```
START
  |
  v
[sragent_agent_node]
  |  Invokes full SRAgent agent with metadata-specific prompt
  |  Asks for: is_illumina, is_single_cell, is_paired_end,
  |            lib_prep, tech_10x, cell_prep, organism,
  |            tissue, disease, perturbation, cell_line
  |
  v
[get_metadata_node]
  |  Structured extraction via LLM:
  |    - ChatPromptTemplate with system instructions + message history
  |    - model.with_structured_output(AllMetadataEnum, strict=True)
  |    - Retry up to 3 times on OpenAIRefusalError
  |    - Fallback to "unsure"/"unknown" defaults
  |  Post-processing logic checks:
  |    - If not single_cell -> tech_10x = not_applicable
  |    - If lib_prep != 10x_Genomics -> tech_10x = not_applicable
  |
  v
[tissue_ontology_node]
  |  Invokes tissue_ontology_workflow with tissue + context
  |  Returns list of UBERON:XXXXXXX IDs
  |
  v
[SRX2SRR_node]
  |  Invokes sragent_agent to find SRR/ERR accessions
  |  Regex extraction of SRR/ERR patterns
  |  Retries up to 2 times with modified prompt
  |
  v
[add2db_node]  (optional, if db_add=True)
  |  Upserts to srx_metadata and srx_srr tables
  |
  v
[final_state_node]
  |  Formats metadata into human-readable message
  |
  v
END
```

## 4. Find-Datasets Workflow (`workflows/find_datasets.py`)

```
START
  |
  v
[search_datasets_node]
  |  find_datasets_agent: uses esearch_scrna tool
  |  Applies organism filters, date ranges, library filters
  |  Excludes Smart-seq, MARS-seq
  |  Returns Entrez IDs of matching datasets
  |
  v
[get_entrez_ids_node]
  |  LLM structured extraction (EntrezInfo model)
  |  Filters existing IDs from database (if use_database)
  |  Caps results at max_datasets
  |  Upserts new IDs to database
  |
  v
[continue_to_srx_info]  -- CONDITIONAL: fan-out via Send()
  |  For each entrez_id -> Send("srx_info_node", input)
  |
  +-- For each entrez_id:
  |    |
  |    v
  |  [srx_info_node]  -- Full SRX-Info subgraph (Section 3)
  |
  v
[final_state_node]
  |  Aggregate all SRX metadata results
  |
  v
END
```

## 5. Papers Workflow (`agents/papers.py` + `cli/papers.py`)

```
cli/papers.py:papers_main(args)
  |
  +-- Parse input: single accession or CSV
  +-- For each accession (semaphore-limited):
       |
       process_accession()
         |
         +-- Create papers_agent (ReAct with structured output)
         |    Tools: esearch, esummary, efetch, elink sub-agents
         |    response_format=PublicationsResult
         |
         +-- Agent workflow:
         |    1. esearch: accession -> Entrez ID
         |    2. elink: SRA Entrez ID -> PubMed Entrez IDs
         |    3. For each PMID:
         |       a. efetch (XML) -> extract DOI
         |       b. esummary (fallback) -> extract DOI
         |    4. Return PublicationsResult structured output
         |
         +-- Extract PubMed IDs and DOIs
         +-- _download_papers_batch():
         |    For each DOI:
         |      1. Try preprint server (arXiv, bioRxiv, medRxiv)
         |      2. Try CORE API
         |      3. Try Europe PMC
         |      4. Try Unpaywall
         |
         +-- Return results dict
  |
  +-- Display results table (Rich)
  +-- [If CSV input]: merge results, write updated CSV
```

## 6. Tissue/Disease Ontology Workflow

```
CLI input: "Tissues: lung, brain, liver"
  |
  v
create_tissue_ontology_workflow()  -- Supervisor agent
  |  System prompt: split input into individual tissues
  |  Tool: create_tissue_ontology_agent()
  |
  +-- For each tissue description:
       |
       invoke_tissue_ontology_agent()  -- Worker agent
         |  response_format=UBERON_ID
         |
         +-- Step 1: query_vector_db() -- semantic search on ChromaDB
         |    Downloads uberon-full_chroma.tar.gz if missing
         |    Returns top-k similar Uberon terms
         |
         +-- Step 2: get_neighbors() -- graph traversal
         |    Downloads uberon-full.obo if missing
         |    Returns adjacent terms in ontology graph
         |
         +-- Step 3: Iterate 1-3 times
         |
         +-- Step 4: query_uberon_ols() -- OLS API lookup (if uncertain)
         |
         +-- Return: UBERON:XXXXXXX or "No suitable ontology term found"
  |
  v
Supervisor collects all UBERON_IDs
Returns: UBERON_IDS (list of IDs)
```

Disease ontology follows identical pattern with MONDO/PATO instead of UBERON.

## 7. Data Flow: Input to Output

### For `SRAgent find-datasets`:

```
Input: "Obtain recent single cell RNA-seq datasets in the SRA database"
  |
  v
[Entrez esearch] -- search terms + organism + date filters
  |
  v
Entrez IDs: [12345678, 87654321, ...]
  |
  v
[Per ID] Entrez ID -> efetch/esummary/elink -> SRX accession(s)
  |
  v
[Per SRX] SRX -> SRAgent agent -> raw metadata text
  |
  v
[Per SRX] Raw text -> LLM structured extraction -> AllMetadataEnum
  |                                                  (is_illumina, is_single_cell,
  |                                                   lib_prep, tech_10x, organism,
  |                                                   tissue, disease, ...)
  v
[Per SRX] Tissue text -> ChromaDB + OBO graph -> UBERON:XXXXXXX IDs
  |
  v
[Per SRX] SRX -> BigQuery/Entrez -> SRR accession list
  |
  v
[Optional] Upsert to PostgreSQL (srx_metadata + srx_srr tables)
  |
  v
Output: Formatted metadata report per SRX accession
```

## 8. Feedback Loops and Self-Correction

### Convert Graph Router Loop
- `workflows/convert.py` lines 194-200: After accession extraction, a router LLM decides CONTINUE/STOP
- If CONTINUE: loops back to convert_agent_node with feedback message
- Hard limit: 2 attempts (state["attempts"] >= 2 forces exit)

### SRR Extraction Retry
- `workflows/metadata.py` lines 396-432: If SRR regex extraction fails, retries with modified prompt
- Includes previous failed response as context
- Up to 2 attempts

### Structured Output Retry
- `workflows/metadata.py` lines 286-321, `workflows/convert.py` lines 99-120, `workflows/find_datasets.py` lines 100-125
- On `OpenAIRefusalError`: append permissive instruction, retry up to 3 times
- Final fallback: default/empty values

### Multi-Source Paper Download
- `tools/papers.py` lines 311-442: Sequential fallback chain (not a loop, but a cascade)

## 9. State Management

### LangGraph TypedDict States
Each workflow defines its own `GraphState(TypedDict)`:

- **Convert graph**: messages, entrez_id, SRP, SRX, SRR, route, attempts
- **Metadata graph**: messages, database, entrez_id, SRX, SRR, all metadata fields, tissue_ontology_term_id
- **SRX-Info graph**: messages, database, entrez_id, SRX (list), plus per-metadata lists
- **Find-Datasets graph**: messages, entrez_ids, database

### State annotation patterns:
- `Annotated[Sequence[BaseMessage], operator.add]` -- messages accumulate via addition
- `Annotated[List[str], operator.add]` -- lists accumulate (for fan-out/fan-in)
- `Annotated[str, "description"]` -- simple string fields

### Parallel execution
- `langgraph.types.Send()` used for fan-out to parallel subgraph invocations
- `asyncio.Semaphore` used for concurrency limiting at CLI level

## 10. Async Architecture

- All agent invocations are async (`ainvoke`, `astream`)
- CLI functions use `asyncio.run()` to bridge sync CLI to async internals
- `workflows/utils.py` provides async NCBI fetch helpers with `aiohttp`
- Semaphores limit concurrent NCBI requests (default 5) and concurrent workflow processing (configurable via `--max-parallel`)

## Completeness Assessment

This document covers all 8 CLI subcommands, all 4 workflow graphs (convert, metadata, srx_info, find_datasets), both ontology workflows, the papers pipeline, the ReAct agent execution pattern, all feedback/retry loops, all state management patterns, and the async architecture. The only flows not diagrammed are the standalone `scripts/` utilities, which are operational tools rather than core agent flows.
