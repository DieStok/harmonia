# Brainstorm: Two-Table Evaluation Pipeline Design

**Date:** 2026-03-13
**Status:** Draft
**Context:** Extending the single-table metrics pipeline (Experiment 1) to evaluate two-table harmonization (Experiment 2)

---

## What We're Building

The current evaluation pipeline assumes one source table harmonized to one external schema (GDC). Experiment 2 introduces **two source tables** (Dou 2020 / mmc1: 153 rows × ~179 cols; Dou 2023 / mmc2: 190 rows × ~213 cols) that must be harmonized together. We need to design the evaluation pipeline for two distinct approaches:

- **Approach A:** Harmonize each table independently to GDC, then concatenate
- **Approach B:** Harmonize both tables together into a self-determined unified schema (no external target)

---

## Step 1: Existing Pipeline — Key Design Decisions

From the implementation transcripts (sessions 611ff963, 5038997b, c7875125):

### Data Flow
1. Agent produces: harmonized CSV + `column_mapping.json` + (optionally) `value_mapping.json`
2. `calculate_metrics.py` loads gold standard files and agent output
3. `metrics.py` computes column mapping metrics and per-column value metrics
4. Output: `metrics.json` (Pydantic-validated) + `row_values.csv`

### Baked-In Assumptions
- **Single source CSV → single output CSV** (one-to-one)
- **Fixed target schema** (GDC): column mapping gold standard is `{source_col: gdc_col}`
- **Row alignment by index**: row _i_ in gold matches row _i_ in output
- **Column-wise independence**: no cross-column evaluation
- **Exact match after normalization**: no fuzzy matching (errors categorized as whitespace/case/genuine)
- **Macro-averaged metrics**: rare classes weighted equally
- **One-to-many column mappings raise NotImplementedError** (line 116)

### Key Design Choices (and why)
| Decision | Rationale |
|----------|-----------|
| Dual precision (incl/excl null) | Lets users compare whether null mappings are errors or intentional |
| Index-based row alignment | Handles LLM output with different row counts without silent misalignment |
| Sparse confusion matrices | Memory-efficient for large vocabularies |
| Error categorization hierarchy (strip → lower → strip+lower → genuine) | Identifies systematic LLM issues |
| Row comparisons written to CSV, not metrics.json | Space efficiency |
| Acceptable columns file (optional) | Handles ambiguous mappings like "Country" → either "country_of_birth" or "country_of_residence" |

---

## Step 2: Approach A — "Harmonize Separately, Then Combine"

### Concept
Each source table is independently harmonized to GDC. The agent produces two harmonized CSVs. These are vertically concatenated into one combined table. Evaluation happens at two levels: per-table and post-concatenation.

### Gold Standard Format

**Directory structure:**
```
gold_standard/
  approach_a/
    t1_column_mapping.json        # T1 source cols → GDC cols
    t1_value_mapping.json         # T1 source vals → GDC vals
    t1_acceptable_columns.json    # T1 acceptable alternatives
    t1_harmonized_gold.csv        # T1 expected harmonized output
    t2_column_mapping.json        # T2 source cols → GDC cols
    t2_value_mapping.json         # T2 source vals → GDC vals
    t2_acceptable_columns.json    # T2 acceptable alternatives
    t2_harmonized_gold.csv        # T2 expected harmonized output
    combined_harmonized_gold.csv  # Vertically concatenated gold (T1 + T2)
```

**Example t1_column_mapping.json** (same format as current):
```json
{
  "Country": "country_of_birth",
  "Histologic_Grade_FIGO": "tumor_grade",
  "Age": "age_at_index",
  "BMI": "bmi",
  "Gender": "gender"
}
```

**Example t2_column_mapping.json** (different source names, same GDC targets):
```json
{
  "Participant_country": "country_of_birth",
  "Histologic_grade": "tumor_grade",
  "Age": "age_at_index",
  "BMI": "bmi",
  "Sex": "gender"
}
```

**Value mappings follow the same per-table format.** T1 might have `"FIGO grade 1": "G1"` while T2 has `"Grade 1": "G1"` — different source vocabularies, same target.

### Metrics Pipeline Changes

**Level 1: Per-table evaluation (reuse existing pipeline)**
- Run `calculate_all_metrics()` independently on (T1 gold, T1 output) and (T2 gold, T2 output)
- Produces two independent `metrics.json` files — no code changes needed
- Each file reports column mapping accuracy and value metrics for that table

