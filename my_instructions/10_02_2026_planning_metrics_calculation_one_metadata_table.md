# Planning Conversation: Metrics Calculation for One Metadata Table Harmonization

**Date:** 2026-02-10
**Participants:** User (dstoker), Claude Opus 4.6
**Purpose:** Design a metrics calculation pipeline for evaluating LLM metadata harmonization experiments

---

## User's Initial Request

I want to make a command-line python script that calculates metrics for metadata harmonization. To start off with, I want the accuracy, the precision, recall, and the F1 score. I also want detailed insights into the misclassifications: for each column, what is the 'classification' obtained, and what should it have been? This is not a two-class problem, each column has many possible values.

The command-line script always compares a gold-standard harmonized metadata file with the output of an experiment where an LLM agent harmonized this metadata (semi)-autonomously.

The script should also have logging. At least:
- columns in the input and gold standard csv
- unique values (and the columns they are in) for each separately, and any unique values for either that are not found in the other.

Finally, I currently have a pipeline where I can either manually or automatically run experiments with a certain experimental config.yaml file, and I automatically get named logs and named results folders with outputs. I want this metric calculation to happen automatically after the experiment has finished. Hence, we should think of some way to automatically run it once an output harmonized .csv has appeared in specific folders.

Also, the command-line python script should accept something like `{{experiment_name}}` and `{{timestamp}}` to name its output accordingly.

Later, I want to gather the metrics from all experiments, and combine them in another command line `visualize_performance_metrics.py` to see what models perform well, etc.

An example gold-standard output: `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/harmonized_dou_correct.csv`

---

## Claude's Initial Analysis

After examining the gold standard CSV (11 columns, ~104 rows of clinical/demographic data with GDC-compliant values), the experiment configs, the result directory structure, and the experiment runner code, Claude began a Socratic dialogue.

---

## Question 1: What exactly is a "cell" in this comparison?

**Claude:** Looking at the gold standard CSV, I see 11 columns and ~104 rows. The LLM output has 17 columns with different column names — the harmonization task maps both column names and cell values. When you say "accuracy, precision, recall, F1" — what is the unit of comparison?

Options:
- **(a) Cell-level:** Every individual cell (row x column) is a comparison unit. ~104 x 11 = 1,144 comparisons.
- **(b) Column-level:** Each column mapping is a comparison unit. Only ~11 comparisons.
- **(c) Both separately:** Column mapping accuracy as one metric, and then cell-level value accuracy per-column as another.

**User:** I want both the correct column mappings (schema matching) and the correct values within those columns (value mappings). The metrics script should report whether the column mapping is correct, and also report within-column metrics. I will decide later about whether to aggregate or average to a full-table score, for now I want both separated.

So: column names -> new column names (proper GDC schema in this instance) and within-column: proper GDC-compliant values.

---

## Question 2: This is not a standard classification problem — is it?

**Claude:** Standard multi-class precision/recall requires a fixed set of classes. Here you have:
- **Categorical columns** like `tumor_grade` (G1, G2, G3) — fit multi-class metrics naturally.
- **Continuous/numeric columns** like `bmi` (38.88, 39.76...) — precision/recall doesn't make sense here.
- **Free-text-ish columns** like `primary_diagnosis` — exact string match, or fuzzy matching?

Suggestion: Split columns into categorical vs. numeric, compute classification metrics only on categorical, and use exact-match accuracy (or MAE) on numeric.

**User:** For the numeric columns, the original data has these values, and the output data as harmonized by the LLM agent should recapitulate them. Hence, a 'classification' metric is still consistent. Allow an optional tolerance, and an optional amount of digits expected for each number. I still want exact string matches, since the GDC schema is strict. For now assume truly only one correct match.

---

## Question 3: How do we align the LLM output to the gold standard?

**Claude:** The gold standard has specific column names (`tumor_grade`, `primary_diagnosis`, etc.) and the LLM output may have different ones. Options:
- **(a)** Assume same column names
- **(b)** Use column mapping from experiment trace
- **(c)** Require explicit mapping file

**User:** For now, we know that the column must be in there for a correct mapping. If it is not there, the LLM did not get the gold standard, and it is a 0 for that column-column mapping and for values within it in principle. However, perhaps the LLM indeed chose another column from the GDC schema. I will resolve this by having the LLM output a `mapping.json` that lists `initial_colname : mapped_to_colname` so that the metric script can take this along. Fall-back option if that is not present should be to loudly complain about that in the logging and then do metric calculation for metrics that can be calculated.

