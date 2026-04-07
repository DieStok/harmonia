# SRAgent: Code Organization Practices

## 1. Directory Structure Assessment

```
SRAgent/                          # Repository root
  SRAgent/                        # Python package (same name as repo)
    __init__.py                   # Empty
    utils.py                      # Top-level utility (save_graph_image)
    organisms.py                  # OrganismEnum definition
    search.py                     # construct_query() helper
    settings.yml                  # Dynaconf configuration
    cli/                          # CLI entry points
      __init__.py                 # Empty
      __main__.py                 # Main entry, subcommand dispatch
      utils.py                    # CustomFormatter
      entrez.py, sragent.py, srx_info.py, metadata.py,
      find_datasets.py, tissue_ontology.py, disease_ontology.py, papers.py
    agents/                       # LLM agent definitions
      utils.py                    # Model factory, settings loader, FlexTierChatOpenAI
      display.py                  # Streaming display, Rich formatting
      entrez.py, sragent.py, esearch.py, esummary.py, efetch.py, elink.py,
      bigquery.py, ncbi_fetch.py, sequences.py, entrez_convert.py,
      find_datasets.py, tissue_ontology.py, disease_ontology.py, papers.py
    tools/                        # Deterministic tool implementations
      utils.py                    # Shared helpers (XML, batching, credentials)
      vector_db.py                # ChromaDB loader
      esearch.py, esummary.py, efetch.py, elink.py, entrez_db.py,
      bigquery.py, ncbi_fetch.py, sequences.py,
      tissue_ontology.py, disease_ontology.py, papers.py
    workflows/                    # LangGraph state machine definitions
      __init__.py                 # Empty
      utils.py                    # Async NCBI fetch helpers
      graph_utils.py              # Graph export utilities
      convert.py, metadata.py, srx_info.py, find_datasets.py,
      tissue_ontology.py, disease_ontology.py
    db/                           # Database layer
      __init__.py                 # Empty
      utils.py                    # Schema introspection, execute_query
      connect.py, create.py, get.py, upsert.py, update.py, fix.py
  tests/                          # Test suite
    agents/, tools/, workflows/   # Mirror package structure
  scripts/                        # Standalone utilities
  notebooks/                      # Jupyter notebooks
  claude-skill/                   # Claude Code integration
  assets/                         # Documentation images
```

### Strengths
- **Clear 4-layer separation**: cli -> agents -> tools -> db with clean dependency direction
- **Parallel naming**: `agents/esearch.py` wraps `tools/esearch.py`; `agents/tissue_ontology.py` uses `tools/tissue_ontology.py`
- **Test structure mirrors source**: `tests/agents/`, `tests/tools/`, `tests/workflows/`
- **Configuration co-located**: `settings.yml` ships with the package

### Issues
- **Repo/package naming collision**: Both the repo root and the package are named `SRAgent/SRAgent/`, which can cause confusion
- **Empty `__init__.py` files**: No package-level exports; all imports use full module paths
- **`utils.py` proliferation**: 5 different `utils.py` files (top-level, cli, agents, tools, db) with no shared naming convention

## 2. Naming Conventions

### File naming
- **snake_case** throughout: `tissue_ontology.py`, `ncbi_fetch.py`, `find_datasets.py`
- **Exception**: `__main__.py` for CLI entry (standard Python convention)
- **Consistency**: Agent files mirror tool files (1:1 mapping where applicable)

### Function naming
- **Factory functions**: `create_<name>_agent()`, `create_<name>_graph()`, `create_<name>_workflow()`, `create_<name>_node()`
- **Tool wrappers**: `invoke_<name>_agent()` (inside factory functions)
- **Main functions**: `<name>_main(args)` for CLI handlers
- **Parser functions**: `<name>_parser(subparsers)` for argparse setup
- **Database functions**: `db_<verb>_<noun>()` (e.g., `db_upsert`, `db_get_srx_records`, `db_connect`)
- **Private functions**: `_fetch_ncbi_record()`, `_process_single_entrez_id()` (underscore prefix)

### Class naming
- **CamelCase**: `GraphState`, `FlexTierChatOpenAI`, `AllMetadataEnum`, `CustomFormatter`
- **Enum classes**: `OrganismEnum`, `Tech10XEnum`, `LibPrepEnum`, `CellPrepEnum`, `YesNo`, `Choices`
- **Pydantic models**: `UBERON_ID`, `MONDO_ID`, `Acessions`, `Choice`, `EntrezInfo`, `PublicationsResult`

### Variable naming
- **snake_case** for variables and parameters
- **UPPER_SNAKE_CASE** for constants: `ELINK_BASE_URL`, `MISSING_CLIENT_MSG`, `STRUCTURED_OUTPUT_AGENTS`
- **Inconsistency**: Some function parameters use `SRR_accessions` (Pascal + snake mix) while others use `entrez_ids`

