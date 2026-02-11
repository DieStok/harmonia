# Implementation Plan: Metadata Harmonization Metrics Calculation

**Date:** 2026-02-10
**Planning document:** `my_instructions/10_02_2026_planning_metrics_calculation_one_metadata_table.md`
**Status:** Ready for implementation

---

## Overview

Implement a metrics calculation pipeline that evaluates LLM metadata harmonization experiments by comparing their output against gold-standard data. The pipeline has three parts:

1. Gold standard reference files (JSON + CSV)
2. A `calculate_metrics.py` CLI script with Pydantic-validated JSON output
3. Integration into the existing experiment runner pipeline

---

## Part 1: Gold Standard Reference Files

### 1.1 Create `gold_standard_column_mapping.json`

**Location:** `.../raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/gold_standard_column_mapping.json`

```json
{
  "Country": "country_of_birth",
  "Histologic_Grade_FIGO": "tumor_grade",
  "Histologic_type": "primary_diagnosis",
  "FIGO_stage": "figo_stage",
  "BMI": "bmi",
  "Age": "age_at_index",
  "Race": "race",
  "Ethnicity": "ethnicity",
  "Gender": "gender",
  "Tumor_Focality": "tumor_focality",
  "Tumor_Size_cm": "tumor_largest_dimension_diameter"
}
```

### 1.2 Create `gold_standard_value_mapping.json`

**Location:** `.../raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/gold_standard_value_mapping.json`

Structure: `{ source_column: { source_value: target_value } }` with `"__identity__"` shorthand for columns where values pass through unchanged.

```json
{
  "Country": {
    "United States": "United States",
    "Ukraine": "Ukraine",
    "Poland": "Poland",
    "Other_specify": ""
  },
  "Histologic_Grade_FIGO": {
    "FIGO grade 1": "G1",
    "FIGO grade 2": "G2",
    "FIGO grade 3": "G3"
  },
  "Histologic_type": {
    "Endometrioid": "Endometrioid carcinoma",
    "Serous": "Serous cystadenocarcinoma",
    "Carcinosarcoma": "Carcinosarcoma, NOS",
    "Clear cell": "Clear cell adenocarcinoma, NOS"
  },
  "FIGO_stage": {
    "IA": "Stage IA",
    "IB": "Stage IB",
    "II": "Stage II",
    "IIIA": "Stage IIIA",
    "IIIB": "Stage IIIB",
    "IIIC1": "Stage IIIC1",
    "IIIC2": "Stage IIIC2",
    "IVB": "Stage IVB"
  },
  "BMI": "__identity__",
  "Age": "__identity__",
  "Race": {
    "White": "white",
    " White": "white",
    "Asian": "asian",
    "Black or African American": "black or african american",
    "Not Reported": "not reported"
  },
  "Ethnicity": {
    "Not-Hispanic or Latino": "not hispanic or latino",
    "Hispanic or Latino": "hispanic or latino",
    "Not reported": "not reported"
  },
  "Gender": {
    "Female": "female"
  },
  "Tumor_Focality": {
    "Unifocal": "Unifocal",
    "Multifocal": "Multifocal"
  },
  "Tumor_Size_cm": "__identity__"
}
```

### 1.3 Create `harmonization_acceptable_columns.json`

**Location:** `.../raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/harmonization_acceptable_columns.json`

Only columns with genuinely ambiguous GDC mappings:

```json
{
  "Country": ["country_of_birth", "country_of_residence"],
  "Age": ["age_at_index", "age_at_diagnosis"]
}
```

### 1.4 Create `dou_with_index.csv`

**Location:** `.../raw/datasets_harmonia/one_metadata_table_gdc_schema/data/dou_with_index.csv`

**How:** Python script that:
1. Reads `dou-ucec-discovery.csv`, extracts first 104 rows
2. Takes `Proteomics_Participant_ID` column + the existing 17 columns from `dou.csv`
3. Writes with `Proteomics_Participant_ID` as the first column

