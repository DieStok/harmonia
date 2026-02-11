# Multi-Table Metrics: Discussion Notes & Plan

**Date:** 2026-02-10 18:18
**Context:** Preparing metrics pipeline to handle 2+ input tables harmonized into one output table.

---

## Current Single-Table Assumptions

The current metrics pipeline assumes:

1. **One gold column mapping** (`{source_col: target_col}`) — maps columns from *one* input table to *one* target schema
2. **One LLM column mapping** (`column_mapping.json`) — the LLM's mapping for that *one* table
3. **One gold standard CSV** and **one LLM output CSV** — compared row by row
4. **Row counts roughly match** — same source, same output
5. **Comma separator** hardcoded in `pd.read_csv()`

---

## What Changes With Multi-Table

The core challenge: with N input tables, each source table has its own set of source columns that get mapped to a shared target schema. So there are N column mappings, not one.

- **Two-table case:** `dou_2020` has columns like `Histologic_Grade_FIGO`, `Gender`. `dou_2023` has `Histologic_grade`, `Sex`. Both must map to the same GDC target columns (`tumor_grade`, `gender`). That's **two separate column mappings** to evaluate.

- **Ten-table case:** 10 source tables each with wildly different column names. `krug_2020` has `Age.in.Month`, `cao_2021` has `age`, `wang_2021` has `age`. Each needs its own source-to-target mapping. That's **10 column mappings**.

---

## Decisions Made