### Naming issues
- `Acessions` (line 56, `workflows/convert.py`): Misspelled; should be `Accessions`
- `accesions` (line 155, `workflows/convert.py`): Misspelled variable name
- `state_mod` used universally for system prompts -- semantically correct ("state modifier") but `system_prompt` would be clearer
- `SRX_info_agent_main` vs `SRX_info_agent_parser`: Mixed camelCase/snake_case (the `SRX` part)

## 3. Separation of Concerns

### Layer responsibilities (well-separated)

| Layer | Responsibility | Does NOT contain |
|-------|---------------|-----------------|
| `cli/` | Argument parsing, async bridging, result display | LLM logic, API calls |
| `agents/` | LLM agent definitions, prompt engineering | Direct API calls, database access |
| `tools/` | Deterministic API wrappers, data transformation | LLM calls, state management |
| `workflows/` | State machine orchestration, routing, aggregation | Direct API calls (mostly) |
| `db/` | Database connection, CRUD operations | LLM logic, business logic |

### Cross-cutting concerns
- **Credential management**: `tools/utils.py:set_entrez_access()` is called from tools and workflows
- **Model creation**: `agents/utils.py:set_model()` is called from agents and workflows
- **Display**: `agents/display.py` is called from CLI layer

### Boundary violations (minor)
- `workflows/metadata.py` imports `set_model` directly (line 28) instead of going through an agent
- `workflows/metadata.py:invoke_SRX2SRR_sragent_agent_node()` creates a new `create_sragent_agent()` per invocation (line 409) rather than receiving it as a dependency
- `agents/bigquery.py` creates BigQuery client inline (line 96) rather than receiving it as a dependency

## 4. Abstractions and Interfaces

### Well-defined abstractions

**Agent factory interface**: All agent factories follow the same signature and return type:
```python
def create_<name>_agent(
    model_name: Optional[str] = None,
    return_tool: bool = True,
) -> Callable:
```

**Tool interface**: All tools use the `@tool` decorator from `langchain_core.tools`:
```python
@tool
def tool_name(
    param: Annotated[type, "description"],
) -> Annotated[return_type, "description"]:
    """Docstring."""
```

**Workflow graph interface**: All workflows return a compiled `StateGraph`:
```python
def create_<name>_graph() -> StateGraph:
    workflow = StateGraph(GraphState)
    # add nodes, edges
    return workflow.compile()
```

**Database interface**: All DB functions take `connection` as parameter:
```python
def db_<verb>(data, table_name: str, conn: connection) -> None:
```

### Missing abstractions

- **No base class for agents**: Each agent repeats the factory pattern; a base class or decorator could reduce boilerplate
- **No tool result type**: Tools return heterogeneous types (strings, dicts, lists); a unified result envelope would improve consistency
- **No explicit interface for workflows**: The "node function" signature (`async def f(state: GraphState) -> Dict[str, Any]`) is implicit
- **No configuration object**: Settings are loaded via `load_settings()` each time `set_model()` is called (no caching)

## 5. Code Duplication

### High duplication areas

**Tissue/Disease ontology tools** (`tools/tissue_ontology.py` vs `tools/disease_ontology.py`):
- Nearly identical code (350+ lines each)
- Same structure: `query_vector_db`, `get_neighbors`, `query_<ontology>_ols`
- Differ only in: ChromaDB URL, collection name, OBO URL, ID prefix (UBERON vs MONDO/PATO)
- **Recommendation**: Extract shared ontology resolution base with parameterization

**Tissue/Disease ontology agents** (`agents/tissue_ontology.py` vs `agents/disease_ontology.py`):
- Near-identical structure (144 lines each)
- Differ only in: tool imports, Pydantic model names, prompt text
- **Recommendation**: Parameterized factory function

**Tissue/Disease ontology workflows** (`workflows/tissue_ontology.py` vs `workflows/disease_ontology.py`):
- Near-identical structure (144 lines each)
- **Recommendation**: Same parameterized factory

**Entrez tool wrappers** (`tools/esearch.py`, `tools/esummary.py`, `tools/efetch.py`, `tools/elink.py`):
- Share identical batch processing, error handling, XML-to-JSON conversion patterns
- Each has slight variations in Entrez function calls and error handling

**CLI handler files**: All 8 CLI files follow the same pattern with minor variations

### Low duplication (well-factored)
- `tools/utils.py` properly centralizes shared utilities
- `agents/utils.py:set_model()` is a single model factory
- `db/utils.py` centralizes schema introspection

## 6. Error Handling Patterns

### Strengths
- Consistent use of try/except with informative error messages returned as strings
- Tools return error strings rather than raising (LLM can interpret errors)
- Retry logic with exponential backoff in multiple places
- Transaction rollback in database operations

