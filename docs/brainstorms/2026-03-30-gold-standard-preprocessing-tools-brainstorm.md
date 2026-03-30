# Brainstorm: Gold Standard Preprocessing Tools

**Date:** 2026-03-30
**Status:** Draft

## What We're Building

Two reusable CLI tools in `code_development_tools_agents/gold_standard_harmonized_table_tools/` that help humans and agents prepare for metadata harmonization tasks:

1. **Table Profiler** (`profile_tables.py`) — Generates curated markdown summaries of input data tables using ydata-profiling, with optional detailed/JSON output modes.

2. **Column Matcher** (`match_columns.py`) — Uses Valentine schema matching to find likely column correspondences between table pairs, outputting results as CSV.

These tools are preprocessing steps that feed into the gold-standard harmonized table creation workflow. They will be reused across different dataset configurations (2-table, N-table).

## Why This Approach

- **Agent-friendly outputs**: Markdown summaries and CSVs are directly consumable by LLM agents without parsing overhead.
- **Human-friendly too**: Markdown reads well in terminals and editors; CSV opens in any spreadsheet tool.
- **Reusable across datasets**: CLI interface with auto-detection means the same tools work on any tabular dataset, not just the current two-table task.
- **Incremental complexity**: Start with ydata-profiling only (skimpy deferred). Valentine matchers are user-selectable so users can start simple and add more.

## Key Decisions

### Tool 1: Table Profiler (`profile_tables.py`)

| Decision | Choice |
|----------|--------|
| **Profiling library** | ydata-profiling only (skimpy deferred to future) |
| **Default output** | Curated markdown summary per table |
| **Optional outputs** | `--detailed` for richer report (distributions, alerts, value counts — with context-size warning); `--json` for full ydata-profiling JSON dump |
| **Input discovery** | Auto-detect CSV dialect (separator sniffing); `--separator` override; support `.csv` and `.xlsx` (with `--sheet` flag) |
| **Profiling mode** | `minimal=True` by default for speed; `--detailed` switches to fuller analysis |
| **Markdown sections (default)** | Table overview (rows, columns, memory, total missing) + per-column: detected type, missing count/%, unique count/%, min/max/mean/std (numeric), top 5 values (categorical) |
| **Markdown sections (--detailed)** | Above + histogram bins for numeric, full value counts for low-cardinality categoricals, ydata-profiling alerts (CONSTANT, SKEWED, HIGH_CORRELATION, etc.) |
| **Output location** | `--output-dir` flag; defaults to `code_development_tools_agents/gold_standard_harmonized_table_tools/DD_MM_YYYY_HH:MM_{INPUT_FOLDER_NAME}_output/profiles/` |

### Tool 2: Column Matcher (`match_columns.py`)

| Decision | Choice |
|----------|--------|
| **Default matchers** | DistributionBased + Cupid |
| **Matcher selection** | `--matchers` flag accepts any combination of: `distribution`, `cupid`, `jaccard`, `similarity_flooding`, `coma` |
| **Pair selection** | All pairs by default (N*(N-1)/2); repeatable `--pairs table1.csv table2.csv` flag to filter specific comparisons (each `--pairs` takes exactly two filenames) |
| **Output format** | CSV with columns: `source_table, source_column, target_table, target_column, similarity_score, matcher` |
| **Filtering** | `--top-n` (default: show all, sorted by score descending); `--threshold` to filter by minimum score; `--one-to-one` flag for 1:1 matches only |
| **Input discovery** | Same auto-detection as profiler (CSV dialect sniffing, xlsx support) |
| **Output location** | `--output-dir` flag; defaults to `code_development_tools_agents/gold_standard_harmonized_table_tools/DD_MM_YYYY_HH:MM_{INPUT_FOLDER_NAME}_output/matches/` |

### Shared Conventions

| Decision | Choice |
|----------|--------|
| **CLI framework** | argparse (matches existing tools in code_development_tools_agents) |
| **Input argument** | Positional: path to directory (auto-discovers all `.csv` and `.xlsx` files) or explicit file paths |
| **Python environment** | Project `.venv` (must have ydata-profiling and valentine installed) |
| **Error handling** | Fail fast with clear error messages (per user preference) |
| **Logging** | Print progress to stderr, results to files |
| **Output dir naming** | `DD_MM_YYYY_HH:MM_{folder_name}_output/` under the tools directory |

## Architecture Sketch

```
code_development_tools_agents/
  gold_standard_harmonized_table_tools/
    profile_tables.py           # Tool 1: Table profiling
    match_columns.py            # Tool 2: Valentine column matching
    DD_MM_YYYY_HH:MM_two_metadata_tables_harmonize_output/  # Example output
      profiles/
        metadata_endometrial_cancer_from_mmc1_profile.md
        metadata_endometrial_cancer_from_mmc2xlsx_profile.md
        metadata_endometrial_cancer_from_mmc1_profile.json   # Only with --json
      matches/
        mmc1_vs_mmc2xlsx_matches.csv              # Combined: all matchers, distinguished by `matcher` column
```

## CLI Examples

```bash
cd harmonia_metadata_agent/analysis/dstoker/harmonia

# Profile all tables in a dataset directory
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/profile_tables.py \
  /path/to/datasets/two_metadata_tables_harmonize/data/

# Profile with detailed output + JSON
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/profile_tables.py \
  /path/to/datasets/two_metadata_tables_harmonize/data/ \
  --detailed --json

# Match columns across all table pairs
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/match_columns.py \
  /path/to/datasets/two_metadata_tables_harmonize/data/

# Match with specific matchers and threshold
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/match_columns.py \
  /path/to/datasets/two_metadata_tables_harmonize/data/ \
  --matchers distribution cupid jaccard \
  --threshold 0.5 --one-to-one

# Custom output directory
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/match_columns.py \
  /path/to/datasets/two_metadata_tables_harmonize/data/ \
  --output-dir /custom/output/path/
```

## Dependencies

| Library | Purpose | Notes |
|---------|---------|-------|
| ydata-profiling | Table profiling | Local repo at `/hpc/compgen/projects/llm_GEO_project/ydata-profiling` — install with `pip install -e` or use from venv |
| valentine | Column matching | Local repo at `/hpc/compgen/projects/llm_GEO_project/valentine` — install with `pip install -e` |
| pandas | DataFrame handling | Already in .venv |

## Resolved Questions

1. **Java availability for Coma**: Java 8 (OpenJDK 1.8.0_472) is available at `/usr/bin/java`. Coma matcher is supported.

2. **ydata-profiling/valentine installation**: Install both into the existing project `.venv` via `pip install -e` from the local repos.

3. **Large table performance**: Add `--sample-rows` flag to the column matcher tool (Valentine only — profiling with `minimal=True` handles full tables fine). Defaults to all rows but auto-caps at 500 if the table exceeds that. Users can override with an explicit value.