**Level 2: Cross-table schema consistency check (NEW)**
- After independent harmonization, verify that T1 and T2 mapped semantically-equivalent source columns to the **same** GDC target
- Example failure: T1 maps `"Gender" → "gender"` but T2 maps `"Sex" → "sex"` (should both be `"gender"`)
- New metric: **schema_consistency_score** = fraction of shared-concept columns that got the same GDC target name
- This requires a new gold standard artifact: **cross_table_column_equivalences.json**

```json
{
  "comment": "Source columns from T1 and T2 that should map to the same GDC target",
  "equivalences": [
    {"t1_source": "Country", "t2_source": "Participant_country", "expected_gdc_target": "country_of_birth"},
    {"t1_source": "Gender", "t2_source": "Sex", "expected_gdc_target": "gender"},
    {"t1_source": "Histologic_Grade_FIGO", "t2_source": "Histologic_grade", "expected_gdc_target": "tumor_grade"},
    {"t1_source": "Age", "t2_source": "Age", "expected_gdc_target": "age_at_index"},
    {"t1_source": "BMI", "t2_source": "BMI", "expected_gdc_target": "bmi"},
    {"t1_source": "Tumor_Size_cm", "t2_source": "Tumor_size_cm", "expected_gdc_target": "tumor_largest_dimension_diameter"}
  ]
}
```

**Level 3: Combined table evaluation (NEW)**
- After concatenation, check: do all 343 rows share the same column set?
- Metric: **column_union_penalty** — number of columns present in one sub-table but not the other (should be zero if both map to GDC correctly)
- Value-level: run existing value metrics on the combined CSV against `combined_harmonized_gold.csv`

**Aggregation strategy:**
- **Micro-average** across all rows (treats the 343-row table as one dataset — weights T2 more because it has more rows)
- **Macro-average** across tables (average of T1 metrics and T2 metrics — treats each table equally)
- Report both; let user decide which matters

### Files/Functions Changed
| File | Change |
|------|--------|
| `calculate_metrics.py` | New `--multi-table` mode; loop over per-table configs, then run cross-table checks |
| `metrics.py` | New `calculate_schema_consistency()` function |
| `schemas.py` | New `MultiTableMetricsResult` schema wrapping per-table results + cross-table metrics |
| Experiment YAML | New `evaluation.tables` list instead of single `gold_standard` path |

### New Failure Modes
1. **Schema divergence**: T1 and T2 map equivalent columns to different GDC names (e.g., `"gender"` vs `"sex"`)
2. **Column mismatch after concat**: T1 output has columns T2 doesn't (concat produces NaN columns)
3. **Value vocabulary collision**: Same GDC column gets different value conventions from T1 vs T2 (e.g., `"G1"` from T1 but `"Grade 1"` from T2, both supposedly GDC-compliant)
4. **Partial overlap blindness**: Agent harmonizes only the overlapping columns, ignoring T1-only or T2-only columns
5. **Index collision**: Both tables might have overlapping index values (row 1 in T1 and row 1 in T2)

---

## Step 3: Approach B — "Harmonize Together Directly"

### Concept
The agent receives both T1 and T2 simultaneously and produces a **single harmonized table** (343 rows). There is **no external target schema** — the agent invents the unified schema. This fundamentally changes what "correct" means.

### The Core Evaluation Problem

In Approach A, evaluation asks: "Did you pick the right GDC column?" — there's a fixed answer.

In Approach B, evaluation asks: "Did you recognize that T1's 'Country' and T2's 'Participant_country' are the same concept and unify them correctly?" — the target column name is the agent's choice, so we can't evaluate by string matching against a fixed name.

### Gold Standard Format

The gold standard must encode three things:
1. Which columns across T1 and T2 are semantically equivalent (column alignment)
2. What the unified values should be (value reconciliation)
3. Which columns exist in only one table (table-specific columns)

**Directory structure:**
```
gold_standard/
  approach_b/
    cross_table_column_alignment.json   # Which cols are the "same concept"
    unified_value_mapping.json          # How values should be reconciled
    combined_harmonized_gold.csv        # Expected 343-row output
    column_metadata.json                # Per-column metadata (provenance, type)
```