---

## Question 4: Row alignment

**Claude:** Is the row order guaranteed to be preserved?

**User:** The rows should be aligned. If they are not, then something went wrong. Later tables will probably have an index column or key. Add functionality to check alignment and sort properly for the check based on this index column.

Note: `dou.csv` is actually a subset of `dou-ucec-discovery.csv`. Perhaps you can make a `dou_with_index.csv`, where the `Proteomics_Participant_ID` is added in, so that we could use that as well if needed.

---

## Question 5: Auto-triggering

**Claude:** Three options:
- **(a)** Hook into Python pipeline after `runner.run()`
- **(b)** Hook into shell script
- **(c)** Add `gold_standard` field to YAML config

**User:** Go for a + c.

---

## Question 6: Output naming

**Claude:** Should the metrics output just be a file inside the results directory (e.g., `metrics.json` alongside `trace.json`)?

**User:** Yes the metrics file should just be a file in that output folder. If the `experiment*.py` files take care of creating that and we can write to that we are good on this part.

---

## Additional Metrics Suggested by Claude

Beyond accuracy/precision/recall/F1:

1. **Column mapping recall/precision** — 11 target columns, LLM might map 9 correctly, miss 2, produce 1 extra
2. **Per-column completeness** — fraction of non-empty gold cells with non-empty LLM values
3. **Hallucination rate** — gold=empty but LLM produced a value
4. **Omission rate** — gold has value but LLM=empty
5. **Value-level confusion matrix per column** — for categorical columns
6. **Schema compliance rate** — fraction of cells with valid GDC values at all
7. **Timing metrics** — from trace.json

---

## Question 7: Case sensitivity

**Claude:** Gold standard has `"white"`, `"female"` (lowercase). What if LLM outputs `"White"`, `"Female"`? Should we also report case-insensitive accuracy?

**User:** In principle the LLM should be exactly correct. After all, the schema is strict. That means that extra whitespace is an error, as is capitalisation. That said: for each column, also categorize what fraction of errors are due to whitespace and wrong capitalization only, and output this in the metrics file.

---

## Question 8: Whitespace normalization

**Claude:** Should we strip whitespace before comparison?

**User:** (Same answer as Q7) — whitespace is an error, but categorize it.

---

## Question 9: The mapping.json — who produces it?

**Claude:** Three options for who creates the mapping.json.

**User:** Yes, option (c) — I'll handle it in the experiment prompt design, and the metrics script just expects `mapping.json` to exist (or not) in the results directory.

---

## Question 10: Multiple gold standards, multiple datasets

**Claude:** Should the metrics script handle arbitrary dataset/schema combinations from the start?

**User:** (Implicitly answered through config design — the `evaluation` block in the config points to the specific gold standard file, making it dataset-agnostic by design.)

---

## Question 11: dou_with_index.csv

**Claude:** Confirmed that `dou.csv` is the first 104 rows of `dou-ucec-discovery.csv` in the same order, aligned with the gold standard.

**User:** I will change the experiment configs and the gold standard to use the `.csv` with the index column and to compare it against a gold standard that has that selfsame index column if I choose to change the experiment. You can also make a `harmonized_dou_correct_with_index.csv` in preparation for this.

---

## Question 12: Columns the LLM produces that aren't in the gold standard

**Claude:** Options:
- **(a)** Ignore, just report which extras exist
- **(b)** Penalize extra columns

**User:** (a) for now. However if there are columns in the output that were not requested this should somehow count against the model. Report any columns that are outside of the gold standard (just report their count as a metric).

---

## Question 13: Config design for evaluation block

**Claude proposed:**
```yaml
evaluation:
  gold_standard: "/path/to/harmonized_dou_correct.csv"
  input_file: "/path/to/dou.csv"
  column_mapping_file: "mapping.json"
  index_column: null
  numeric_tolerance: 0.01
  numeric_precision: null
```

**User:** Correct. Introduce this config section in all config files.

---

## Question 14: Output format

**Claude compared three formats:**

1. **JSON** — naturally represents nested/hierarchical data, handles sparse confusion matrices, easy programmatic loading
2. **JSON + summary CSV** — best of both worlds: JSON for detail, CSV for quick comparison
3. **Pure CSV** — simple but can't represent confusion matrices

**User:** Let's just make it entirely JSON. Could you also create a Pydantic schema for this gold standard that the JSON should conform to so that that is clear and can be used by the visualisation script perhaps?

