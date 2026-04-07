# SRAgent: Full Codebase Overview

## 1. System Purpose

SRAgent (v0.6.0) is a multi-agent LLM-powered CLI tool for extracting metadata from the NCBI Sequence Read Archive (SRA). It was built to support the **scBaseCount** project -- a uniformly processed single-cell data repository. The system converts accession IDs, retrieves dataset metadata (organism, sequencing technology, tissue, disease), maps tissues/diseases to ontologies, finds publications, and optionally stores results in a PostgreSQL database.

## 2. Top-Level Components

| Directory | Role |
|-----------|------|
| `SRAgent/cli/` | CLI entry points (argparse parsers + main functions) |
| `SRAgent/agents/` | LLM-based agent definitions (ReAct agents wrapping tools) |
| `SRAgent/tools/` | Deterministic tool implementations (NCBI APIs, BigQuery, web scraping, ontology DBs) |
| `SRAgent/workflows/` | LangGraph state-machine workflows composing agents into multi-step pipelines |
| `SRAgent/db/` | PostgreSQL database layer (connect, create, get, upsert, update) |
| `scripts/` | Standalone utility scripts for database operations, evaluations, data conversion |
| `tests/` | Pytest test suite |
| `claude-skill/` | Claude Code skill definition for natural-language access |

## 3. Entry Points

### CLI (primary)
- **Entry point**: `SRAgent.cli.__main__:main` (registered as `SRAgent` console script in `pyproject.toml`, line 54)
- **Subcommands**: `entrez`, `sragent`, `metadata`, `srx-info`, `find-datasets`, `tissue-ontology`, `disease-ontology`, `papers`
- **Pattern**: Each subcommand has a `<name>_parser(subparsers)` function that registers CLI args, and a `<name>_main(args)` function that executes the workflow.

### Direct module execution
- Most agent and tool files have `if __name__ == "__main__":` blocks for standalone testing.

## 4. Module Dependency Graph

```
CLI Layer
  cli/__main__.py
    -> cli/entrez.py      -> agents/entrez.py
    -> cli/sragent.py     -> agents/sragent.py
    -> cli/srx_info.py    -> workflows/srx_info.py
    -> cli/metadata.py    -> workflows/metadata.py
    -> cli/find_datasets.py -> workflows/find_datasets.py
    -> cli/tissue_ontology.py -> workflows/tissue_ontology.py
    -> cli/disease_ontology.py -> workflows/disease_ontology.py
    -> cli/papers.py      -> agents/papers.py

Agent Layer (agents/)
  sragent.py (supervisor)
    -> entrez.py (supervisor)
        -> esearch.py  -> tools/esearch.py
        -> esummary.py -> tools/esummary.py
        -> efetch.py   -> tools/efetch.py
        -> elink.py    -> tools/elink.py
    -> ncbi_fetch.py   -> tools/ncbi_fetch.py
    -> bigquery.py     -> tools/bigquery.py
        -> entrez_convert.py (sub-supervisor)
    -> sequences.py    -> tools/sequences.py
  tissue_ontology.py   -> tools/tissue_ontology.py -> tools/vector_db.py
  disease_ontology.py  -> tools/disease_ontology.py -> tools/vector_db.py
  papers.py            -> tools/papers.py
  display.py           (streaming/formatting utilities)
  utils.py             (model factory, settings loader, flex-tier retry)

Workflow Layer (workflows/)
  find_datasets.py -> workflows/srx_info.py
  srx_info.py      -> workflows/convert.py + workflows/metadata.py
  metadata.py      -> agents/sragent.py + workflows/tissue_ontology.py
  convert.py       -> agents/sragent.py + workflows/utils.py
  tissue_ontology.py -> agents/tissue_ontology.py
  disease_ontology.py -> agents/disease_ontology.py

Tool Layer (tools/)
  esearch.py, esummary.py, efetch.py, elink.py  -- NCBI Entrez API wrappers
  entrez_db.py -- which_entrez_databases helper
  ncbi_fetch.py -- HTML scraping of NCBI web pages (SRA, GEO, PubMed, BioSample, BioProject)
  bigquery.py  -- Google BigQuery queries against SRA metadata
  sequences.py -- fastq-dump and sra-stat CLI wrappers
  tissue_ontology.py -- ChromaDB vector search + OBO graph + OLS API for Uberon
  disease_ontology.py -- ChromaDB vector search + OBO graph + OLS API for MONDO/PATO
  papers.py    -- Multi-source paper download (CORE, Europe PMC, Unpaywall, preprint servers)
  vector_db.py -- ChromaDB + OpenAI embeddings loader
  utils.py     -- Shared helpers (XML/JSON conversion, batching, truncation, Entrez credentials)

Database Layer (db/)
  connect.py -- GCP Secret Manager + psycopg2 connection
  create.py  -- Table DDL definitions (srx_metadata, srx_srr, eval, screcounter_*, scbasecamp_metadata)
  get.py     -- Query functions
  upsert.py  -- Upsert via ON CONFLICT
  update.py  -- Batch UPDATE
  fix.py     -- Blocking process management
  utils.py   -- Schema introspection, table listing
```

## 5. Configuration System

### settings.yml (`SRAgent/settings.yml`)
- Managed by **Dynaconf** with environment switching via `DYNACONF` env var
- Three environments: `test`, `prod`, `claude`
- Per-agent configuration for: `models`, `temperature`, `reasoning_effort`, `service_tier`
- 20+ named agent slots (esearch, esummary, elink, efetch, sequences, ncbi_fetch, bigquery, entrez, sragent, tissue_ontology, disease_ontology, metadata, metadata_router, convert_router, accessions, entrez_convert, find_datasets, step_summary, get_entrez_ids, papers)
- Default model: `gpt-5-mini` (test/prod), `claude-sonnet-4-5` (claude env)
- `service_tier: flex` enables OpenAI flex tier with automatic fallback to standard

