# SRAgent: Prompt and Context Management

## 1. Complete Prompt Catalog

### 1.1 Agent System Prompts (state_mod / prompt parameters)

#### Entrez Supervisor Agent
- **File**: `agents/entrez.py`, lines 41-83
- **Role**: "helpful senior bioinformatician assisting a researcher"
- **Variables**: None (static prompt)
- **Key instructions**: Start with esearch, use efetch for details, esummary for summaries, elink for cross-DB navigation. Includes 4 example workflows.
- **Output style**: "plain text instead of markdown", concise lists

#### SRAgent Supervisor Agent
- **File**: `agents/sragent.py`, lines 39-89
- **Role**: "helpful senior bioinformatician" coordinating 4 sub-agents
- **Variables**: None (static)
- **Key instructions**: Describes each sub-agent's capabilities (Entrez, NCBI Fetch, BigQuery, Sequences). Strategy: try multiple approaches, cross-validate, provide ALL important info to agents. Contains domain warnings (bulk vs scRNA-seq).
- **Output style**: concise, lists, no markdown headers

#### esearch Agent
- **File**: `agents/esearch.py`, lines 32-41
- **Role**: "expert in bioinformatics"
- **Key instructions**: Use esearch, try sra/gds if one fails. Evidence-based, concise.

#### esummary Agent
- **File**: `agents/esummary.py`, lines 29-43
- **Role**: "expert in bioinformatics"
- **Key instructions**: Use esummary, can use which_entrez_databases tool. Evidence-based, concise.

#### efetch Agent
- **File**: `agents/efetch.py`, lines 33-44
- **Role**: "expert in bioinformatics"
- **Key instructions**: Use efetch, which_entrez_databases for DB disambiguation.

#### elink Agent
- **File**: `agents/elink.py`, lines 27-41
- **Role**: "expert in bioinformatics"
- **Key instructions**: elink for cross-DB linking, requires Entrez IDs (not accessions).

#### BigQuery Agent
- **File**: `agents/bigquery.py`, lines 49-77
- **Role**: "expert bioinformatician specialized in querying the SRA"
- **Key instructions**: Describes SRA hierarchy (SRP -> SRX -> SRR). Use entrez_convert for ID conversion. Warns about bulk vs scRNA-seq. Structured key-value output, no markdown.

#### NCBI Fetch Agent
- **File**: `agents/ncbi_fetch.py`, lines 36-53
- **Role**: "expert in bioinformatics"
- **Key instructions**: Direct NCBI website queries, accepts both Entrez IDs and accessions. Try multiple tools.

#### Sequences Agent
- **File**: `agents/sequences.py`, lines 30-42
- **Role**: "expert in bioinformatics"
- **Key instructions**: Use fastq-dump and sra-stat. fastq-dump only for SRR accessions.

#### Entrez Convert Agent
- **File**: `agents/entrez_convert.py`, lines 39-64
- **Role**: "helpful senior bioinformatician" for ID conversion
- **Key instructions**: Convert Entrez IDs to SRA/ENA accessions. 2 example workflows (SRA, GEO conversions).

#### Find Datasets Agent
- **File**: `agents/find_datasets.py`, lines 33-47
- **Role**: "expert in bioinformatics"
- **Key instructions**: Use esearch_scrna. Must make at least 2 attempts if first fails. Returns Entrez IDs.

#### Tissue Ontology Agent
- **File**: `agents/tissue_ontology.py`, lines 53-81
- **Role**: "helpful senior bioinformatician" for tissue classification
- **Structured output**: `UBERON_ID` Pydantic model
- **Key instructions**: 4-step workflow (vector DB -> neighbors -> iterate -> OLS). No valid term for "tumor"/"cancer" without tissue context. 1-3 iterations.

#### Disease Ontology Agent
- **File**: `agents/disease_ontology.py`, lines 53-78
- **Role**: "helpful senior bioinformatician" for disease classification
- **Structured output**: `MONDO_ID` Pydantic model
- **Key instructions**: Same 4-step workflow as tissue ontology, using MONDO/PATO instead of Uberon.