**cross_table_column_alignment.json:**
```json
{
  "comment": "Defines which source columns across T1 and T2 represent the same concept",
  "aligned_columns": [
    {
      "concept": "participant_country",
      "acceptable_unified_names": ["country", "participant_country", "country_of_origin"],
      "sources": {
        "t1": "Country",
        "t2": "Participant_country"
      }
    },
    {
      "concept": "histologic_grade",
      "acceptable_unified_names": ["histologic_grade", "tumor_grade", "grade"],
      "sources": {
        "t1": "Histologic_Grade_FIGO",
        "t2": "Histologic_grade"
      }
    },
    {
      "concept": "participant_age",
      "acceptable_unified_names": ["age", "age_years", "participant_age"],
      "sources": {
        "t1": "Age",
        "t2": "Age"
      }
    },
    {
      "concept": "biological_sex",
      "acceptable_unified_names": ["sex", "gender", "biological_sex"],
      "sources": {
        "t1": "Gender",
        "t2": "Sex"
      }
    }
  ],
  "t1_only_columns": [
    {
      "source": "Proteomics_TMT_batch",
      "acceptable_unified_names": ["proteomics_tmt_batch", "tmt_batch"]
    }
  ],
  "t2_only_columns": [
    {
      "source": "Metformin_treatment",
      "acceptable_unified_names": ["metformin_treatment", "metformin"]
    }
  ]
}
```

**unified_value_mapping.json:**
```json
{
  "comment": "For aligned columns, defines how values from both tables should be reconciled",
  "histologic_grade": {
    "winner": "t2_vocabulary",
    "comment": "T2 uses simpler naming; either is acceptable",
    "t1_mappings": {
      "FIGO grade 1": ["G1", "Grade 1", "FIGO grade 1"],
      "FIGO grade 2": ["G2", "Grade 2", "FIGO grade 2"],
      "FIGO grade 3": ["G3", "Grade 3", "FIGO grade 3"]
    },
    "t2_mappings": {
      "Grade 1": ["G1", "Grade 1", "FIGO grade 1"],
      "Grade 2": ["G2", "Grade 2", "FIGO grade 2"],
      "Grade 3": ["G3", "Grade 3", "FIGO grade 3"]
    }
  },
  "participant_age": "__identity__",
  "bmi": "__identity__",
  "biological_sex": {
    "winner": "either",
    "t1_mappings": {"Female": ["Female", "female", "F"], "Male": ["Male", "male", "M"]},
    "t2_mappings": {"Female": ["Female", "female", "F"], "Male": ["Male", "male", "M"]}
  }
}
```

Key difference from Approach A: values have **sets of acceptable outputs** rather than single correct answers, because the agent chooses the vocabulary.

### Metrics Pipeline Changes

**New metric 1: Column Alignment Accuracy (replaces column mapping precision/recall)**

Instead of "did you pick the right GDC column?", we ask: "did you recognize that these source columns are the same concept?"

