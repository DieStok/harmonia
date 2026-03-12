# Plan: Expand Dashboard with All Visualization Types

**Date:** 2026-03-12
**Priority:** 3 of 3 (after watcher script)
**Brainstorm:** `docs/brainstorms/2026-03-12-unified-visualization-pipeline-brainstorm.md`
**Depends on:** `12_03_2026_1115_enhance_standard_plots_with_failure_modes.md`

## Goal

Add failure analysis, error breakdown, boxplots, confusion matrices, and cross-model comparison to the main dashboard (`src/dashboard/`).

## Current State

The main dashboard has 5 tabs:
1. **Overview** — summary cards, status pie, AG Grid runs table
2. **Metrics** — accuracy bars, cost vs accuracy scatter, heatmap, radar chart
3. **Trace Explorer** — per-run deep-dive with turn accordion
4. **Tokens & Cost** — cost/tokens per model
5. **Comparison** — side-by-side two-run diff

The March 11 dash app (`analysis/march11_experiment_plots/dash_app.py`) has working implementations of failure analysis and error breakdown, but it's a standalone app with hardcoded data.

## Implementation Steps

### Step 1: Add "Failure Analysis" tab to main dashboard

New tab: `src/dashboard/tabs/failure_analysis.py`

Components:
- **Success/failure heatmap** (model x context grid) — port from `analysis/march11_experiment_plots/dash_app.py:fig_success_failure_heatmap()`
- **Failure distribution bar** — port from `analysis/march11_experiment_plots/dash_app.py:fig_failure_bars()`
- **Failure sunburst** — port from `analysis/march11_experiment_plots/dash_app.py:fig_failure_sunburst()`
- **Failure reason explanations** — collapsible text section

Data source: `data_loader.py` already discovers all result directories and knows which have metrics.json. Enhance `get_all_runs()` to also load the analysis report JSON (if available in the results dir) to get failure reasons and problem categories.

Key change to `data_loader.py`:
- Add `load_analysis_report(path)` — try to find and load `analysis_report.json` from the results analysis directory
- Merge failure reasons into the runs DataFrame
- Fallback: if no analysis report, mark runs without metrics as "Unknown failure"

### Step 2: Add "Error Analysis" tab to main dashboard

New tab: `src/dashboard/tabs/error_analysis.py`

Components:
- **Error breakdown stacked bars** (hallucinations/omissions/genuine per run) — port from `analysis/march11_experiment_plots/dash_app.py:fig_error_breakdown()`
- **Error type pie chart** — aggregate across all runs
- **Per-column error table** — AG Grid showing error counts by column by run

Data source: Already available in `get_all_metrics()` which loads metrics.json with error counts.

### Step 3: Enhance "Metrics" tab with boxplots

Add to existing `tabs/metrics.py`:
- **Boxplot section** below existing charts
- Groupable by: model_family, is_local, cost_tier (dropdown selector)
- Metrics: accuracy, F1, precision, recall

Data source: Already in `get_all_metrics()`.

### Step 4: Add confusion matrices to Trace Explorer

Enhance `tabs/trace_explorer.py`:
- When viewing a single run, show confusion matrices for each column below the turn accordion
- Use plotly heatmaps (already implemented in `visualization/plots.py:plot_confusion()`)
- Add a column selector dropdown to view one at a time (avoid overwhelming the page)

Data source: Load from `metrics.json` which contains confusion matrix data per column.

### Step 5: Add cross-model comparison to Comparison tab

Enhance `tabs/comparison.py`:
- New section: "Per-row comparison" below existing per-column bars
- Shows color-coded heatmap of correct/incorrect/empty per row per model
- Column selector dropdown

Data source: Requires `row_values.csv` files. Use `build_row_values_table()` from `visualization/normalize.py`.

### Step 6: Update navigation and tab ordering

Update `app.py`:
- Tab order: Overview, Metrics, Failure Analysis, Error Analysis, Trace Explorer, Tokens & Cost, Comparison
- Add click-through from failure analysis heatmap → trace explorer (for successful runs) or → log viewer (for failed runs)

## Files to Create

| File | Purpose |
|------|---------|
| `src/dashboard/tabs/failure_analysis.py` | Failure analysis tab |
| `src/dashboard/tabs/error_analysis.py` | Error breakdown tab |

## Files to Modify

| File | Change |
|------|--------|
| `src/dashboard/app.py` | Add new tabs, update tab order, add callbacks |
| `src/dashboard/data_loader.py` | Load analysis report, merge failure reasons into runs |
| `src/dashboard/tabs/metrics.py` | Add boxplot section |
| `src/dashboard/tabs/trace_explorer.py` | Add confusion matrices |
| `src/dashboard/tabs/comparison.py` | Add cross-model comparison heatmaps |

## Testing

- Start dashboard with results that include both successful and failed runs
- Verify each new tab renders without errors
- Test with no analysis report (graceful degradation)
- Test with only failed runs (failure tab works, metrics tab shows empty state)
- Test click-through navigation from failure heatmap to trace explorer
- Check performance with many runs (lazy-load confusion matrices)
