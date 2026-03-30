---
title: "feat: Gold Standard Preprocessing Tools"
type: feat
status: active
date: 2026-03-30
origin: docs/brainstorms/2026-03-30-gold-standard-preprocessing-tools-brainstorm.md
---

# feat: Gold Standard Preprocessing Tools

## Overview

Two reusable CLI tools in `code_development_tools_agents/gold_standard_harmonized_table_tools/` that help humans and agents prepare for metadata harmonization tasks:

1. **`profile_tables.py`** — Profiles data tables using ydata-profiling, outputs curated markdown summaries with optional detailed/JSON modes.
2. **`match_columns.py`** — Uses Valentine schema matching to find likely column correspondences between table pairs, outputting CSV results.

These are preprocessing steps for gold-standard harmonized table creation, reusable across 2-table and N-table configurations. (See brainstorm: `docs/brainstorms/2026-03-30-gold-standard-preprocessing-tools-brainstorm.md`)

## Problem Statement / Motivation

Creating gold-standard harmonized outputs requires understanding each table's structure and finding column correspondences across tables. Currently this is manual and ad-hoc. These tools automate the discovery phase so that both humans and LLM agents can quickly assess what they're working with before harmonizing.

## Proposed Solution

Two single-file Python CLI scripts following the established `code_development_tools_agents/` patterns (argparse, `build_parser()`, fail-fast errors, progress to stderr). Both produce agent-friendly outputs (markdown, CSV) that can be directly consumed by LLM agents or read by humans.

## Technical Approach

### Shared Infrastructure

Both tools share these patterns:

**Input discovery:**
- Positional arg: path to directory (auto-discovers `.csv` and `.xlsx` files) or explicit file paths
- CSV dialect auto-detection via `csv.Sniffer` with `--separator` override on both tools
- Encoding: always use `encoding='utf-8-sig'` to strip BOM silently (the actual data files have UTF-8 BOM + CRLF)
- xlsx: use first sheet by default, `--sheet` flag to select, warning to stderr if multiple sheets exist
- `pandas.read_csv()` / `pandas.read_excel()` for loading
- Duplicate handling: when a directory contains both `.csv` and `.xlsx` for the same data (e.g., `mmc1.xlsx` alongside its derived CSV), auto-discovery picks up both. Users should pass explicit file paths to avoid duplicates, or use `--exclude-pattern` in a future version. For now, warn to stderr if the discovered file list seems to contain both formats.

**Output directory:**
- `--output-dir` flag with default: `code_development_tools_agents/gold_standard_harmonized_table_tools/DD_MM_YYYY_HH_MM_{INPUT_FOLDER_NAME}_output/`
- Note: underscores in timestamp (not colons) to avoid filesystem/transfer issues
- On collision (same minute): append `_2`, `_3`, etc.

**CLI framework:**
- argparse with `build_parser()` function, `RawDescriptionHelpFormatter`, epilog with usage examples
- Progress to stderr, results to files
- Exit codes: 0 = success, 1 = usage error, 2 = data/file error

**Error handling:**
- Fail fast with clear stderr messages
- Partial output preserved on disk — error message says which file/pair failed
- Validate paths early, check file readability before processing

### Tool 1: `profile_tables.py`

**Default output (curated markdown per table):**
Uses `ProfileReport(df, minimal=True)` then `get_description()` to extract:

```
# Profile: {filename}

## Table Overview
- Rows: N
- Columns: N
- Total missing cells: N (X.X%)
- Memory usage: X MB

## Column Summary

| Column | Type | Missing | Missing % | Unique | Unique % | Notes |
|--------|------|---------|-----------|--------|----------|-------|
| col1   | Numeric | 0 | 0.0% | 150 | 100% | mean=X, std=X, min=X, max=X |
| col2   | Categorical | 5 | 3.3% | 12 | 8.0% | top: "val1" (40%), "val2" (25%), ... |
```

For numeric columns, "Notes" shows: mean, std, min, max.
For categorical columns, "Notes" shows: top 5 values with percentages.

**`--detailed` mode:**
Switches to `ProfileReport(df, minimal=False)` with correlations disabled (too expensive for 200+ columns). Adds:
- Histogram bin counts for numeric columns
- Full value counts for columns with <20 unique values
- ydata-profiling alerts (CONSTANT, SKEWED, HIGH_CORRELATION, MISSING, etc.)
- Context-size warning printed to stderr: "Warning: --detailed produces larger output that may consume significant LLM context"

**`--json` mode:**
Dumps full `profile.to_json()` alongside the markdown. File: `{filename}_profile.json`.

