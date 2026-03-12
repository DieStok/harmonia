# Plan: Enhance Standard Plots with Failure Mode Visualizations

**Date:** 2026-03-12
**Priority:** 1 of 3 (start here)
**Brainstorm:** `docs/brainstorms/2026-03-12-unified-visualization-pipeline-brainstorm.md`

## Goal

Add failure mode visualizations to `make_standard_evaluation_plots.py` and the visualization CLI, using the log analysis CLI's JSON output as the data source for failed runs.

## Current State

- `make_standard_evaluation_plots.py` generates: global bars, heatmap, confusion matrices, cross-model comparison, boxplots — but ONLY for runs with `metrics.json` (successful runs)
- `analysis/march11_experiment_plots/generate_march11_experiment_overview.py` has working failure plots (success/failure heatmap, failure bars, failure sunburst, error breakdown) but with hardcoded failure reasons
- Log analysis CLI (`read_and_analyze_logs_and_traces_cli.py --json`) outputs structured `AnalysisReport` with per-run `RunAnalysis` objects containing: run_id, experiment_name, llm_model, llm_provider, has_metrics, has_trace, problems list

## Implementation Steps

### Step 1: Add failure mode plot functions to `visualization/plots.py`

Add 4 new functions (ported from `analysis/march11_experiment_plots/generate_march11_experiment_overview.py` and `analysis/march11_experiment_plots/dash_app.py`):

1. **`plot_success_failure_heatmap(all_runs_df, row_col, col_col, backend)`**
   - Model x context grid showing OK/FAIL with hover details
   - Seaborn: annotated heatmap with custom colormap
   - Plotly: go.Heatmap with hover text

2. **`plot_failure_distribution(all_runs_df, backend)`**
   - Horizontal bar chart of failure reason counts
   - Only includes runs where `has_output == False`

3. **`plot_failure_sunburst(all_runs_df, backend)`**
   - Plotly only (sunburst is plotly-native); for seaborn backend, generate a grouped bar instead
   - Hierarchy: failure_reason → model → context

4. **`plot_error_breakdown(runs_df, backend)`**
   - Stacked bar: hallucinations / omissions / genuine errors per successful run
   - Data comes from existing metrics (already in `runs` table from `build_tables()`)

### Step 2: Create `visualization/failure_io.py` — bridge between log analysis JSON and visualization tables

New module with:
- `load_analysis_report(path) -> dict` — load and validate the log analysis JSON
- `build_all_runs_table(analysis_report, metrics_tables) -> pd.DataFrame` — merge failed runs (from analysis report) with successful runs (from metrics tables) into a unified DataFrame with columns: `run_id, experiment_name, model, context, has_output, failure_reason, column_mapping_accuracy, avg_value_accuracy, ...`
- Infer `model` and `context` from experiment_name using existing `enrich.py` functions
- Map `problems[].problem_id` to a human-readable `failure_reason` string (use the primary/most-severe problem)

### Step 3: Add `--analysis-report` flag to `make_standard_evaluation_plots.py`

```python
parser.add_argument("--analysis-report",
    help="Path to log analysis JSON (from read_and_analyze_logs_and_traces_cli.py --json)")
```

New section after existing plots (section 9, before manifest):
```
# 9. Failure mode plots (if analysis report provided)
if args.analysis_report:
    report = load_analysis_report(args.analysis_report)
    all_runs = build_all_runs_table(report, tables)
    # Generate: success/failure heatmap, failure distribution, failure sunburst, error breakdown
```

When `--analysis-report` is NOT provided, skip failure plots but still generate error breakdown (which only needs metrics data).

### Step 4: Add `failure-analysis` command to `visualize_metrics_cli.py`

New subcommand:
```
visualize_metrics_cli.py failure-analysis \
    --analysis-report analysis_report.json \
    --metrics-glob "results/*/metrics.json" \
    --out-dir analysis/visualizations
```

Generates all 4 failure mode plots. Also add `--analysis-report` to the existing `compare` command so `compare` generates the full suite including failures.

### Step 5: Add error breakdown to `compare` command

The `compare` command currently generates: global bars, heatmaps, confusion, boxplots, cross-compare. Add error breakdown (stacked bar of hallucinations/omissions/genuine errors) — this doesn't need the analysis report, just the metrics.

## Files to Modify

| File | Change |
|------|--------|
| `src/evaluation/visualization/plots.py` | Add 4 new plot functions |
| `src/evaluation/visualization/failure_io.py` | **New file** — bridge between log analysis JSON and viz tables |
| `src/evaluation/make_standard_evaluation_plots.py` | Add `--analysis-report` flag and failure plot section |
| `src/evaluation/visualize_metrics_cli.py` | Add `failure-analysis` command, enhance `compare` |

## Testing

- Run log analysis CLI with `--json > /tmp/test_report.json`
- Run enhanced `make_standard_evaluation_plots.py --analysis-report /tmp/test_report.json --metrics-glob "results/*/metrics.json" --out-dir /tmp/test_plots`
- Verify all plots generated (existing + new failure plots)
- Test without `--analysis-report` to ensure backward compatibility
- Test CLI `failure-analysis` subcommand
