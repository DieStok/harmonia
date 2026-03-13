---
title: "feat: Add grouped bar charts to standard evaluation plots"
type: feat
status: completed
date: 2026-03-13
---

# Add Grouped Bar Charts to Standard Evaluation Plots

## Overview

The hand-crafted overview script (`generate_march11_experiment_overview.py`) produces nicer, more readable bar charts than the generic `make_standard_evaluation_plots.py` pipeline. The goal is to add these "grouped by model" bar chart variants to the standard pipeline so they're generated automatically for any experiment batch — not just March 11.

## Problem Statement / Motivation

Currently `make_standard_evaluation_plots.py` generates `global_bar_*` plots where:
- X-axis = `display_label` (one bar per `model | context` combo, flat list)
- Raw metric names as titles/labels
- No value annotations on bars

The overview script's `sns_*` plots are better because:
- X-axis = **model**, with bars **grouped by context** (hue)
- Clean, human-readable titles and axis labels
- Value annotations on top of each bar
- More compact when there are many runs (N models x M contexts → N groups instead of N*M bars)

These are complementary views — the flat `global_bar` is useful for comparing individual runs, while the grouped view is better for comparing models across contexts.

## Proposed Solution

Add a new plot function `plot_grouped_model_bars()` to `plots.py` and call it from `make_standard_evaluation_plots.py` alongside the existing `global_bar_*` plots. This is a **minimal addition** — no refactoring of existing code needed.

## Technical Approach

### Files to change

1. **`src/evaluation/visualization/plots.py`** — Add `plot_grouped_model_bars()` function
2. **`src/evaluation/make_standard_evaluation_plots.py`** — Call the new function after existing global bars

### Step 1: Add `plot_grouped_model_bars()` to `plots.py`

Add a new function that takes the `runs` DataFrame and produces a grouped bar chart. The function signature:

```python
def plot_grouped_model_bars(
    df: pd.DataFrame,
    metric: str,
    model_col: str = "model_label",
    hue_col: str = "context",
    backend: str = "seaborn",
    title: str | None = None,
    contexts_order: list[str] | None = None,
) -> Figure:
```

Key design decisions:
- **`model_col`**: Use `model_label` (from `normalize.py`'s `_run_row()`). This is the canonical model name extracted from the experiment. Falls back gracefully if column missing.
- **`hue_col`**: Use `context` (also from `_run_row()`, populated by `enrich.infer_context()`). Values are `bdikit_context`, `code_context`, `codeact_context`.
- **`contexts_order`**: Optional ordering for the hue. If not provided, sorted alphabetically.
- Add bar value annotations (`.bar_label()` for seaborn, `text` for plotly).
- Set y-axis 0–1.05 range (all target metrics are 0–1 scores).
- Use a fixed color palette mapping context names to consistent colors.

The context values from `enrich.py` use underscores (`bdikit_context`, `code_context`, `codeact_context`). The overview script used hyphens (`bdikit-tools`, `code-context`, `codeact`). The new function should work with whatever values are in the data — no hardcoding.

Seaborn implementation (matches the overview script style):
```python
sns.set_theme(style="whitegrid", font_scale=1.1)
fig, ax = plt.subplots(figsize=(12, 6))
sns.barplot(data=data, x=model_col, y=metric, hue=hue_col,
            hue_order=contexts_order, ax=ax, edgecolor="white")
ax.set_ylim(0, 1.05)
ax.set_ylabel(nice_metric_name)
ax.set_xlabel("Model")
ax.set_title(title or f"{nice_metric_name} by Model and Context")
ax.legend(title="Context")
for container in ax.containers:
    ax.bar_label(container, fmt="%.2f", fontsize=9, padding=3)
```

Plotly implementation: similar grouped bar with `barmode="group"`, text annotations.

### Step 2: Add metric name prettifier

Add a small helper `_pretty_metric_name()` to clean up metric column names for titles:

```python
_METRIC_PRETTY = {
    "column_mapping_accuracy": "Column Mapping Accuracy",
    "avg_value_accuracy_excl_empty": "Value Accuracy (excl empty)",
    "avg_value_accuracy_incl_empty": "Value Accuracy (incl empty)",
    "avg_value_f1_excl_empty": "Value F1 (excl empty)",
    "avg_value_f1_incl_empty": "Value F1 (incl empty)",
}

def _pretty_metric_name(metric: str) -> str:
    return _METRIC_PRETTY.get(metric, metric.replace("_", " ").title())
```

This replaces the raw `avg_value_accuracy_excl_empty` labels with human-readable ones.

### Step 3: Call from `make_standard_evaluation_plots.py`

After the existing step 4 (global bar charts), add:

```python
# 4b. Grouped model bar charts
logger.info("Generating grouped model bar charts...")
for metric in default_metrics:
    if metric in runs.columns:
        try:
            fig = plot_grouped_model_bars(
                runs, metric=metric,
                model_col="model_label",
                hue_col="context",
                backend=args.backend,
            )
            save_figure(
                fig, plots_out / f"grouped_bar_{metric}",
                backend=args.backend, figure_format=args.figure_format, dpi=args.dpi,
            )
            logger.info(f"  grouped_bar_{metric}")
        except Exception as e:
            logger.warning(f"  Skipping grouped bar for {metric}: {e}")
```

Output filenames: `grouped_bar_column_mapping_accuracy.png`, `grouped_bar_avg_value_accuracy_excl_empty.png`, `grouped_bar_avg_value_f1_excl_empty.png`.

### What about the completion heatmap and failure distribution?

The overview script also produces `sns_completion_heatmap` and `sns_failure_distribution`. These are **already available** in the standard pipeline via the `--analysis-report` flag (step 10 in `make_standard_evaluation_plots.py`), which calls `plot_success_failure_heatmap()` and `plot_failure_distribution()` from `plots.py`.

So the grouped bar charts are the only missing piece that needs to be added as a new plot type.

## Acceptance Criteria

- [x] `plot_grouped_model_bars()` added to `src/evaluation/visualization/plots.py`
- [x] `_pretty_metric_name()` helper added to `plots.py`
- [x] `make_standard_evaluation_plots.py` calls new function for each default metric
- [x] Output files: `grouped_bar_column_mapping_accuracy.png`, `grouped_bar_avg_value_accuracy_excl_empty.png`, `grouped_bar_avg_value_f1_excl_empty.png`
- [x] Works with both seaborn and plotly backends
- [x] Existing plots unchanged
- [x] Verify by re-running: `.venv/bin/python src/evaluation/make_standard_evaluation_plots.py --metrics-glob "results/dou_harmonization_*_2026031*/metrics.json" --metrics-glob "results/20260312_*dou_harmonization_*/metrics.json" --out-dir analysis/march11_experiment_plots/march11_seaborn --skip-confusion --skip-cross-compare`

## Sources & References

- Existing grouped bars: `analysis/march11_experiment_plots/generate_march11_experiment_overview.py:293-323` (`seaborn_column_mapping_accuracy`, `seaborn_value_accuracy`)
- Standard pipeline: `src/evaluation/make_standard_evaluation_plots.py:171-190` (step 4, global bars)
- Plot library: `src/evaluation/visualization/plots.py:46-67` (`plot_global_bars`)
- Data normalization: `src/evaluation/visualization/normalize.py:187-249` (`_run_row` — produces `model_label`, `context`, `display_label`)
- Context inference: `src/evaluation/visualization/enrich.py:15-23` (`infer_context`)