#### Tissue Ontology Workflow (Supervisor)
- **File**: `workflows/tissue_ontology.py`, lines 58-84
- **Role**: Supervisor splitting multi-tissue input into individual lookups
- **Structured output**: `UBERON_IDS` (list of `UBERON_ID`)
- **Key instructions**: Split semicolon/comma-separated tissues, invoke agent per tissue. No term for "tumor" without tissue context.

#### Disease Ontology Workflow (Supervisor)
- **File**: `workflows/disease_ontology.py`, lines 58-79
- **Role**: Same pattern as tissue, for MONDO/PATO
- **Structured output**: `MONDO_IDS`

#### Papers Agent
- **File**: `agents/papers.py`, lines 257-291
- **Role**: "expert bioinformatician helping to find publications"
- **Structured output**: `PublicationsResult` (accession + list of `PublicationDOI`)
- **Key instructions**: 4-step workflow (esearch -> elink -> efetch/esummary -> structured output). Describes each sub-agent's capabilities.

### 1.2 Workflow-Level Prompts

#### Metadata Extraction Prompt (SRAgent node in metadata graph)
- **File**: `workflows/metadata.py`, lines 183-196
- **Template variables**: `{SRX_accession}` (dynamically substituted)
- **Content**: "For the SRA experiment accession {SRX_accession}, find the following dataset metadata:" + enumerated metadata items
- **Source of metadata items**: `get_metadata_items()` extracts from `GraphState.__annotations__` (line 151-171)

#### Structured Metadata Extraction Prompt
- **File**: `workflows/metadata.py`, lines 259-283
- **Type**: ChatPromptTemplate with system message + MessagesPlaceholder
- **System message**: Instructions for extracting metadata from text, majority rules for ambiguous values, enum-specific guidance (lib_prep vs tech_10x logic), 300 char limit
- **Variables**: `{history}` (message history from state)

#### Convert Graph Router Prompt
- **File**: `workflows/convert.py`, lines 157-178
- **Type**: ChatPromptTemplate with system + human + MessagesPlaceholder
- **System**: Determine if SRX accessions obtained; STOP or CONTINUE
- **Variables**: `{history}` (last 4 messages), `{accesions}` (extracted accessions)

#### Accession Extraction Prompt
- **File**: `workflows/convert.py`, lines 88-94
- **Content**: "Extract SRX and ERX accessions... from the message below" + message content delimited by markers
- **Appended on retry**: "If no valid SRX/ERX accessions are found, return an empty list."

#### Entrez ID Extraction Prompt
- **File**: `workflows/find_datasets.py`, lines 79-94
- **Content**: Extract Entrez IDs and database name from message, with format guidance (GEO -> 'gds', SRA -> 'sra')
- **Appended on retry**: "If no valid Entrez IDs or database are found, return empty values."

#### SRX-to-SRR Prompt
- **File**: `workflows/metadata.py`, lines 400-407
- **Template variables**: `{state['SRX']}` (SRX accession)
- **Content**: "Find the SRR accessions for {SRX}. Provide a list. Generally, the bigquery agent can handle this task."

#### Tissue Ontology Node Prompt (within metadata graph)
- **File**: `workflows/metadata.py`, lines 377-388
- **Template variables**: tissues, organism, disease, perturbation, cell_line from state
- **Content**: "Primary information: The tissues: {tissues}" + secondary context

### 1.3 Step Summary Prompt
- **File**: `agents/display.py`, lines 25-33
- **Template**: "Concisely summarize the provided step in the langgraph workflow. The summary must be {max_tokens} tokens or less..."
- **Variables**: `{step}` (workflow step data)
- **Model**: Uses `step_summary` agent name, max_tokens=45

## 2. Runtime Prompt Assembly

### Pattern 1: Static string join
Most agent prompts are assembled at agent creation time via `"\n".join([...])`:
```python
state_mod = "\n".join([
    "# Instructions",
    " - You are an expert...",
    ...
])
agent = create_react_agent(model=model, tools=tools, prompt=state_mod)
```
This is used in: `entrez.py`, `sragent.py`, `esearch.py`, `esummary.py`, `efetch.py`, `elink.py`, `bigquery.py`, `ncbi_fetch.py`, `sequences.py`, `entrez_convert.py`, `find_datasets.py`, `tissue_ontology.py`, `disease_ontology.py`, `papers.py`

