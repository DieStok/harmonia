# Brainstorm: Unified Visualization & Post-Experiment Pipeline

**Date:** 2026-03-12
**Status:** Complete

## What We're Building

Three interconnected improvements to the experiment evaluation flow:

1. **Enhanced standard plots** — Add failure mode visualizations (success/failure heatmap, failure distribution bars, failure sunburst, error breakdown) to `make_standard_evaluation_plots.py` and the visualization CLI, accepting log analysis JSON as input alongside metrics.json files.

2. **Post-experiment orchestrator** — A watcher sbatch script that auto-triggers after all experiment runs finish, chains log analysis → metrics calculation → plot generation into a single automated pipeline.

3. **Dashboard expansion** — Add failure analysis tab, error breakdown tab, boxplots, confusion matrices, and cross-model comparison to the main dashboard (`src/dashboard/`).

## Why This Approach

Currently the flow is manual and fragmented:
- Experiments finish → user asks Claude to gather results → Claude runs log analysis CLI → Claude runs metrics → Claude generates plots → user reviews
- The March 11 experiment overview script (`analysis/march11_experiment_plots/generate_march11_experiment_overview.py`) proved that failure mode visualizations are valuable, but it's a one-off script with hardcoded failure reasons
- The log analysis CLI already produces structured JSON output (`--json` flag) with per-run `RunAnalysis` objects containing problems, model info, run status — this is the missing bridge

The approach connects existing tools into an automated pipeline rather than building new analysis infrastructure.

## Key Decisions

1. **Data source for failure modes:** Use the log analysis CLI's `--json` output (`AnalysisReport` with `RunAnalysis` objects) as the structured input for failure visualizations. No hardcoded failure reasons.

2. **Integration point:** `make_standard_evaluation_plots.py` gets a `--analysis-report` flag to accept the JSON. Failed runs are visualized alongside successful runs.

3. **Automation via sbatch dependency:** `sbatch --dependency=afterany:$JOB_ID` chains a watcher job that runs the full pipeline automatically.

4. **Dashboard gets all visualizations:** All 4 new visualization types (failure analysis, error breakdown, boxplots/confusion, cross-model comparison) will be added to the main dashboard.

5. **Priority order:** Enhanced standard plots first → watcher script → dashboard expansion.

## Open Questions (Resolved)

- **Q: How to discover failed runs?** → Use log analysis CLI's `--json` output, which already cross-references SLURM logs with results dirs and categorizes failures using the YAML taxonomy.
- **Q: Where do failure mode plots go in the standard pipeline?** → New section in `make_standard_evaluation_plots.py` after the existing plot sections, gated by `--analysis-report` flag (skip if not provided).