### 1.5 Create `harmonized_dou_correct_with_index.csv`

**Location:** `.../raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/harmonized_dou_correct_with_index.csv`

**How:** Same Python script:
1. Reads the same 104 `Proteomics_Participant_ID` values from the discovery CSV
2. Prepends them to `harmonized_dou_correct.csv`

---

## Part 2: Pydantic Schemas

### 2.1 Create `src/evaluation/__init__.py`

Empty init file to make `evaluation` a proper package.

### 2.2 Create `src/evaluation/schemas.py`

Pydantic models defining the metrics output structure. All models use `BaseModel`.

#### Models (top-down):

```
MetricsResult                    # Top-level: the full metrics.json
├── ExperimentMetadata           # experiment name, timestamp, LLM info, timing
├── ColumnMappingMetrics         # schema-matching metrics
│   └── ColumnMappingDetail      # per-column: source, expected, actual, is_correct, is_acceptable
├── dict[str, ColumnValueMetrics]  # per-column value metrics
│   └── ColumnValueMetrics
│       ├── accuracy, precision, recall, f1 (with and without empty-empty)
│       ├── hallucination_rate, omission_rate
│       ├── ErrorCategorization  # fraction whitespace-only, case-only, genuine
│       ├── confusion_matrix: dict[str, dict[str, int]]  # sparse: {actual: {predicted: count}}
│       └── misclassifications: list[Misclassification]
│           └── Misclassification  # row_index, expected, actual, error_type
└── OverallSummary               # aggregate stats across all columns
```

#### Key fields in `MetricsResult`:

```python
class MetricsResult(BaseModel):
    schema_version: str = "1.0"
    experiment_name: str
    timestamp: str
    llm_provider: str
    llm_model: str
    timing_seconds: Optional[float]

    column_mapping: ColumnMappingMetrics
    column_values: dict[str, ColumnValueMetrics]
    extra_columns_count: int
    extra_columns: list[str]

    # Logging/diagnostic info
    gold_standard_file: str
    llm_output_file: str
    column_mapping_file_found: bool
    value_mapping_file_found: bool
```

#### Key fields in `ColumnMappingMetrics`:

```python
class ColumnMappingMetrics(BaseModel):
    total_expected: int           # columns in gold standard
    correct: int                  # exact match or acceptable match
    wrong: int                    # mapped to wrong GDC column
    missing: int                  # absent from mapping entirely
    explicitly_null: int          # mapped to null (conscious decision)
    precision: float              # correct / (correct + wrong + explicitly_null applied to mapped cols)
    recall: float                 # correct / total_expected
    accuracy: float               # correct / total_expected
    details: list[ColumnMappingDetail]
```

#### Key fields in `ColumnValueMetrics`:

```python
class ColumnValueMetrics(BaseModel):
    column_name: str              # gold standard column name
    source_column_name: str       # original source column name
    total_cells: int

    # With empty-empty counted as correct (default view)
    accuracy_incl_empty: float
    precision_macro_incl_empty: float
    recall_macro_incl_empty: float
    f1_macro_incl_empty: float

    # Without empty-empty (strict view)
    accuracy_excl_empty: float
    precision_macro_excl_empty: float
    recall_macro_excl_empty: float
    f1_macro_excl_empty: float

    # Completeness
    hallucination_count: int      # gold=empty, LLM=filled
    hallucination_rate: float
    omission_count: int           # gold=filled, LLM=empty
    omission_rate: float
    empty_empty_count: int        # both empty (matched trivially)

    # Error categorization
    error_categorization: ErrorCategorization

    # Detailed
    confusion_matrix: dict[str, dict[str, int]]   # sparse
    misclassifications: list[Misclassification]
```

#### `ErrorCategorization`:

```python
class ErrorCategorization(BaseModel):
    total_errors: int
    whitespace_only: int          # error disappears after strip()
    case_only: int                # error disappears after lower()
    whitespace_and_case: int      # error disappears after strip().lower()
    genuine: int                  # still wrong after normalization

    whitespace_only_fraction: float
    case_only_fraction: float
    whitespace_and_case_fraction: float
    genuine_fraction: float
```