### Pattern 2: ChatPromptTemplate with MessagesPlaceholder
Used when conversation history must be injected:
```python
prompt = ChatPromptTemplate.from_messages([
    ("system", system_instructions),
    ("human", "\nHere are the last few messages:"),
    MessagesPlaceholder(variable_name="history"),
    ("human", additional_context),
])
formatted = prompt.format_messages(history=state["messages"][-4:])
```
Used in: `workflows/metadata.py` (structured extraction), `workflows/convert.py` (router)

### Pattern 3: Dynamic string formatting
```python
prompt = "For the SRA experiment accession {SRX_accession}, find..."
prompt.format(SRX_accession=state['SRX'])
```
Used in: `workflows/metadata.py` (SRAgent node), `workflows/srx_info.py` (continue_to_metadata), `cli/metadata.py`

### Pattern 4: Prompt augmentation on retry
On structured output failure, prompts are extended:
```python
prompt += "\nIf no valid SRX/ERX accessions are found, return an empty list."
# or
prompt.append(HumanMessage(content="If you cannot determine certain fields..."))
```
Used in: `workflows/convert.py` (lines 115-116), `workflows/metadata.py` (line 304), `workflows/find_datasets.py` (line 118)

## 3. Context Window Management

### Token limit awareness
- **Step summary chain**: Explicitly limited to `max_tokens=45` (`agents/display.py`, line 14)
- **Model max_tokens**: Set per-agent via `set_model()` with default of 1024 for Claude models (`agents/utils.py`, lines 271-288)
- **Claude thinking tokens**: Added on top of max_tokens (1024 for low, 2048 for medium, 4096 for high; `agents/utils.py`, lines 261-274)

### Truncation strategies
- **XML/JSON truncation**: `tools/utils.py:truncate_values()` limits XML element text to configurable max_length (500 for esummary, 1000 for efetch/elink)
- **Data structure truncation**: `tools/utils.py:truncate_data()` limits number of leaf nodes in nested structures
- **String field truncation**: `workflows/metadata.py:max_str_len()` caps extracted fields at 300 chars (100 for organism)
- **Display truncation**: `agents/display.py:format_agent_message()` limits displayed messages to 100 chars (line 74)
- **Message history windowing**: Router prompt uses only last 4 messages: `state["messages"][-4:]` (`workflows/convert.py`, line 179)

### BigQuery result limits
- All BigQuery queries use `LIMIT {limit}` with configurable limits (default 100; `tools/bigquery.py`)

### Entrez batch sizes
- esearch: `retmax=50` per batch for general queries, `retmax=10000` for scrna search
- esummary: batch_size=200, max_string_length=500
- efetch: batch_size=200, max_length=1000
- elink: batch_size=200, max_records=50 (configurable)

## 4. Prompt Chaining Between LLM Calls

### Sequential agent chains (within workflows)
The metadata workflow demonstrates the most complex chaining:

1. **sragent_agent_node** -> produces free-text metadata descriptions -> stored in `state["messages"]`
2. **get_metadata_node** -> reads `state["messages"]` via `MessagesPlaceholder` -> produces structured `AllMetadataEnum`
3. **tissue_ontology_node** -> reads extracted `state["tissue"]` -> produces UBERON IDs

### Supervisor-to-worker pattern
- Supervisor agents (entrez, sragent) include previous worker results in their message history
- Workers return `AIMessage(content=..., name="<agent_name>")` for attribution
- The ReAct agent automatically manages the tool-call/tool-response chain

### Cross-workflow chaining
- `find_datasets` -> `srx_info` -> `convert` + `metadata`: Each invocation receives the previous workflow's state

## 5. Few-Shot Examples

System prompts include **example workflows** (not few-shot completions):

- **Entrez agent** (`agents/entrez.py`, lines 72-83): 4 task-workflow examples
  - "Convert GSE123456 to SRX accessions" -> 2-step workflow
  - "Obtain SRR accessions for SRX4967527" -> 2-step workflow
  - "Is SRP309720 paired-end 10X data?" -> 2-step workflow
  - "Obtain SRA study accessions for Entrez ID" -> 1-step workflow

