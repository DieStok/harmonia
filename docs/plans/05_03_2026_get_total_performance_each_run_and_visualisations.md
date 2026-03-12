# Implementation Plan: Per-Row Values Table + Confusion Matrices + Standard Plots Script

## Context

The Harmonia evaluation pipeline currently stores per-row comparison data only partially: `metrics.json` records misclassifications (errors) with row indices, but not correct predictions. The confusion matrix in `metrics.json` and `confusion.csv` stores aggregated counts only. To build a cross-model comparison heatmap (showing each model's prediction for each sample, colour-coded by correctness), we need complete per-row data.

**Goal:** Emit a `row_values.csv` per run at metrics calculation time, add a cross-model comparison heatmap to the visualization library, generate per-run confusion matrices as standard output, and wrap it all in a `make_standard_evaluation_plots.py` script.

---

## File Inventory

All paths relative to repo root: `harmonia_metadata_agent/analysis/dstoker/harmonia/`

| File | Action |
|------|--------|
| `src/evaluation/metrics.py` | **Modify** — collect per-row data in `calculate_column_value_metrics()`, return it alongside existing `ColumnValueMetrics` |
| `src/evaluation/schemas.py` | **Modify** — add `RowComparison` schema, add `row_comparisons` field to `ColumnValueMetrics` |
| `calculate_metrics.py` | **Modify** — emit `row_values.csv` from the new per-row data after metrics calculation |
| `src/evaluation/visualization/normalize.py` | **Modify** — add `build_row_values_table()` that discovers and concatenates `row_values.csv` files across runs |
| `src/evaluation/visualization/plots.py` | **Modify** — add `plot_cross_model_comparison()` function |
| `src/evaluation/visualize_metrics_cli.py` | **Modify** — add `cross-compare` subcommand, modify `cmd_confusion` to support all-runs mode |
| `src/evaluation/make_standard_evaluation_plots.py` | **Create** — orchestration script for standard post-experiment plots |

---

## Step 1: Add `RowComparison` schema to `schemas.py`

**File:** `src/evaluation/schemas.py`

Add a new Pydantic model after `Misclassification`:

```python
class RowComparison(BaseModel):
    """Per-row comparison result for a single cell."""
    row_index: int
    gold_value: str          # normalized (stripped, empty→"")
    predicted_value: str     # normalized (stripped, empty→"")
    classification: str      # "correct", "empty_empty", "hallucination", "omission", "error"
    error_type: str | None   # None unless classification=="error"; then whitespace_only/case_only/etc.
```

Add field to `ColumnValueMetrics`:

```python
class ColumnValueMetrics(BaseModel):
    ...
    row_comparisons: list[RowComparison] = Field(
        default_factory=list,
        description="Complete per-row comparison results (all cells, not just errors)"
    )
```

Using `default_factory=list` ensures backward compatibility — existing `metrics.json` files without this field will deserialize with an empty list.

---

## Step 2: Collect per-row data in `metrics.py`

**File:** `src/evaluation/metrics.py`, function `calculate_column_value_metrics()` (line 172)

Import `RowComparison` alongside the other schema imports (line 14-22).

Inside the per-row loop (lines 221-282), build a `row_comparisons` list. For each row `i`, after determining the classification (correct_filled / empty_empty / hallucination / omission / error), append a `RowComparison`:

```python
row_comparisons: list[RowComparison] = []

for i, (gold_val, llm_val) in enumerate(zip(gold_values, llm_values)):
    # ... existing classification logic (lines 222-282) ...

    # Determine classification and error_type
    if gold_empty and llm_empty:
        classification = "empty_empty"
        error_type_val = None
    elif gold_empty and not llm_empty:
        classification = "hallucination"
        error_type_val = None
    elif not gold_empty and llm_empty:
        classification = "omission"
        error_type_val = None
    elif gold_normalized == llm_normalized:
        classification = "correct"
        error_type_val = None
    else:
        # Check numeric tolerance (existing logic)
        if <numeric_tolerance_match>:
            classification = "correct"
            error_type_val = None
        else:
            classification = "error"
            error_type_val = error_type  # already computed

    row_comparisons.append(RowComparison(
        row_index=i,
        gold_value=gold_normalized,
        predicted_value=llm_normalized,
        classification=classification,
        error_type=error_type_val,
    ))
```

This will be integrated into the existing if/elif/else chain at lines 232-275 — not duplicating it, but adding `RowComparison` construction alongside the existing counter increments and misclassification appends.

Add `row_comparisons=row_comparisons` to the `ColumnValueMetrics(...)` return at line 372.

---

## Step 3: Emit `row_values.csv` in `calculate_metrics.py`

**File:** `calculate_metrics.py`, after line 258 (after `metrics_path.write_text(...)`)

```python
# Emit per-row comparison data
import csv
row_values_path = results_dir / "row_values.csv"
with open(row_values_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "column_name", "source_column_name", "row_index",
        "gold_value", "predicted_value", "classification", "error_type"
    ])
    for col_name, col_metrics in validated_result.column_values.items():
        for rc in col_metrics.row_comparisons:
            writer.writerow([
                col_name,
                col_metrics.source_column_name,
                rc.row_index,
                rc.gold_value,
                rc.predicted_value,
                rc.classification,
                rc.error_type or "",
            ])
logger.info(f"✓ Row values saved to: {row_values_path}")
```

Note: `row_comparisons` is **not** serialized into `metrics.json` — it would bloat the JSON significantly (104 rows × 11 columns = 1,144 entries per run). The `default_factory=list` in the schema means `model_dump_json()` will include an empty `row_comparisons: []` by default. To avoid this, we'll exclude it from JSON serialization:

Change line 258 from:
```python
metrics_path.write_text(validated_result.model_dump_json(indent=2))
```
to:
```python
metrics_path.write_text(validated_result.model_dump_json(indent=2, exclude={"column_values": {"__all__": {"row_comparisons"}}}))
```

This keeps `metrics.json` clean and unchanged, while `row_values.csv` is the canonical per-row output.

---

## Step 4: Backfill utility for existing runs

**File:** `calculate_metrics.py` — add a `--backfill-row-values` flag

When this flag is set and `--results-dir` points to a directory with an existing `metrics.json` but no `row_values.csv`, re-run metrics calculation (using paths from the existing metrics.json's `gold_standard_file` and `llm_output_file` fields, plus `column_mapping.json`) and emit only the `row_values.csv`.

Implementation: add to `main()`:
```python
parser.add_argument(
    "--backfill-row-values",
    action="store_true",
    help="Regenerate row_values.csv from existing results (requires gold standard + LLM output still accessible)"
)
```

When active:
1. Load existing `metrics.json` to get `gold_standard_file`, `llm_output_file`
2. Load `column_mapping.json` from results dir (for gold column mapping) and reconstruct the gold_column_mapping
3. Re-call `calculate_all_metrics()` with same args
4. Emit `row_values.csv` only (skip overwriting `metrics.json`)

Actually — cleaner approach: add a standalone function `backfill_row_values(results_dir)` that:
1. Reads the config YAML path from `.experiment_id` → `config_path`
2. Loads the config to get `evaluation.gold_standard`, `evaluation.gold_column_mapping`, `evaluation.index_column`
3. Re-runs `calculate_all_metrics()`
4. Writes only `row_values.csv`

This function will also be called from `make_standard_evaluation_plots.py`.

---

## Step 5: Add `build_row_values_table()` to `normalize.py`

**File:** `src/evaluation/visualization/normalize.py`

Add function:

```python
def build_row_values_table(
    runs_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Discover and concatenate row_values.csv files from each run's results_dir.
    Merges in run metadata (model_label, context, display_label).

    Returns long-format DataFrame with columns:
        run_id, model_label, context, display_label, column_name,
        source_column_name, row_index, gold_value, predicted_value,
        classification, error_type
    """
    frames = []
    for _, run in runs_df.iterrows():
        rv_path = Path(run["results_dir"]) / "row_values.csv"
        if not rv_path.exists():
            continue
        df = pd.read_csv(rv_path, dtype=str)
        df["run_id"] = run["run_id"]
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    row_values = pd.concat(frames, ignore_index=True)

    # Merge run metadata
    merge_cols = ["run_id", "model_label", "context", "display_label"]
    merge_cols = [c for c in merge_cols if c in runs_df.columns]
    row_values = row_values.merge(
        runs_df[merge_cols],
        on="run_id",
        how="left",
    )
    return row_values
```

Also update `build_tables()` to optionally include `row_values` in its return dict:

```python
def build_tables(bundle, labels_df=None):
    ...  # existing code
    tables = {
        "runs": runs_df,
        "column_mapping": mapping_df,
        "column_values": columns_df,
        "confusion": confusion_df,
    }
    # Add row_values if available
    if not runs_df.empty:
        row_values_df = build_row_values_table(runs_df)
        if not row_values_df.empty:
            tables["row_values"] = row_values_df
    return tables
```

---

## Step 6: Add `plot_cross_model_comparison()` to `plots.py`

**File:** `src/evaluation/visualization/plots.py`

```python
def plot_cross_model_comparison(
    row_values_df: pd.DataFrame,
    column_name: str,
    backend: str = "seaborn",
    title: str | None = None,
    row_filter: list[int] | None = None,        # Filter by row_index
    id_filter: list[str] | None = None,          # Filter by identifier values
    id_column: str | None = None,                # Column in row_values containing identifiers
    errors_only: bool = False,                    # Show only rows with at least one error
    max_rows: int | None = None,
):
```

**Seaborn implementation:**
1. Pivot `row_values_df` filtered to `column_name`:
   - Rows = `row_index` (+ gold_value for labeling)
   - Columns = `display_label` (one per model/context combo)
   - Values = `predicted_value`
2. Build a parallel boolean matrix: `is_correct` (1 if `classification == "correct" or "empty_empty"`, 0 otherwise)
3. Create a `matplotlib` figure with `ax.table()` or a heatmap where:
   - First column: gold value (grey background)
   - Remaining columns: predicted values
   - Cell colors: green (#c6efce) for correct, red (#ffc7ce) for incorrect, light grey for empty_empty
   - Text annotations: the actual values
4. Handle `errors_only`: filter to rows where any model has `classification` not in `{"correct", "empty_empty"}`
5. Handle `row_filter` / `id_filter` subsetting

**Plotly implementation:**
- Use `plotly.figure_factory.create_annotated_heatmap` or `px.imshow` with custom text
- Green/red color scale based on correctness
- Hover shows gold vs predicted

The function returns a figure object (same pattern as other plot functions).

---

## Step 7: Add `cross-compare` CLI subcommand

**File:** `src/evaluation/visualize_metrics_cli.py`

Add `cmd_cross_compare(args)`:

```python
def cmd_cross_compare(args):
    tables, paths, skipped = _load_tables(args)
    out_dir = Path(args.out_dir) / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    backend = "plotly" if args.interactive else args.backend

    row_values = tables.get("row_values")
    if row_values is None or row_values.empty:
        raise SystemExit("No row_values data available. Run calculate_metrics.py first (or with --backfill-row-values).")

    columns = [args.column] if args.column else sorted(row_values["column_name"].unique())

    for col in columns:
        fig = plot_cross_model_comparison(
            row_values,
            column_name=col,
            backend=backend,
            errors_only=args.errors_only,
            max_rows=args.max_rows,
            title=f"Cross-model comparison: {col}",
        )
        save_figure(fig, out_dir / f"cross_compare_{col}", backend=backend,
                    figure_format=args.figure_format, dpi=args.dpi)

    write_manifest(Path(args.out_dir), {
        "command": "cross-compare",
        "columns": columns,
        "errors_only": args.errors_only,
        "backend": backend,
        "input_count": len(paths),
        "skipped": skipped,
    })
```

Register in `build_parser()`:

```python
p_cross = sub.add_parser("cross-compare", help="Cross-model comparison heatmap per column")
_common_parser(p_cross)
p_cross.add_argument("--column", help="Specific column to compare (default: all)")
p_cross.add_argument("--errors-only", action="store_true", help="Show only rows with at least one error")
p_cross.add_argument("--max-rows", type=int, help="Maximum rows to display")
p_cross.set_defaults(func=cmd_cross_compare)
```

---

## Step 8: Enhance `cmd_confusion` for all-runs mode

**File:** `src/evaluation/visualize_metrics_cli.py`, function `cmd_confusion` (line 173)

Currently generates one confusion matrix for one run+column. Add `--all-runs` flag:

When `--all-runs` is set:
- Iterate all unique run_ids in confusion_df
- For each run, look up model_label from runs_df to create subfolder name
- For each column in that run, generate a confusion matrix
- Skip columns with `>max_unique_values` unique expected values (default 25)
- Save to: `plots/confusion_matrices/<model_subfolder>/confusion_<run_id>_<context>_<column>.png`

```python
p_conf.add_argument("--all-runs", action="store_true", help="Generate confusion matrices for all runs and columns")
p_conf.add_argument("--max-unique-values", type=int, default=25,
                     help="Skip columns with more unique values than this (default: 25)")
```

---

## Step 9: Create `make_standard_evaluation_plots.py`

**File:** `src/evaluation/make_standard_evaluation_plots.py`

Orchestration script that calls existing CLI functions to produce all standard plots after experiments.

```python
#!/usr/bin/env python3
"""
Generate the standard set of evaluation plots for completed experiments.
Intended to be run after calculate_metrics.py, or as a batch post-processing step.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.visualization.aggregate import heatmap_matrix
from evaluation.visualization.io import discover_metrics_files, load_metrics_bundle
from evaluation.visualization.normalize import build_tables
from evaluation.visualization.plots import (
    plot_confusion,
    plot_cross_model_comparison,
    plot_global_bars,
    plot_heatmap,
    save_figure,
)
from evaluation.visualization.report import write_manifest


def main():
    parser = argparse.ArgumentParser(description="Generate standard evaluation plots")
    parser.add_argument("--metrics-files", nargs="*", default=[])
    parser.add_argument("--metrics-glob", action="append", default=[])
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--backend", default="seaborn", choices=["seaborn", "plotly"])
    parser.add_argument("--figure-format", default="png")
    parser.add_argument("--dpi", type=int, default=160)
    parser.add_argument("--max-unique-values", type=int, default=25,
                        help="Skip confusion matrices for columns with more unique values")
    parser.add_argument("--backfill-row-values", action="store_true",
                        help="Regenerate missing row_values.csv files before plotting")
    args = parser.parse_args()

    # 1. Discover and load metrics
    paths = discover_metrics_files(args.metrics_files, args.metrics_glob)
    loaded, skipped = load_metrics_bundle(paths)
    tables = build_tables(loaded)

    runs = tables["runs"]
    base_out = Path(args.out_dir)
    plots_out = base_out / "plots"
    tables_out = base_out / "tables"

    # 2. Backfill row_values.csv if requested
    if args.backfill_row_values:
        _backfill_missing_row_values(runs)
        # Rebuild tables to pick up new row_values
        tables = build_tables(loaded)

    # 3. Save data tables
    tables_out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(tables_out / f"{name}.csv", index=False)

    # 4. Global bar charts
    for metric in ["column_mapping_accuracy", "avg_value_accuracy_excl_empty", "avg_value_f1_excl_empty"]:
        if metric in runs.columns:
            fig = plot_global_bars(runs, metric=metric, x_col="display_label",
                                   hue_col="context", backend=args.backend)
            save_figure(fig, plots_out / f"global_bar_{metric}",
                       backend=args.backend, figure_format=args.figure_format, dpi=args.dpi)

    # 5. Heatmap
    col_df = tables["column_values"]
    matrix = heatmap_matrix(col_df, metric="accuracy_excl_empty", row_key="display_label")
    if not matrix.empty:
        fig = plot_heatmap(matrix, backend=args.backend)
        save_figure(fig, plots_out / f"heatmap_accuracy_excl_empty",
                   backend=args.backend, figure_format=args.figure_format, dpi=args.dpi)

    # 6. Confusion matrices — per model subfolder
    confusion_df = tables["confusion"]
    if not confusion_df.empty:
        _generate_all_confusion_matrices(
            confusion_df, runs, plots_out,
            args.backend, args.figure_format, args.dpi,
            args.max_unique_values,
        )

    # 7. Cross-model comparison heatmaps (if row_values available)
    row_values = tables.get("row_values")
    if row_values is not None and not row_values.empty:
        cross_out = plots_out / "cross_model_comparison"
        for col in sorted(row_values["column_name"].unique()):
            fig = plot_cross_model_comparison(row_values, column_name=col, backend=args.backend)
            save_figure(fig, cross_out / f"cross_compare_{col}",
                       backend=args.backend, figure_format=args.figure_format, dpi=args.dpi)

    write_manifest(base_out, {...})


def _generate_all_confusion_matrices(confusion_df, runs_df, plots_out, backend, fmt, dpi, max_unique):
    """Generate confusion matrices for every run × column, organized by model subfolder."""
    for _, run in runs_df.iterrows():
        run_id = run["run_id"]
        model_label = run.get("model_label", run_id)
        context = run.get("context", "")
        # Create safe folder name
        folder_name = model_label.replace("/", "_").replace(" ", "_")
        model_dir = plots_out / "confusion_matrices" / folder_name

        columns = confusion_df[confusion_df["run_id"] == run_id]["column_name"].unique()
        for col in columns:
            # Skip high-cardinality columns
            n_unique = confusion_df[
                (confusion_df["run_id"] == run_id) & (confusion_df["column_name"] == col)
            ]["expected_value"].nunique()
            if n_unique > max_unique:
                continue

            fig = plot_confusion(confusion_df, run_id=run_id, column_name=col, backend=backend)
            fname = f"confusion_{run_id}_{context}_{col}"
            save_figure(fig, model_dir / fname, backend=backend, figure_format=fmt, dpi=dpi)
```

---

## Execution Order

1. **Step 1** (`schemas.py`) — add `RowComparison` model + field on `ColumnValueMetrics`
2. **Step 2** (`metrics.py`) — collect `row_comparisons` in the per-row loop
3. **Step 3** (`calculate_metrics.py`) — emit `row_values.csv`, exclude `row_comparisons` from JSON
4. **Step 4** (`calculate_metrics.py`) — add `--backfill-row-values` flag + backfill function
5. **Step 5** (`normalize.py`) — add `build_row_values_table()`, update `build_tables()`
6. **Step 6** (`plots.py`) — add `plot_cross_model_comparison()`
7. **Step 7** (`visualize_metrics_cli.py`) — add `cross-compare` subcommand
8. **Step 8** (`visualize_metrics_cli.py`) — add `--all-runs` to `cmd_confusion`
9. **Step 9** (`make_standard_evaluation_plots.py`) — create orchestration script
10. **Step 10** — backfill existing 7 runs, then generate plots for current analysis directory

---

## Verification

1. **Unit test: `row_values.csv` emission**
   - Run `calculate_metrics.py --results-dir <existing_run> --config <config>` on one run
   - Verify `row_values.csv` exists with 104 × 11 = 1,144 rows (header + data)
   - Verify columns: `column_name, source_column_name, row_index, gold_value, predicted_value, classification, error_type`
   - Verify `metrics.json` does NOT contain `row_comparisons` (excluded)

2. **Backfill test**
   - Run `calculate_metrics.py --results-dir <run_without_row_values> --backfill-row-values`
   - Verify `row_values.csv` appears, `metrics.json` unchanged

3. **Cross-model heatmap test**
   - Run `visualize_metrics_cli.py cross-compare --metrics-glob "results/*/metrics.json" --column primary_diagnosis --out-dir /tmp/test`
   - Verify PNG/HTML generated in `/tmp/test/plots/`

4. **All-runs confusion test**
   - Run `visualize_metrics_cli.py confusion --all-runs --metrics-glob "results/*/metrics.json" --out-dir /tmp/test`
   - Verify subfolders per model with confusion matrix PNGs

5. **Full pipeline test**
   - Run `make_standard_evaluation_plots.py --metrics-glob "results/*/metrics.json" --out-dir analysis/test_output --backfill-row-values`
   - Verify all expected outputs: bar charts, heatmaps, confusion matrices in subfolders, cross-model heatmaps

6. **Generate final plots for current analysis**
   - Run against the 7 successful runs, output to `analysis/plots_latest_successful_20260302_1843/`