**Output files:**
- `{output_dir}/profiles/{input_filename_without_ext}_profile.md`
- `{output_dir}/profiles/{input_filename_without_ext}_profile.json` (only with `--json`)

### Tool 2: `match_columns.py`

**Pairing strategy:**
- Default: all unique unordered pairs (N choose 2), excluding self-pairs
- `--pairs` flag: repeatable, takes exactly 2 filenames per invocation, resolved relative to input directory
  - Example: `--pairs table1.csv table2.csv --pairs table1.csv table3.csv`

**Matchers:**
- Default: `distribution` + `cupid`
- `--matchers` flag accepts any combination of: `distribution`, `cupid`, `jaccard`, `similarity_flooding`, `coma`
- Coma requires Java — if unavailable, warn to stderr and skip gracefully
- Each matcher runs independently on each pair

**Sampling:**
- `--sample-rows` flag, default behavior: use all rows, but auto-cap at 500 if table has >500 rows
- Sampling: random with fixed seed (42) for reproducibility; seed printed to stderr
- If user passes `--sample-rows N` where N > actual rows, silently use all rows

**Result combination:**
- Results from all matchers are **concatenated** into one CSV per pair
- The `matcher` column distinguishes which matcher produced each row
- Sorted by `similarity_score` descending within each matcher group

**CSV output schema:**

```csv
source_table,source_column,target_table,target_column,similarity_score,matcher
metadata_from_mmc1,Histologic_Grade_FIGO,metadata_from_mmc2,Histologic_grade,0.87,distribution_based
metadata_from_mmc1,Histologic_Grade_FIGO,metadata_from_mmc2,Histologic_grade,0.72,cupid
```

**Filtering flags:**
- `--threshold FLOAT` — minimum similarity score, default 0.0 (no filtering)
- `--top-n INT` — top N matches **per source column per matcher**, default: all
- `--one-to-one` — use Valentine's `one_to_one()` method (greedy, highest-score-first conflict resolution)

**Output files:**
- `{output_dir}/matches/{table1_stem}_vs_{table2_stem}_matches.csv`

**Recommended addition from SpecFlow: `--dry-run`**
- Lists discovered files, planned pairs, and selected matchers without executing
- Useful for verifying before long N-table runs

### Dependency Installation

Install both libraries into the existing project `.venv` from local repos:

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
.venv/bin/uv pip install -e /hpc/compgen/projects/llm_GEO_project/ydata-profiling
.venv/bin/uv pip install -e /hpc/compgen/projects/llm_GEO_project/valentine
```

### File Structure

```text
code_development_tools_agents/
  gold_standard_harmonized_table_tools/
    profile_tables.py
    match_columns.py
    30_03_2026_14_30_two_metadata_tables_harmonize_output/   # example
      profiles/
        metadata_endometrial_cancer_from_mmc1_profile.md
        metadata_endometrial_cancer_from_mmc2xlsx_profile.md
      matches/
        metadata_endometrial_cancer_from_mmc1_vs_metadata_endometrial_cancer_from_mmc2xlsx_matches.csv