---

## Part 3: Core Metrics Calculation

### 3.1 Create `src/evaluation/metrics.py`

The core computation module. Functions, not a class — keeps it simple and testable.

#### Function: `calculate_column_mapping_metrics`

```python
def calculate_column_mapping_metrics(
    llm_column_mapping: dict[str, str | None],     # from column_mapping.json
    gold_column_mapping: dict[str, str],            # from gold_standard_column_mapping.json
    acceptable_columns: dict[str, list[str]] | None,  # from harmonization_acceptable_columns.json
) -> ColumnMappingMetrics:
```

**Logic:**
1. For each source column in `gold_column_mapping`:
   - If source column absent from `llm_column_mapping` → **missing**
   - If source column mapped to `null` in `llm_column_mapping` → **explicitly_null**
   - If mapped target matches gold target → **correct**
   - If mapped target is in `acceptable_columns[source]` → **correct** (acceptable)
   - If mapped target is a list (one-to-many) → **raise NotImplementedError**
   - Otherwise → **wrong**
2. Compute precision = correct / (correct + wrong)
3. Compute recall = correct / total_expected
4. Compute accuracy = correct / total_expected

#### Function: `calculate_column_value_metrics`

```python
def calculate_column_value_metrics(
    gold_values: list[str],          # gold standard column values (all rows)
    llm_values: list[str],           # LLM output column values (all rows)
    column_name: str,
    source_column_name: str,
) -> ColumnValueMetrics:
```

**Logic:**
1. Iterate row-by-row, comparing `gold_values[i]` vs `llm_values[i]`
2. Classify each cell:
   - Both empty → `empty_empty`
   - Gold empty, LLM filled → `hallucination`
   - Gold filled, LLM empty → `omission`
   - Both filled, match → `correct`
   - Both filled, no match → `error` → subcategorize:
     - `strip()` fixes it → `whitespace_only`
     - `lower()` fixes it → `case_only`
     - `strip().lower()` fixes it → `whitespace_and_case`
     - Otherwise → `genuine`
3. Build confusion matrix (sparse dict)
4. Compute multi-class precision/recall/F1 (macro-averaged):
   - Get set of all unique classes (union of gold and LLM values)
   - For each class: TP, FP, FN
   - Macro-average across classes
5. Compute both incl_empty and excl_empty variants
6. Record misclassifications list

#### Function: `calculate_all_metrics`

```python
def calculate_all_metrics(
    gold_standard_csv: Path,
    llm_output_csv: Path,
    gold_column_mapping: dict[str, str],
    llm_column_mapping: dict[str, str | None] | None,   # None = fallback mode
    gold_value_mapping: dict | None,                      # for reference/logging
    acceptable_columns: dict[str, list[str]] | None,
    index_column: str | None = None,
    numeric_tolerance: float | None = None,
    trace_json: dict | None = None,                       # for metadata extraction
) -> MetricsResult:
```

**Logic:**
1. Load both CSVs as pandas DataFrames
2. If `index_column` provided: verify alignment by checking index values match, sort both by index
3. If `llm_column_mapping` is None:
   - Log loud warning
   - Fall back: match gold standard column names directly against LLM output columns
4. Calculate column mapping metrics
5. For each gold standard column that has a corresponding LLM column (via mapping):
   - Extract both columns as lists
   - Call `calculate_column_value_metrics()`
6. For columns where the LLM mapping is wrong but a column exists:
   - Still evaluate values (report "column name wrong, values X% correct")
7. Detect extra columns (in LLM output but not in gold standard mapping targets)
8. Extract metadata from `trace.json` if provided (provider, model, timing)
9. Assemble and return `MetricsResult`

### 3.2 Handle one-to-many column mappings