- For each `aligned_columns` entry in the gold standard, check whether the agent's output has a single column containing data from both T1 and T2 sources
- **column_alignment_recall** = (correctly unified pairs) / (total expected pairs)
- **column_alignment_precision** = (correctly unified pairs) / (total pairs the agent unified)
- A "false merge" (agent unified two columns that shouldn't be) counts against precision
- A "missed merge" (agent kept them separate) counts against recall
- Column naming evaluated separately: did the agent's chosen name appear in `acceptable_unified_names`?

**New metric 2: Value Reconciliation Accuracy**

- For each aligned column, check whether values from both source tables are in a consistent vocabulary
- Use the `acceptable` lists from `unified_value_mapping.json`
- Score: fraction of cells where the agent's value appears in the acceptable set

**New metric 3: Table-Specific Column Handling**

- For `t1_only_columns` and `t2_only_columns`: did the agent preserve them?
- Rows from the other table should have empty/null values in these columns
- Score: fraction of table-specific columns correctly preserved

**Retained metrics (with adaptation):**
- Per-column value accuracy, error categorization, confusion matrices — same as current, but evaluated against `combined_harmonized_gold.csv`
- Row alignment: still index-based, but must handle the 153+190 split (T1 rows then T2 rows, or agent may interleave)

### Files/Functions Changed
| File | Change |
|------|--------|
| `metrics.py` | New `calculate_column_alignment_metrics()` replacing `calculate_column_mapping_metrics()`; new `calculate_value_reconciliation_metrics()` |
| `schemas.py` | New `ApproachBMetricsResult` with `ColumnAlignmentMetrics`, `ValueReconciliationMetrics` |
| `calculate_metrics.py` | New `--approach b` mode; load cross-table gold standard; different evaluation flow |

### What Metrics Replace the Current Ones?

| Current (single-table) | Approach B equivalent |
|---|---|
| Column mapping precision/recall | Column alignment precision/recall (did you unify the right pairs?) |
| Column mapping accuracy | Column naming accuracy (did you pick a reasonable name?) |
| Value mapping precision | Value reconciliation accuracy (did you pick a consistent vocabulary?) |
| Per-column value accuracy | Same, but against combined gold CSV with acceptable-value sets |
| Error categorization | Same (whitespace/case/genuine) |

---

## Key Decisions Made

1. **Approach A reuses the existing pipeline** almost entirely — the main new work is cross-table schema consistency checking
2. **Approach B requires fundamentally new metrics** because there's no fixed target schema
3. **Gold standard for Approach B uses acceptable-name sets** rather than single correct answers, to handle the agent's freedom in naming
4. **Both approaches need a cross-table column equivalence artifact** — the human must define which columns across T1 and T2 represent the same concept
5. **Row alignment for the combined table** needs a provenance marker (which source table each row came from)

---

## Open Questions

### Approach A
1. **Value vocabulary consistency after concat**: If T1 produces `"G1"` and T2 produces `"Grade 1"` for the same GDC column, both might be "correct" per their individual value mappings but inconsistent in the combined table. Should we add a post-concat value consistency check? Or is this the agent's responsibility to harmonize?
2. **Index handling**: T1 has `idx` column (1-153), T2 has `Idx` column (1-190). After concat, these collide. Should the gold standard specify a combined index scheme? Or use a `(source_table, original_index)` composite key?
3. **Column-only vs column-subset evaluation**: T1 has ~179 columns, T2 has ~213. Many are highly domain-specific (proteomics, genomics scores). Should the gold standard map ALL columns to GDC, or only a curated subset? If subset, how do we score columns the agent maps but the gold standard doesn't cover?
4. **Weighting in macro-average**: T1 has fewer rows but a different column set. Should macro-average weight by column count, row count, or equally?

### Approach B
5. **How to detect column alignment in agent output**: The agent produces a single CSV. How do we determine that the agent "unified" T1's `Country` with T2's `Participant_country`? Options: (a) require the agent to also output a mapping file, (b) infer from column names + non-null patterns, (c) require a provenance column. Each has trade-offs.
6. **Acceptable name sets — who defines them?**: The gold standard must list all acceptable unified names for each concept. This is subjective. How exhaustive should these lists be? Should we use fuzzy matching as a fallback?
7. **Row ordering in combined output**: Does the agent preserve T1-then-T2 order, or is it free to interleave/reorder? This affects row alignment for value metrics.
8. **Columns unique to one table**: If a column exists only in T1, the 190 T2 rows should be empty in the output. But the agent might fill them with inferred/hallucinated values. How do we score this — as hallucinations (current framework) or as a new error category?
9. **Granularity of value reconciliation**: For `histologic_grade`, the gold standard says T1's `"FIGO grade 1"` and T2's `"Grade 1"` should both become some consistent value. But what if the agent picks `"G1"` for T1 rows and `"Grade 1"` for T2 rows? Both are individually "acceptable" but inconsistent. Is within-column consistency a separate metric?
10. **Scale of the gold standard effort**: T1 has ~179 columns, T2 has ~213. Creating cross-table alignment for all of them is a massive manual effort. Should we evaluate only a curated subset (say, 20-30 clinically relevant columns) and ignore the rest?

### Both Approaches
11. **Should Approach A and B share a metrics schema version?** Or should they be separate schema versions with a shared base?
12. **Experiment YAML structure**: How does the config file specify which approach is being used? A single `evaluation.approach: "a"` or `"b"` flag, or completely separate config structures?

---

## Next Steps

- Resolve open questions (especially #5, #6, #9, #10 — these are blocking for implementation)
- Create gold standard artifacts for a small pilot subset (~10 columns) before committing to full coverage
- Decide whether to implement A first (lower risk, reuses existing code) or B first (higher value, more novel)