```

## Implementation Phases

### Phase 1: Setup and shared utilities

1. Create `code_development_tools_agents/gold_standard_harmonized_table_tools/` directory
2. Install ydata-profiling and valentine into `.venv` via `uv pip install -e`
3. Verify imports work: `python -c "from ydata_profiling import ProfileReport; from valentine import valentine_match"`

### Phase 2: `profile_tables.py`

1. Scaffold CLI: `build_parser()` with args (positional input, `--output-dir`, `--detailed`, `--json`, `--separator`, `--sheet`)
2. Implement file discovery (glob `.csv` + `.xlsx` in directory, or use explicit paths)
3. Implement table loading with auto-dialect detection and BOM handling
4. Implement curated markdown generation from `get_description()`
5. Implement `--detailed` mode (fuller profiling, alerts section, context-size warning)
6. Implement `--json` mode (dump alongside markdown)
7. Test on actual data: `two_metadata_tables_harmonize/data/*.csv`

### Phase 3: `match_columns.py`

1. Scaffold CLI: `build_parser()` with args (positional input, `--output-dir`, `--matchers`, `--pairs`, `--threshold`, `--top-n`, `--one-to-one`, `--sample-rows`, `--separator`, `--sheet`, `--dry-run`)
2. Implement file discovery (same pattern as Phase 2 — duplicate the ~10 lines rather than extracting a shared module)
3. Implement pair generation (all-pairs default, `--pairs` filtering)
4. Implement sampling logic (auto-cap at 500, fixed seed)
5. Implement matcher execution loop (instantiate selected matchers, run `valentine_match` per pair)
6. Implement CSV output with concatenated results
7. Implement `--dry-run` mode
8. Test on actual data: mmc1 vs mmc2 CSVs

### Phase 4: Validation and polish

1. Run both tools on the two-table dataset end-to-end
2. Verify output is agent-consumable (try feeding markdown/CSV to an LLM prompt)
3. Add epilog usage examples to both tools' `--help`
4. Check ruff compliance (line-length 100)

## Acceptance Criteria

- [ ] `profile_tables.py` produces per-table markdown summaries from a directory of CSVs
- [ ] `profile_tables.py --detailed` produces richer reports with alerts
- [ ] `profile_tables.py --json` dumps full ydata-profiling JSON alongside markdown
- [ ] `match_columns.py` produces CSV with column matches for all table pairs
- [ ] `match_columns.py --matchers` allows selecting specific Valentine matchers
- [ ] `match_columns.py --pairs` allows filtering to specific table pairs
- [ ] `match_columns.py --dry-run` lists planned operations without executing
- [ ] Both tools auto-detect CSV dialect (handles semicolons) and strip BOM
- [ ] Both tools support xlsx input with `--sheet` flag
- [ ] Output directory follows `DD_MM_YYYY_HH_MM_{folder}_output/` convention
- [ ] Both tools fail fast with clear stderr messages and appropriate exit codes
- [ ] Tools work on the actual two-table dataset at `raw/datasets_harmonia/two_metadata_tables_harmonize/data/`

## Dependencies & Risks

| Risk | Mitigation |
| --- | --- |
| ydata-profiling dependency conflicts with existing .venv packages | Install with `--no-deps` if conflicts arise, manually install only needed sub-deps |
| Valentine's Coma matcher fails without proper Java setup | Graceful skip with warning; other matchers work without Java |
| Large JSON output from ydata-profiling (200+ columns) | `--json` is opt-in; default curated markdown is compact |
| Valentine slow on wide tables (38K column pairs) | Auto-sampling at 500 rows; most computation is per-column-pair not per-row |

## CLI Examples

```bash
cd harmonia_metadata_agent/analysis/dstoker/harmonia

# Profile all tables in the two-table dataset
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/profile_tables.py \
  ../../raw/datasets_harmonia/two_metadata_tables_harmonize/data/

# Profile with detailed output + JSON
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/profile_tables.py \
  ../../raw/datasets_harmonia/two_metadata_tables_harmonize/data/ \
  --detailed --json

# Match columns across all table pairs (default matchers)
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/match_columns.py \
  ../../raw/datasets_harmonia/two_metadata_tables_harmonize/data/

# Dry run to see what would be matched
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/match_columns.py \
  ../../raw/datasets_harmonia/two_metadata_tables_harmonize/data/ \
  --dry-run

# Match with specific matchers, threshold, and one-to-one constraint
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/match_columns.py \
  ../../raw/datasets_harmonia/two_metadata_tables_harmonize/data/ \
  --matchers distribution cupid jaccard \
  --threshold 0.5 --one-to-one --top-n 10

# Custom output directory
.venv/bin/python code_development_tools_agents/gold_standard_harmonized_table_tools/match_columns.py \
  ../../raw/datasets_harmonia/two_metadata_tables_harmonize/data/ \
  --output-dir /tmp/my_matches/
```

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-03-30-gold-standard-preprocessing-tools-brainstorm.md](docs/brainstorms/2026-03-30-gold-standard-preprocessing-tools-brainstorm.md) — Key decisions: ydata-profiling only (no skimpy), curated markdown + optional JSON, user-selectable Valentine matchers with DistributionBased+Cupid defaults, CSV output with matcher column, auto-sampling at 500 rows.

### Internal References

- CLI pattern reference: `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` — argparse, `build_parser()`, dual output
- Dataset: `raw/datasets_harmonia/two_metadata_tables_harmonize/data/` — semicolon-separated CSVs with UTF-8 BOM
- Local ydata-profiling: `/hpc/compgen/projects/llm_GEO_project/ydata-profiling`
- Local valentine: `/hpc/compgen/projects/llm_GEO_project/valentine`

### SpecFlow Findings Incorporated

- BOM handling (`utf-8-sig` encoding) — actual data files have BOM
- Underscore timestamps instead of colons — filesystem/transfer safety
- `--separator` on both tools — consistency
- `--dry-run` on matcher — safety for large N-table runs
- Disable correlations in default profiling — too expensive for 200+ columns
- Fixed random seed for sampling — reproducibility
- Per-source-column scoping for `--top-n` — most useful for harmonization