In `calculate_column_mapping_metrics`, if a mapping value is a list:
```python
if isinstance(mapped_target, list):
    raise NotImplementedError(
        f"One-to-many column mapping not yet supported: {source_col} -> {mapped_target}"
    )
```

---

## Part 4: CLI Script

### 4.1 Create `calculate_metrics.py`

**Location:** `.../harmonia/calculate_metrics.py` (same level as `run_experiment.py`)

**CLI arguments:**

```
python calculate_metrics.py --results-dir <path>
                            [--config <path>]           # alternative: read paths from config
                            [--gold-standard <path>]    # override
                            [--gold-column-mapping <path>]
                            [--gold-value-mapping <path>]
                            [--acceptable-columns <path>]
                            [--llm-output <filename>]   # default: dou_harmonized.csv
                            [--index-column <name>]
                            [--numeric-tolerance <float>]
                            [--verbose]
```

**Logic:**

1. If `--config` provided: load the YAML, read `evaluation` block for all paths
2. Override any paths with explicit CLI args
3. Determine `results_dir` (required)
4. Look for files in `results_dir`:
   - `column_mapping.json` (LLM-produced)
   - `value_mapping.json` (LLM-produced)
   - `dou_harmonized.csv` (or `--llm-output` override)
   - `trace.json` (for metadata)
5. Load gold standard files from paths in config/CLI
6. Call `calculate_all_metrics()`
7. Validate result with Pydantic
8. Write `metrics.json` to `results_dir`
9. Print summary to stdout

**Logging:** Use Python `logging` module, level configurable via `--verbose`.
Log to both console and `results_dir/metrics_calculation.log`.

Logged info includes:
- Columns found in input and gold standard
- Unique values per column for both
- Values present in one but not the other
- Missing files (column_mapping.json, value_mapping.json)
- Row count comparison
- Index column alignment check results

---

## Part 5: Config Changes

### 5.1 Add `EvaluationConfig` dataclass to `src/automation/config.py`

```python
@dataclass
class EvaluationConfig:
    """Evaluation configuration for metrics calculation."""
    gold_standard: Optional[str] = None
    input_file: Optional[str] = None
    gold_column_mapping: Optional[str] = None
    gold_value_mapping: Optional[str] = None
    acceptable_columns_file: Optional[str] = None
    column_mapping_file: str = "column_mapping.json"
    value_mapping_file: str = "value_mapping.json"
    index_column: Optional[str] = None
    numeric_tolerance: Optional[float] = None
    numeric_precision: Optional[int] = None
```

Add to `ExperimentConfig`:
```python
evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
```

Update `ExperimentConfig.from_dict()` to parse the `evaluation` block.

### 5.2 Update all 10 automated config YAMLs

Each config file gets two changes:

#### Change A: Add `evaluation` block

```yaml
evaluation:
  gold_standard: "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/harmonized_dou_correct.csv"
  input_file: "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/data/dou.csv"
  gold_column_mapping: "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/gold_standard_column_mapping.json"
  gold_value_mapping: "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/gold_standard_value_mapping.json"
  acceptable_columns_file: "/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/gold_standard/harmonization_acceptable_columns.json"
  column_mapping_file: "column_mapping.json"
  value_mapping_file: "value_mapping.json"
  index_column: null
  numeric_tolerance: null
```

Note: inside the Apptainer container, paths starting with `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/` are mounted at `/data/` (based on the existing message content referencing `/data/one_metadata_table_gdc_schema/data/dou.csv`). The `calculate_metrics.py` script runs **outside** the container, so it uses the full host paths. The evaluation block should use full host paths.

#### Change B: Add new message step after "save dou_harmonized.csv"

Insert after the existing message 6 (save harmonized CSV), before the "show comparison" message:

```yaml
  - content: |
      Now save the column mapping you used as "results/column_mapping.json".
      The format should be a JSON object where each key is the original source
      column name and each value is the GDC column name it was mapped to.
      For example: {"Country": "country_of_birth", "Age": "age_at_index", ...}
      Include all columns, even those that were not mapped (set value to null).

      Also save the value mapping as "results/value_mapping.json".
      The format should be a JSON object where each key is the original source
      column name, and each value is another object mapping each unique source
      value to its harmonized target value.
      For example: {"Histologic_Grade_FIGO": {"FIGO grade 1": "G1", "FIGO grade 2": "G2"}, ...}
      For columns where values were not changed, use the string "__identity__" instead of
      the mapping object.
    wait_seconds: 300
    decision_mode: auto_accept
```

#### Change C: Update `save_artifacts` list

```yaml
output:
  base_dir: "./results"
  save_artifacts:
    - "dou_harmonized.csv"
    - "column_mapping.json"
    - "value_mapping.json"
```

### 5.3 List of all 10 config files to update

All in `.../experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/`:

1. `dou_harmonization_anyllm_devstral.yaml`
2. `dou_harmonization_anyllm_openrouter.yaml`
3. `dou_harmonization_devstral.yaml`
4. `dou_harmonization_devstral-small.yaml`
5. `dou_harmonization_glm-4.5-air.yaml`
6. `dou_harmonization_kimi-k2.yaml`
7. `dou_harmonization_mimo-v2-flash.yaml`
8. `dou_harmonization_nemotron-3-nano.yaml`
9. `dou_harmonization_olmo3.yaml`
10. `dou_harmonization_qwen3-coder.yaml`

---

## Part 6: Pipeline Integration

### 6.1 Modify `run_experiment.py`

After line 138 (`output_dir = await runner.run(...)`), add:

```python
# Calculate metrics if evaluation config is present
if config.evaluation and config.evaluation.gold_standard:
    print(f"\nCalculating metrics...")
    try:
        from evaluation.metrics import calculate_all_metrics
        from evaluation.schemas import MetricsResult
        import json

        # Load gold standard files
        gold_column_mapping = _load_json(config.evaluation.gold_column_mapping)
        gold_value_mapping = _load_json(config.evaluation.gold_value_mapping)
        acceptable_columns = _load_json(config.evaluation.acceptable_columns_file)

        # Load LLM-produced mappings (if they exist)
        llm_column_mapping_path = output_dir / config.evaluation.column_mapping_file
        llm_column_mapping = _load_json(llm_column_mapping_path) if llm_column_mapping_path.exists() else None

        # Load trace.json for metadata
        trace_path = output_dir / "trace.json"
        trace_data = _load_json(trace_path) if trace_path.exists() else None

        # Find LLM output CSV
        llm_output = output_dir / "dou_harmonized.csv"

        if llm_output.exists():
            result = calculate_all_metrics(
                gold_standard_csv=Path(config.evaluation.gold_standard),
                llm_output_csv=llm_output,
                gold_column_mapping=gold_column_mapping,
                llm_column_mapping=llm_column_mapping,
                gold_value_mapping=gold_value_mapping,
                acceptable_columns=acceptable_columns,
                index_column=config.evaluation.index_column,
                numeric_tolerance=config.evaluation.numeric_tolerance,
                trace_json=trace_data,
            )

            metrics_path = output_dir / "metrics.json"
            metrics_path.write_text(result.model_dump_json(indent=2))
            print(f"  Metrics saved to: {metrics_path}")
        else:
            print(f"  Warning: LLM output CSV not found at {llm_output}")
            print(f"  Skipping metrics calculation.")
    except Exception as e:
        print(f"  Error calculating metrics: {e}")
        # Don't fail the whole experiment just because metrics failed
```

Add a helper:
```python
def _load_json(path) -> dict | None:
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        return None
    import json
    return json.loads(path.read_text())
```

### 6.2 Modify `run_manual_experiment.py`

Similar integration after `run_monitor()` returns (line 369-374). The output_dir is already available. Add the same metrics calculation block in the `try` body, after `run_monitor` returns 0.

### 6.3 Update output summary prints

In both scripts, after metrics calculation, add:
```python
print(f"  - metrics.json: Harmonization metrics")
```

---

## Part 7: File Structure Summary