**Claude confirmed Pydantic schema is useful for:**
1. Validation at write time
2. Typed loading in visualization script
3. Documentation — the schema IS the spec
4. Forward compatibility

**User:** Agreed.

---

## Question 15: Empty/NaN handling in confusion matrix

**Claude:** Should empty/NaN be a valid "class" in the confusion matrix?

**User:** Set it as an option and log it. Default should be to treat cells that are empty in the gold standard as 'correct'. In-depth view should show that it is simply due to empty being categorized as correct. Perhaps just log the metric both counting and not-counting empty-empty matches.

---

## Question 16: mapping.json design — deep dive

**Claude identified scenarios:**
- **A — Correct mapping:** `Country` -> `country_of_birth`. Match.
- **B — Wrong mapping:** `Country` -> `country_of_residence`. Wrong name.
- **C — Missing mapping:** Column absent from mapping entirely.
- **D — Explicit null:** `Tumor_Site` -> `null`. Conscious decision, no GDC equivalent.
- **E — Extra column:** LLM maps to a column not in gold standard.
- **F — One-to-many:** LLM splits one column into two.

**Q16a:** Should explicit null differ from absent?
**User:** Yes. Treat differently.

**Q16b:** Should values still be evaluated for wrongly-named columns?
**User:** Yes, we are logging separate metrics for schema matching (column-column) and value-matching.

**Q16c:** One-to-many support?
**User:** Since one-to-many could in principle occur later, please construct a path for it in the code but do not implement anything there yet. If it is called just let it return a `NotImplementedError`.

**Q16d:** Should `mapping.json` also store value mappings?
**User:** I assume ideally we make a `column_mapping.json` and `value_mapping.json`. Where the latter has per-column `source_value:target_value` mappings. Let's build this into the pipeline. Also make me a `gold_standard_column_mapping.json` and `gold_standard_value_mapping.json` for this experiment.

Also: change all automated configs in the automated configs folder to properly list what needs to be saved + add in another prompt after saving `results/dou_harmonized.csv` that tells the LLM to save `results/column_mapping.json` with `source_column : target_column`, and `results/value_mapping.json` with `source_column : { unique_val_1_source_col : unique_val_1_target_col, ...}` etc.

---

## Nuanced discussion: Scenario B (wrong column mapping)

**User:** Scenario B is more nuanced. It could well be that if there is one column Country, and GDC has both `country_of_residence` and `country_of_birth` then without additional information you cannot determine which is correct, and hence both should be considered correct.

I propose the experimental config also has a file path to a `harmonization_acceptable_columns.json` that lists for certain source columns what acceptable columns are (and this could be more than one). It should be explicit about whether either is correct or whether a column should be split. For now it should only be: `one_colname : [correct_gdc_colname_given_limited_info_1, correct_gdc_colname_given_limited_info_2]`.

---

## Observations from data analysis

### Country: "Other_specify" -> ???
Source has `"Other_specify"` but gold standard has empty cells for those rows.

**User:** `"Other_specify": ""` because that is the actual value.

### Race: Source has `" White"` (leading space!)
Raw input has `" White"` (with leading space) as distinct from `"White"`. Both map to `"white"`.

**User:** The LLM should make both into `"white"`, so for the mapping it should be `" White"` and `"White"` both to `"white"`. Means that value mapping could be many-to-one.

### Ethnicity: `"Not-Hispanic or Latino"` -> `"not hispanic or latino"`
Hyphen in source disappears in gold standard. Not just casing — character transformation.

**User:** This is just correct, GDC uses the latter.

### Ambiguous column mappings

**User confirmed:**
- `Country` -> `[country_of_birth, country_of_residence]` — both acceptable
- `Age` -> `[age_at_index, age_at_diagnosis]` — both acceptable
- `Tumor_Size_cm` -> `tumor_largest_dimension_diameter` is the only correct one
- `Histologic_type` -> `primary_diagnosis` — the values tell the story, even though schema might suggest `morphology`
- All others: not ambiguous for now

### Numeric columns: identity mapping
BMI, Age, Tumor_Size_cm values are identical between source and gold standard.

**User:** Numbers could change (e.g., age in years vs days). Hence just make a shorthand for identity if the values should be unchanged, otherwise put in the mapping. Do include numeric columns in value mapping.

---

## Final Consolidated Spec

### Deliverables