1. **Two-table gold standard:** Will be created manually (doesn't exist yet). Focus on ten-table case first since it has a real gold standard (Li et al. 2023).

2. **Column mapping structure:** Per-source-table mappings, not a flat union. Format:
   ```json
   {
     "cao_2021": {"case_id": "Case_ID", "age": "Age", "sex": "Sex", ...},
     "krug_2020": {"Sample.ID": "Case_ID", "Age.in.Month": "Age", ...},
     ...
   }
   ```
   The single-table case becomes a special case where this dict has one key.

3. **Per-source-table reporting:** Metrics broken down by source table (e.g., "BRCA mapping accuracy: 80%, PDAC mapping accuracy: 60%") in addition to overall.

4. **Graceful degradation:** Code should handle the case where gold standard column mapping is not yet available — skip column mapping metrics and only do value metrics (which just need gold CSV + LLM CSV + index column). This lets us start evaluating immediately.

---

## Key Findings From Data Exploration

### Separator Inconsistency

Most source files use `;` but vasaikar_2019 (COAD) uses `,`. The gold standard also uses `;`. Need a `separator` parameter for `pd.read_csv()`.

### Identifier Column Differences Across Source Tables

| Source Table | ID Column Name | Separator |
|---|---|---|
| cao_2021 (PDAC) | `case_id` | `;` |
| clark_2019 (ccRCC) | `Case_ID` | `;` |
| dou_2020 (UCEC) | `idx` | `;` |
| gillette_2020 (LUAD) | `Sample.ID` | `;` |
| huang_2021 (HNSCC) | `case_id` | `;` |
| krug_2020 (BRCA) | `Sample.ID` | `;` |
| mcdermott_2020 (HGSC) | `CPTAC Case ID` | `;` |
| satpathy_2021 (LSCC) | `Sample.ID` | `;` |
| vasaikar_2019 (COAD) | `attrib_name` | `,` |
| wang_2021 (GBM) | `case_id` | `;` |

The gold standard uses `Case_ID` as the unified identifier. The LLM must map all these different ID columns to `Case_ID` in the merged output.

### Source Table Grouping Column

The gold standard has `tumor_code` (BRCA, PDAC, ccRCC, etc.) which identifies which source study each row came from. This is the natural column to split metrics by source table.

### Row Count Mismatches Between Source Data and Gold Standard

This is important — the gold standard was independently curated, not a simple transform of the source data:

| Source Study | Source CSV Rows | Gold Standard Rows | Ratio |
|---|---|---|---|
| cao_2021 (PDAC) | 139 | 154 | gold has MORE |
| clark_2019 (ccRCC) | 998 | 110 | gold has far FEWER (filtered subset) |
| dou_2020 (UCEC) | 152 | 123 | gold has fewer |
| gillette_2020 (LUAD) | 224 | 111 | gold has fewer |
| huang_2021 (HNSCC) | 109 | 111 | roughly equal |
| krug_2020 (BRCA) | 121 | 138 | gold has MORE |
| mcdermott_2020 (HGSC) | 92 | 108 | gold has MORE |
| satpathy_2021 (LSCC) | 215 | 110 | gold has fewer |
| vasaikar_2019 (COAD) | 110 | 110 | exact match |
| wang_2021 (GBM) | 109 | 110 | roughly equal |
| **Total** | **~2,269** | **1,185** | **gold is ~52% of source** |

Key implications:
- ccRCC has 998 source rows but only 110 in the gold standard — massive filtering happened
- Some studies (PDAC, BRCA, HGSC) have MORE rows in gold than source — Li et al. may have added rows from other sources, or the source CSVs we have are incomplete extracts
- We can only evaluate rows that appear in BOTH the gold standard and the LLM output — the index-based join we already implemented handles this correctly
- **Coverage metric needed:** what fraction of gold standard rows did the LLM actually produce? This is especially important since the LLM might not merge all 10 tables, or might miss some studies entirely

### Source Data Column Counts

| Source | Columns |
|---|---|
| cao_2021 (PDAC) | 39 |
| clark_2019 (ccRCC) | 26 |
| dou_2020 (UCEC) | 179 |
| gillette_2020 (LUAD) | 74 |
| huang_2021 (HNSCC) | 37 |
| krug_2020 (BRCA) | 54 |
| mcdermott_2020 (HGSC) | 22 |
| satpathy_2021 (LSCC) | 82 |
| vasaikar_2019 (COAD) | 28 |
| wang_2021 (GBM) | 28 |
| **Gold standard** | **85** |

Huge variation — dou_2020 has 179 columns, mcdermott_2020 has 22. The gold standard has 85 unified columns. Many source columns won't map to anything in the target schema, and many gold columns won't have data from every source table.

### Gold Standard Schema

85 columns using a Li et al. 2023 pan-cancer schema (NOT GDC). Column names use a hierarchical naming convention with `/` separators, e.g.:
- `baseline/tumor_site`
- `baseline/tumor_size_cm`
- `follow-up/vital_status`
- `medical_history/bmi`
- `specimen/aliquout_id_protein_tumor`

This is different from the GDC schema used in Experiment 1. The target schema for Experiment 3 is the Li et al. schema, not GDC.

---

## Edge Cases and Difficulties

1. **Duplicate column names across source tables** — `age` appears in 8+ source tables. Column mapping must be per-table, not a flat dict.

2. **Not all gold columns are evaluable** — Some gold columns (like `specimen/aliquout_id_protein_tumor`) are unique sample IDs that don't require harmonization. Need to decide which columns are worth evaluating, or evaluate all and let the user filter.

3. **Missing data patterns differ by study** — A correct harmonization should leave columns blank for studies that lack the data. A study with 22 columns can't fill 85 gold standard columns. Need to distinguish "correctly empty" from "omission."

4. **The LLM might not harmonize all 10 tables** — Need per-source-table coverage (how many of the 10 studies did the LLM include?).

5. **Gold standard column mapping JSONs don't exist yet** — Need to be authored manually for each of the 10 source tables. This is significant manual effort (10 tables x ~30-80 columns each, mapping to 85 target columns).

6. **Value encoding differences** — Same concept encoded differently across studies (e.g., age in months vs years, different grade naming conventions). The value metrics capture this, but it's worth noting that "genuine errors" might partly reflect valid alternative encodings.

---

## Plan: Steps to Implement

### Phase 1: Core code changes (can start immediately)

- Add `separator` parameter to `calculate_all_metrics()`, `calculate_metrics.py` CLI, and `EvaluationConfig`
- Add `source_group_column` parameter (e.g., `tumor_code`) to split metrics by source table
- Change `gold_column_mapping` type from `dict[str, str]` to `dict[str, dict[str, str]]` (outer key = source table name) — detect format automatically so single-table `{src: tgt}` still works as before
- Change `llm_column_mapping` type similarly to per-source-table
- Add per-source-table value metrics to `MetricsResult` schema — a dict keyed by source table name containing per-table `OverallSummary` plus row coverage
- Add row coverage metric — fraction of gold standard rows present in LLM output, overall and per source table
- Bump schema to v1.2

### Phase 2: Per-source-table column mapping evaluation

- Evaluate column mapping per source table — for each source table, compare its column mapping against the gold standard mapping for that table
- Aggregate column mapping metrics across all source tables
- Update CLI summary output to show per-table breakdown

### Phase 3: Gold standard authoring (manual work)

- Create per-table gold standard column mappings for the ten-table experiment — 10 JSON files or one nested JSON mapping each source table's columns to the Li et al. target schema
- Decide which gold columns to evaluate — probably exclude pure identifier columns like specimen IDs unless they're meaningful
- Create gold standard for two-table experiment — merged CSV + per-table column mappings

### Phase 4: Integration & testing

- Run ten-table evaluation with value-metrics-only mode (no column mapping gold standard yet)
- Verify single-table experiments still work (backward compatibility)
- Add per-source-table breakdown to `calculate_metrics.py` summary output
