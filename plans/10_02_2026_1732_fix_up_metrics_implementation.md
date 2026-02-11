# Fix-Up Plan: Metrics Implementation Corrections

**Date:** 2026-02-10 17:32
**Parent plan:** `10_02_2026_implementing_metadata_harmonization_metrics_calculation.md`
**Status:** Ready for implementation

---

## Overview

Seven targeted fixes to the metrics implementation based on code review. Changes touch schemas, core metrics logic, CLI summary output, and one deprecation fix.

---

## Fix 1: `value_mapping_file_found` always `False`

**Problem:** [metrics.py:617](../src/evaluation/metrics.py#L617) hardcodes `value_mapping_file_found=False`. The field always reports that no value mapping was found, even when one was loaded.

**Files to modify:**
- `src/evaluation/metrics.py`

**Changes:**

1. Add a `value_mapping_file_found: bool = False` parameter to `calculate_all_metrics()`:

```python
def calculate_all_metrics(
    ...
    gold_value_mapping: dict | None = None,
    ...
    value_mapping_file_found: bool = False,    # NEW
) -> MetricsResult:
```

2. Pass through to `MetricsResult` constructor:

```python
value_mapping_file_found=value_mapping_file_found,
```

3. Update callers to pass the correct value:

**Files to modify (callers):**
- `calculate_metrics.py` — after loading `llm_value_mapping_file`, pass `value_mapping_file_found=llm_value_mapping_file.exists()`
- `run_experiment.py` — pass `value_mapping_file_found=(output_dir / config.evaluation.value_mapping_file).exists()`
- `run_manual_experiment.py` — same as above

---

## Fix 2: Implement `numeric_tolerance`

**Problem:** The `numeric_tolerance` parameter is threaded through CLI and config but never used. Numeric columns (BMI, Age, Tumor_Size_cm) are compared as strings, so `"23.5"` vs `"23.50"` is a "genuine error."

**Files to modify:**
- `src/evaluation/metrics.py`

**Changes:**

1. Add `numeric_tolerance: float | None = None` parameter to `calculate_column_value_metrics()`:

```python
def calculate_column_value_metrics(
    gold_values: list[str],
    llm_values: list[str],
    column_name: str,
    source_column_name: str,
    numeric_tolerance: float | None = None,    # NEW
) -> ColumnValueMetrics:
```

2. In the row-by-row comparison loop, after both values are confirmed non-empty and the string comparison (`gold_normalized == llm_normalized`) fails, add a numeric comparison attempt before classifying as an error:

```python
elif gold_normalized == llm_normalized:
    correct_filled += 1
else:
    # Try numeric comparison if tolerance is set
    if numeric_tolerance is not None:
        try:
            gold_num = float(gold_normalized)
            llm_num = float(llm_normalized)
            if abs(gold_num - llm_num) <= numeric_tolerance:
                correct_filled += 1
                # Update confusion matrix and continue
                ...
                continue
        except (ValueError, TypeError):
            pass  # Not numeric, fall through to error categorization

    # Misclassification — categorize the error
    error_type = _categorize_error(gold_val, llm_val)
    ...
```

3. Pass `numeric_tolerance` from `calculate_all_metrics()` to each `calculate_column_value_metrics()` call:

```python
metrics = calculate_column_value_metrics(
    gold_values=gold_values,
    llm_values=llm_values,
    column_name=gold_target,
    source_column_name=source_col,
    numeric_tolerance=numeric_tolerance,    # NEW
)
```

**Note:** The `for` loop body uses index tracking, so the numeric-match path needs to update the confusion matrix and `continue` to the next iteration, skipping the error categorization block. Use the existing loop structure — the simplest approach is to restructure the comparison block slightly to avoid deep nesting.

---

## Fix 3: Compose `ExperimentMetadata` into `MetricsResult` (Option A)

**Problem:** `ExperimentMetadata` is defined but never used. `MetricsResult` duplicates its fields inline.

**Files to modify:**
- `src/evaluation/schemas.py`
- `src/evaluation/metrics.py`
- `calculate_metrics.py`

**Changes in `schemas.py`:**

Replace the five flat fields in `MetricsResult`:

```python
# REMOVE these from MetricsResult:
experiment_name: str
timestamp: str
llm_provider: Optional[str]
llm_model: Optional[str]
timing_seconds: Optional[float]

# ADD this instead:
metadata: ExperimentMetadata = Field(..., description="Experiment metadata")
```

`ExperimentMetadata` already has the exact same fields, so no changes needed to that class.

**Changes in `metrics.py`:**

Update `calculate_all_metrics()` to construct `ExperimentMetadata` and pass it to `MetricsResult`:

```python
from .schemas import (
    ...
    ExperimentMetadata,    # ADD to import
)

# In calculate_all_metrics(), replace:
#   result = MetricsResult(
#       experiment_name=experiment_name,
#       timestamp=...,
#       llm_provider=llm_provider,
#       ...
# With:
metadata = ExperimentMetadata(
    experiment_name=experiment_name,
    timestamp=datetime.now(timezone.utc).isoformat(),
    llm_provider=llm_provider,
    llm_model=llm_model,
    timing_seconds=timing_seconds,
)

result = MetricsResult(
    metadata=metadata,
    column_mapping=column_mapping_metrics,
    ...
)
```

**Changes in `calculate_metrics.py`:**

Update all field accesses from flat to nested:

```python
# Before:                              # After:
result.experiment_name          →  result.metadata.experiment_name
result.timestamp                →  result.metadata.timestamp
result.llm_provider             →  result.metadata.llm_provider
result.llm_model                →  result.metadata.llm_model
```

Specific lines to update:
- Line 262: `result.experiment_name` → `result.metadata.experiment_name`
- Line 263: `result.timestamp` → `result.metadata.timestamp`
- Line 265: `result.llm_provider` → `result.metadata.llm_provider`
- Line 266: `result.llm_provider` / `result.llm_model` → `result.metadata.llm_provider` / `result.metadata.llm_model`

**No changes needed in `run_experiment.py` or `run_manual_experiment.py`** — they only call `result.model_dump_json()` and don't access individual fields.

**JSON output change:** The `metrics.json` output will nest metadata under a `"metadata"` key instead of having flat top-level fields. This is a schema change (bump `schema_version` to `"1.1"`).

---

## Fix 4: Dual precision metrics for column mapping (incl/excl null)

**Problem:** The plan specified `precision = correct / (correct + wrong + explicitly_null)` but the implementation uses `correct / (correct + wrong)`. Both perspectives are useful.

**Files to modify:**
- `src/evaluation/schemas.py`
- `src/evaluation/metrics.py`
- `calculate_metrics.py`

**Changes in `schemas.py`:**

In `ColumnMappingMetrics`, rename `precision` and add a second precision field:

```python
class ColumnMappingMetrics(BaseModel):
    ...
    # RENAME existing:
    precision_excl_null: float = Field(
        ...,
        description="Precision excluding null mappings: correct / (correct + wrong)"
    )
    # ADD new:
    precision_incl_null: float = Field(
        ...,
        description="Precision including null mappings: correct / (correct + wrong + explicitly_null)"
    )
    recall: float = Field(..., description="Recall: correct / total_expected")
    accuracy: float = Field(..., description="Accuracy: correct / total_expected")
    ...
```

**Changes in `metrics.py`:**

In `calculate_column_mapping_metrics()`, compute both:

```python
# Precision excluding null (current behavior)
mapped_count_excl_null = correct + wrong
precision_excl_null = correct / mapped_count_excl_null if mapped_count_excl_null > 0 else 0.0

# Precision including null (plan formula)
mapped_count_incl_null = correct + wrong + explicitly_null
precision_incl_null = correct / mapped_count_incl_null if mapped_count_incl_null > 0 else 0.0
```

Pass both to `ColumnMappingMetrics` constructor.

**Changes in `calculate_metrics.py`:**

Update the summary print block to show both:

```python
logger.info(f"Precision (excl null): {result.column_mapping.precision_excl_null:.2%}")
logger.info(f"Precision (incl null): {result.column_mapping.precision_incl_null:.2%}")
```

---

## Fix 5: Rename confusion matrix description

**Problem:** The schema description says `{actual_value: {predicted_value: count}}` which is ambiguous — "actual" could mean either the gold standard or what the LLM actually produced.

**Files to modify:**
- `src/evaluation/schemas.py`

**Change:**

```python
# Before:
confusion_matrix: dict[str, dict[str, int]] = Field(
    ...,
    description="Sparse confusion matrix: {actual_value: {predicted_value: count}}"
)

# After:
confusion_matrix: dict[str, dict[str, int]] = Field(
    ...,
    description="Sparse confusion matrix: {expected_value: {predicted_value: count}}"
)
```

---

## Fix 6: Guard against mismatched CSV row counts with index column

**Problem:** When `index_column` is set and CSVs have different row counts, the code sorts by index then truncates — which may discard valid rows rather than aligning by index.

**Files to modify:**
- `src/evaluation/metrics.py`

**Changes:**

In `calculate_all_metrics()`, when `index_column` is provided, use an inner join on the index column instead of sort + truncate:

```python
if index_column:
    if index_column in gold_df.columns and index_column in llm_df.columns:
        # Merge on index column to align rows
        gold_df = gold_df.set_index(index_column)
        llm_df = llm_df.set_index(index_column)

        # Find common indices
        common_idx = gold_df.index.intersection(llm_df.index)

        if len(common_idx) < len(gold_df):
            logger.warning(
                f"Only {len(common_idx)} of {len(gold_df)} gold standard rows "
                f"found in LLM output (by index column '{index_column}')"
            )
        if len(common_idx) < len(llm_df):
            logger.warning(
                f"LLM output has {len(llm_df) - len(common_idx)} extra rows "
                f"not in gold standard"
            )

        gold_df = gold_df.loc[common_idx].sort_index().reset_index()
        llm_df = llm_df.loc[common_idx].sort_index().reset_index()

        logger.info(f"Aligned {len(common_idx)} rows by index column '{index_column}'")
```

Also remove the later per-column truncation logic (lines 491-499) when `index_column` was used, since alignment is already handled. Keep the truncation as a fallback when no index column is provided.

---

## Fix 7: Replace deprecated `datetime.utcnow()`

**Problem:** `datetime.utcnow()` is deprecated since Python 3.12.

**Files to modify:**
- `src/evaluation/metrics.py`

**Change:**

```python
# Before (line 605):
timestamp=datetime.utcnow().isoformat() + "Z",

# After:
from datetime import datetime, timezone    # update import at top of file

timestamp=datetime.now(timezone.utc).isoformat(),
```

Note: `datetime.now(timezone.utc).isoformat()` produces `2026-02-10T17:32:00+00:00` (with offset) rather than `2026-02-10T17:32:00Z`. Both are valid ISO 8601. If the trailing `Z` format is preferred for consistency, use:

```python
timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
```

Pick whichever format you prefer — both are parseable.

---

## Implementation Order

| Step | Fix | Dependencies |
|------|-----|-------------|
| 1 | Fix 7: `datetime.utcnow()` | None |
| 2 | Fix 5: Rename confusion matrix description | None |
| 3 | Fix 3: Compose `ExperimentMetadata` | None (schema change) |
| 4 | Fix 4: Dual precision metrics | None |
| 5 | Fix 1: `value_mapping_file_found` | None |
| 6 | Fix 2: `numeric_tolerance` | None |
| 7 | Fix 6: Index-based row alignment | None |

All fixes are independent — they can be applied in any order. The order above groups the simpler changes first.

---

## Files Modified Summary

| File | Fixes Applied |
|------|--------------|
| `src/evaluation/schemas.py` | 3, 4, 5 |
| `src/evaluation/metrics.py` | 1, 2, 3, 6, 7 |
| `calculate_metrics.py` | 1, 3, 4 |
| `run_experiment.py` | 1 |
| `run_manual_experiment.py` | 1 |

---

## Schema Version

Bump `schema_version` default in `MetricsResult` from `"1.0"` to `"1.1"` to reflect the structural changes (metadata nesting, dual precision fields).

---

## Testing

After implementation, test with:

```bash
# Re-run against an existing experiment output
python calculate_metrics.py \
  --results-dir results/<any_existing_experiment_dir> \
  --gold-standard .../gold_standard/harmonized_dou_correct.csv \
  --gold-column-mapping .../gold_standard/gold_standard_column_mapping.json \
  --verbose

# Verify metrics.json has:
# - "metadata" nested object (not flat fields)
# - "precision_excl_null" and "precision_incl_null" in column_mapping
# - "value_mapping_file_found" reflects actual file presence
# - confusion_matrix description updated in schema
# - timestamp format correct (no deprecation warning)
```