### Environment variables
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` -- LLM provider (one required)
- `EMAIL` / `EMAIL1..EMAIL10` -- Entrez API email (random rotation for rate limit distribution)
- `NCBI_API_KEY` / `NCBI_API_KEY1..NCBI_API_KEY10` -- Entrez API key (same rotation)
- `DYNACONF` -- environment selector (test/prod/claude)
- `DYNACONF_SETTINGS_PATH` -- override settings file path
- `GCP_SQL_DB_PASSWORD` -- database password
- `GOOGLE_APPLICATION_CREDENTIALS` / `GCP_PROJECT_ID` -- GCP auth for BigQuery + Secret Manager
- `CORE_API_KEY` -- CORE API for paper downloads

### Model factory (`agents/utils.py`, `set_model()`, lines 162-315)
- Central function for creating LLM instances
- Supports OpenAI models (GPT-4o, o-series, GPT-5) and Anthropic Claude models
- Handles reasoning effort / thinking tokens for both providers
- `FlexTierChatOpenAI` subclass provides automatic fallback from flex to standard tier on timeout

## 6. External Service Integrations

| Service | Module | Purpose |
|---------|--------|---------|
| NCBI Entrez API | `tools/esearch.py`, `tools/esummary.py`, `tools/efetch.py`, `tools/elink.py` | Search, fetch, link biological database records |
| NCBI Web (HTML) | `tools/ncbi_fetch.py` | Scrape SRA, GEO, PubMed, BioSample, BioProject pages |
| Google BigQuery | `tools/bigquery.py` | Query `nih-sra-datastore.sra.metadata` for SRA metadata |
| GCP Secret Manager | `db/connect.py` | Fetch database credentials and SSL certificates |
| GCP PostgreSQL | `db/` | Store metadata results, SRR mappings, evaluation data |
| OpenAI API | `agents/utils.py` | LLM inference (GPT-4o, GPT-5-mini, o-series) |
| Anthropic API | `agents/utils.py` | LLM inference (Claude models) |
| OpenAI Embeddings | `tools/vector_db.py` | `text-embedding-3-small` for ChromaDB vector search |
| ChromaDB (local) | `tools/vector_db.py` | Vector similarity search for ontology terms |
| OBO ontology files | `tools/tissue_ontology.py`, `tools/disease_ontology.py` | Graph traversal of Uberon/MONDO ontologies |
| EBI OLS API | `tools/tissue_ontology.py`, `tools/disease_ontology.py` | Ontology Lookup Service queries |
| GCS (download) | `tools/tissue_ontology.py`, `tools/disease_ontology.py` | Download pre-built ChromaDB tarballs |
| CORE API | `tools/papers.py` | Academic paper search and download |
| Europe PMC API | `tools/papers.py` | Open access paper search and download |
| Unpaywall API | `tools/papers.py` | Open access paper location |
| bioRxiv/medRxiv/arXiv | `tools/papers.py` | Preprint download |
| SRA Tools (CLI) | `tools/sequences.py` | `fastq-dump`, `sra-stat` for sequence data inspection |

## 7. Error Handling Strategy

- **Retry with backoff**: NCBI API calls use exponential backoff for HTTP 429 errors (`tools/esearch.py` lines 173-183, `tools/elink.py` lines 78-103)
- **Flex tier fallback**: `FlexTierChatOpenAI` catches `TimeoutError`/`APITimeoutError` and retries with standard tier (`agents/utils.py` lines 37-84)
- **OpenAI refusal handling**: Structured output extraction catches `OpenAIRefusalError` and retries with modified prompts, falling back to defaults (`workflows/metadata.py` lines 287-321, `workflows/convert.py` lines 99-120)
- **Multi-source fallback**: Paper downloads try preprint servers -> CORE -> Europe PMC -> Unpaywall in sequence (`tools/papers.py` lines 311-442)
- **BigQuery credential degradation**: Missing GCP credentials return guidance message instead of crashing (`agents/bigquery.py` lines 91-111)
- **General exception catching**: Most tool functions catch broad exceptions and return error strings rather than raising (the LLM agent can then interpret the error)

## 8. Testing Approach

- **Framework**: pytest with `pytest-asyncio`
- **Test location**: `tests/` mirroring package structure (`tests/agents/`, `tests/tools/`, `tests/workflows/`)
- **CLI tests**: `test_cli_help.py` validates all subcommands respond to `--help` (subprocess-based)
- **Tool tests**: Individual tests for esearch, esummary, efetch, ncbi_fetch, BigQuery, sequences, tissue/disease ontology, papers, utils
- **Agent tests**: Tests for display formatting and papers agent
- **Workflow tests**: Tests for OpenAI refusal error handling and utility functions
- **No mocking of LLM calls**: Most tests appear to test deterministic helper functions; LLM-dependent tests would require API keys
- **CI**: GitHub Actions runs pytest on Python 3.11/3.12 for `main` and `dev` branches

## Completeness Assessment

This overview covers all 63 Python source files in the `SRAgent/` package, all configuration mechanisms, all external integrations, and the full dependency graph. Areas not deeply covered here but addressed in companion documents: prompt templates (see `prompt_and_context_management.md`), execution flows (see `flow_diagrams.md`), and agent orchestration patterns (see `subagent_architecture.md`). The `scripts/` directory (15 utility scripts) and `notebooks/` directory were noted but not individually analyzed as they are operational utilities rather than core architecture.