1. **`calculate_metrics.py`** — CLI script, takes a results directory (or config), compares LLM output against gold standard
2. **`src/evaluation/schemas.py`** — Pydantic models for metrics output
3. **Gold standard files** (in `gold_standard/`):
   - `gold_standard_column_mapping.json` — `{source_col: target_col}` for the 11 subset columns
   - `gold_standard_value_mapping.json` — per-column `{source_val: target_val}`, identity shorthand for numerics
   - `harmonization_acceptable_columns.json` — `{source_col: [acceptable_target_1, ...]}` for ambiguous columns
   - `harmonized_dou_correct_with_index.csv` — gold standard CSV with `Proteomics_Participant_ID` added
   - `dou_with_index.csv` — input CSV with `Proteomics_Participant_ID` added (in `data/`)
4. **Config changes** — `evaluation` block added to all 10 automated configs + new message step for mapping JSONs
5. **Pipeline integration** — hook `calculate_metrics` call into `run_experiment.py` / `run_manual_experiment.py`

### Metrics calculated

| Category | Metrics |
|----------|---------|
| Column mapping | Precision, recall, accuracy, list of correct/wrong/missing/extra columns |
| Per-column values | Accuracy, precision, recall, F1 (multi-class), confusion matrix |
| Per-column errors | Fraction whitespace-only errors, fraction case-only errors, fraction genuine errors |
| Empty cell handling | Metrics reported both with and without empty-empty matches |
| Completeness | Hallucination rate (gold=empty, LLM=filled), omission rate (gold=filled, LLM=empty) |
| Extra columns | Count of LLM columns not in gold standard |
| Metadata | LLM provider, model, timing (from trace.json) |

### Key design decisions

| Decision | Resolution |
|----------|-----------|
| Comparison unit | Column mapping + per-column cell values, reported separately |
| String matching | Exact match, strict |
| Numeric columns | Exact match with optional tolerance/precision |
| Empty cells | Report metrics both with and without empty-empty matches |
| Error categorization | Per column: whitespace-only, case-only, genuine errors |
| Row alignment | Assume ordered; optional index column for verification |
| Column alignment | Via `column_mapping.json`; fallback to name matching with loud warning |
| Auto-trigger | Hook into Python runner + `evaluation` config block |
| Output location | `metrics.json` inside experiment results directory |
| Output format | JSON with Pydantic schema |
| Metadata | Pull in LLM provider/model/timing from trace.json |
| Extra LLM columns | Report count, don't penalize (for now) |
| Schema | Pydantic model in `src/evaluation/schemas.py` |
| One-to-many columns | Code path exists, raises `NotImplementedError` |
| Value mapping | Can be many-to-one (e.g., `" White"` and `"White"` both -> `"white"`) |
| `mapping.json` absent | Loud warning, fallback to column name matching |
| Explicit null vs absent | Treated differently (conscious decision vs forgot) |
| Acceptable columns | `harmonization_acceptable_columns.json` allows multiple correct column targets |

### Example value mappings (gold standard)

**Country:**
```json
{
  "United States": "United States",
  "Ukraine": "Ukraine",
  "Poland": "Poland",
  "Other_specify": ""
}
```

**Ethnicity:**
```json
{
  "Not-Hispanic or Latino": "not hispanic or latino",
  "Hispanic or Latino": "hispanic or latino",
  "Not reported": "not reported"
}
```

**Histologic_Grade_FIGO:**
```json
{
  "FIGO grade 1": "G1",
  "FIGO grade 2": "G2",
  "FIGO grade 3": "G3"
}
```

### Acceptable column mappings

```json
{
  "Country": ["country_of_birth", "country_of_residence"],
  "Age": ["age_at_index", "age_at_diagnosis"]
}
```

### Config evaluation block (to be added to all configs)

```yaml
evaluation:
  gold_standard: "/path/to/harmonized_dou_correct.csv"
  input_file: "/path/to/dou.csv"
  column_mapping_file: "column_mapping.json"
  value_mapping_file: "value_mapping.json"
  acceptable_columns_file: "/path/to/harmonization_acceptable_columns.json"
  index_column: null
  numeric_tolerance: 0.01
  numeric_precision: null
```

### New config message (to be added after "save dou_harmonized.csv" step)

Instructs the LLM to also save:
- `results/column_mapping.json` — `{source_column: target_column}`
- `results/value_mapping.json` — `{source_column: {source_val_1: target_val_1, ...}}`