- **Entrez Convert agent** (`agents/entrez_convert.py`, lines 55-64): 2 task-workflow examples
  - SRA Entrez ID conversion -> 3-step workflow
  - GEO Entrez ID conversion -> 3-step workflow

No traditional few-shot (input/output pair) examples are used. The examples are procedural (describing which tools to call and in what order).

## 6. Structured Output Enforcement

### Pydantic Models Used for Structured Output

| Model | File | Fields | Used By |
|-------|------|--------|---------|
| `UBERON_ID` | `agents/tissue_ontology.py:24` | `id: str` | Tissue ontology agent |
| `UBERON_IDS` | `workflows/tissue_ontology.py:27` | `ids: List[UBERON_ID]` | Tissue ontology workflow |
| `MONDO_ID` | `agents/disease_ontology.py:24` | `id: str` | Disease ontology agent |
| `MONDO_IDS` | `workflows/disease_ontology.py:27` | `ids: List[MONDO_ID]` | Disease ontology workflow |
| `AllMetadataEnum` | `workflows/metadata.py:94` | 11 fields (YesNo, enums, strings) | Metadata extraction |
| `Acessions` | `workflows/convert.py:56` | `srx: List[str]` | Accession extraction |
| `Choice` | `workflows/convert.py:131` | `Choice: Choices (CONTINUE/STOP), Message: str` | Convert router |
| `EntrezInfo` | `workflows/find_datasets.py:63` | `entrez_ids: List[int], database: str` | Entrez ID extraction |
| `PublicationsResult` | `agents/papers.py:39` | `accession: str, publications: List[PublicationDOI]` | Papers agent |
| `PublicationDOI` | `agents/papers.py:33` | `pubmed_id: str, doi: str \| None` | Papers agent |
| `SRR` | `workflows/metadata.py:116` | `SRR: List[str]` | (Defined but unused in structured extraction) |

### Enforcement mechanism
```python
model.with_structured_output(AllMetadataEnum, strict=True).ainvoke(prompt)
```
- `strict=True` ensures the LLM output must conform to the schema
- ReAct agents use `response_format=<Model>` parameter: `create_react_agent(..., response_format=UBERON_ID)`
- Access via `result["structured_response"]`

### Enum types for constrained fields
- `YesNo`: yes/no/unsure
- `Tech10XEnum`: 12 values for 10X Genomics technologies
- `LibPrepEnum`: 17 values for library prep methods
- `CellPrepEnum`: single_nucleus/single_cell/unsure/not_applicable
- `OrganismEnum`: 47 organism species
- `Choices`: CONTINUE/STOP for routing decisions

## 7. Chain-of-Thought / Reasoning

### Explicit reasoning tokens (Claude)
- `agents/utils.py`, lines 260-277: Claude models get explicit thinking budgets
- STRUCTURED_OUTPUT_AGENTS (line 249-256) are excluded from thinking mode to ensure schema compliance
- Agents excluded: `convert_router`, `metadata_router`, `accessions`, `get_entrez_ids`, `entrez_convert`, `metadata`

### OpenAI reasoning effort
- o-series and GPT-5 models use `reasoning_effort` parameter (low/medium/high)
- Per-agent configuration in settings.yml (e.g., `sragent: medium`, `esearch: low`)

### Implicit reasoning via prompts
- "After each agent call, briefly analyze the agent's response" (entrez.py, sragent.py)
- "What information was obtained? Should I verify? What is still missing? Which agent(s) next?"
- This instructs the LLM to reason about its progress before deciding next action

## Completeness Assessment

This catalog includes all 18 system prompts from agent files, all 7 workflow-level prompts, the step summary prompt, all 10 Pydantic structured output models, all 5 enum types, all prompt assembly patterns, all truncation/windowing strategies, and all reasoning configurations. Every prompt string in the codebase that is passed to an LLM has been cataloged with file path, line numbers, and key content. The only prompts not covered are ad-hoc test prompts in `__main__` blocks.