### New files to create:

```
src/evaluation/
├── __init__.py                          # Package init, exports key names
├── schemas.py                           # Pydantic models (MetricsResult, etc.)
└── metrics.py                           # Core calculation functions

calculate_metrics.py                     # CLI entry point (standalone use)

raw/datasets_harmonia/one_metadata_table_gdc_schema/
├── data/
│   └── dou_with_index.csv               # dou.csv + Proteomics_Participant_ID
└── gold_standard/
    ├── gold_standard_column_mapping.json
    ├── gold_standard_value_mapping.json
    ├── harmonization_acceptable_columns.json
    └── harmonized_dou_correct_with_index.csv
```

### Files to modify:

```
src/automation/config.py                 # Add EvaluationConfig dataclass
run_experiment.py                        # Add post-experiment metrics call
run_manual_experiment.py                 # Add post-experiment metrics call

experiments/.../configs/automated/
├── dou_harmonization_anyllm_devstral.yaml      # + evaluation block + mapping message
├── dou_harmonization_anyllm_openrouter.yaml    # + evaluation block + mapping message
├── dou_harmonization_devstral.yaml             # + evaluation block + mapping message
├── dou_harmonization_devstral-small.yaml       # + evaluation block + mapping message
├── dou_harmonization_glm-4.5-air.yaml          # + evaluation block + mapping message
├── dou_harmonization_kimi-k2.yaml              # + evaluation block + mapping message
├── dou_harmonization_mimo-v2-flash.yaml        # + evaluation block + mapping message
├── dou_harmonization_nemotron-3-nano.yaml      # + evaluation block + mapping message
├── dou_harmonization_olmo3.yaml                # + evaluation block + mapping message
└── dou_harmonization_qwen3-coder.yaml          # + evaluation block + mapping message
```

---

## Implementation Order

The implementation should proceed in this order to minimize dependencies:

| Step | What | Why first |
|------|------|-----------|
| 1 | Gold standard JSON files (1.1, 1.2, 1.3) | No code dependencies, pure data |
| 2 | Index CSV files (1.4, 1.5) | Pure data, one-time script |
| 3 | Pydantic schemas (2.1, 2.2) | Defines the contract for everything else |
| 4 | Core metrics functions (3.1, 3.2) | Depends on schemas |
| 5 | CLI script (4.1) | Depends on metrics + schemas |
| 6 | Config dataclass update (5.1) | Small change, needed for integration |
| 7 | Config YAML updates (5.2, 5.3) | Depends on config dataclass |
| 8 | Pipeline integration (6.1, 6.2, 6.3) | Depends on everything above |

---

## Dependencies

- **Python standard library:** `csv`, `logging`, `argparse`, `pathlib`
- **pydantic:** For schema validation (already used in the project? — verify; if not, add to environment)
- **orjson** For fast json processing. (already used in the project? — verify; if not, add to environment)
- **pandas:** For CSV loading and alignment (already available in the Apptainer environment)
- **No new external dependencies** beyond pydantic (if not already present)

---

## Testing Strategy

Before running a full experiment, test the metrics script standalone:

```bash
# Test with an existing experiment output (if dou_harmonized.csv exists)
python calculate_metrics.py \
  --results-dir results/dou_harmonization_devstral_20260115_111823 \
  --gold-standard .../gold_standard/harmonized_dou_correct.csv \
  --gold-column-mapping .../gold_standard/gold_standard_column_mapping.json \
  --verbose

# The old results won't have column_mapping.json, so the fallback path will be exercised
```

For a more complete test, manually create a `column_mapping.json` and `value_mapping.json` in one of the old result directories, then run the script to verify full functionality.

---

## Future Work (out of scope for this implementation)

- `visualize_performance_metrics.py` — aggregates `metrics.json` across experiments, produces comparison charts
- One-to-many column mapping support (code path exists, raises `NotImplementedError`)
- Schema compliance rate (requires list of all valid GDC values per column)
- Support for multiple gold standard files per experiment