### Issues
- **Bare `except Exception`**: Many places catch all exceptions (e.g., `tools/ncbi_fetch.py`, `agents/bigquery.py`), losing specific error information
- **Silent failures**: Some `except` blocks use `pass` or `continue` (e.g., `tools/esummary.py` line 53, `tools/elink.py` line 96)
- **Inconsistent error return types**: Some tools return error strings, others return dicts with error keys
- **No logging framework**: All error output goes to `print(..., file=sys.stderr)` or `print(...)` instead of Python's `logging` module

## 7. Type Annotations

### Strengths
- **Extensive use of `Annotated[type, description]`** on all tool parameters and return values
- **TypedDict** for all workflow states
- **Pydantic BaseModel** for structured outputs
- **Enum classes** for constrained fields

### Issues
- **Missing return types** on several functions (e.g., `create_convert_graph_node()`, many `create_*_node()` functions)
- **`Optional` vs `| None`** syntax mixed (older `Optional[str]` and newer `str | None` in same file)
- **`Dict[str, Any]` overuse**: Many functions return `Dict[str, Any]` when more specific types would be possible

## 8. Documentation

### Present
- Module-level docstrings on most public functions
- `Annotated` descriptions on tool parameters
- README.md with comprehensive usage examples
- AGENTS.md with project guidelines
- Example invocations in CLI help text and `__main__` blocks

### Missing
- **No API documentation** (no Sphinx/mkdocs setup)
- **No inline architecture comments** in workflow files explaining graph topology
- **No changelog** despite version 0.6.0
- **`search.py` has stale docstring**: describes `search_term` parameter but the function takes `search_terms` (plural, list)

## 9. Anti-Patterns and Technical Debt

### Anti-pattern: Settings loaded on every model creation
`agents/utils.py:set_model()` calls `load_settings()` which reads YAML and creates a Dynaconf instance on every invocation. In a pipeline with 20+ agents, this means 20+ file reads.
- **Impact**: Performance (minor, YAML is fast)
- **Fix**: Module-level singleton or `@lru_cache`

### Anti-pattern: Nested agent creation creates quadratic instantiation
When `sragent` creates `entrez` which creates `esearch/esummary/efetch/elink`, and `bigquery` also creates `entrez_convert` which creates `esearch/esummary/elink`, the leaf agents are instantiated multiple times.
- **Impact**: Memory, startup time, redundant LLM model initialization
- **Fix**: Agent registry / dependency injection

### Anti-pattern: God prompt in sragent
`agents/sragent.py` system prompt (50+ lines) tries to cover all possible tasks. Long system prompts consume tokens on every call.
- **Impact**: Token cost, potential confusion
- **Fix**: Dynamic prompt selection based on task type

### Anti-pattern: Mixed sync/async patterns
Some tools are sync (`tools/esearch.py:esearch`), some agents call `await agent.ainvoke()`, and CLI bridges with `asyncio.run()`. The `workflows/utils.py` uses `aiohttp` while tools use synchronous `requests`.
- **Impact**: Cannot benefit from async in tool calls
- **Fix**: Async versions of Entrez tools

### Technical debt: Typo in class name
`Acessions` in `workflows/convert.py` line 56 -- should be `Accessions`. This is a public Pydantic model.

### Technical debt: Unused imports and dead code
- `SRR` class in `workflows/metadata.py` line 116 is defined but never used in structured output
- Various commented-out code blocks throughout (standard for research code)

### Technical debt: Hardcoded URLs
- GCS URLs for ChromaDB downloads (`tools/tissue_ontology.py` line 45, `tools/disease_ontology.py` line 45)
- NCBI base URLs (`workflows/utils.py` lines 11-13)
- OBO download URLs
- These could be in `settings.yml`

## 10. Testing Assessment

### Coverage
- **CLI**: Smoke test via `--help` for all subcommands
- **Tools**: Unit tests for most tools (esearch, esummary, efetch, ncbi_fetch, BigQuery, sequences, tissue/disease ontology, papers, utils)
- **Agents**: Tests for display formatting and papers agent helpers
- **Workflows**: Tests for OpenAI refusal handling and async utilities
- **Missing**: No integration tests, no end-to-end tests, no mock-based LLM tests

### Test quality
- Tests focus on deterministic helper functions
- LLM-dependent functionality untested in CI (would require API keys)
- No property-based testing
- No performance/load tests

## Completeness Assessment

This assessment covers all 63 Python source files in the SRAgent package, evaluating: directory structure, naming conventions across 5 categories, separation of concerns across 5 layers, all public abstractions and interfaces, code duplication across 4 high-duplication areas, error handling patterns, type annotation practices, documentation presence, 6 specific anti-patterns/technical debt items, and testing coverage. Areas not assessed: JavaScript/TypeScript files (none in package), configuration file quality (covered in overview doc), and deployment infrastructure (Dockerfile, GCP Cloud Run).
