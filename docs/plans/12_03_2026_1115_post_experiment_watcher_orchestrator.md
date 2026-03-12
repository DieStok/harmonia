# Plan: Post-Experiment Watcher/Orchestrator Script

**Date:** 2026-03-12
**Priority:** 2 of 3 (after enhanced standard plots)
**Brainstorm:** `docs/brainstorms/2026-03-12-unified-visualization-pipeline-brainstorm.md`
**Depends on:** `12_03_2026_1115_enhance_standard_plots_with_failure_modes.md`

## Goal

Create an sbatch watcher script that automatically triggers after all experiment runs complete, running the full analysis pipeline: log analysis → metrics calculation → plot generation.

## Current State

- Experiments are launched via sbatch array jobs or individual sbatch submissions
- After completion, the user manually asks Claude to: gather results, run log analysis, calculate metrics, generate plots
- All the individual tools exist and work, they're just not chained together

## Design

### Architecture

```
User launches experiment:
  sbatch --array=1-N experiment_batch.sh
  ↓
  Returns BATCH_JOB_ID
  ↓
  Automatically submit watcher:
  sbatch --dependency=afterany:$BATCH_JOB_ID watcher.sh --experiment-name <name>
  ↓
  When all array tasks finish (success or fail), watcher runs:
    1. Log/trace analysis CLI → analysis_report.json
    2. calculate_metrics.py for each run with output → metrics.json + row_values.csv
    3. make_standard_evaluation_plots.py --analysis-report → dated output dir
    4. Summary notification (optional: write status file)
```

### Implementation Steps

#### Step 1: Create `run_post_experiment_analysis.sh` (the watcher sbatch script)

Location: `harmonia_metadata_agent/analysis/dstoker/harmonia/run_post_experiment_analysis.sh`

```bash
#!/bin/bash
#SBATCH --job-name=harmonia_post_analysis
#SBATCH --account=compgen
#SBATCH --time=00:30:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/post_analysis_%j.out
#SBATCH --error=logs/post_analysis_%j.err

# Arguments: --experiment-name <pattern> [--output-dir <dir>]
```

Script flow:
1. Parse arguments (experiment name pattern, optional output dir)
2. Run log analysis: `.venv/bin/python code_development_tools_agents/.../read_and_analyze_logs_and_traces_cli.py --experiment "$EXPERIMENT_NAME" --json > "$OUTPUT_DIR/analysis_report.json"`
3. For each run with output (has results dir + harmonized CSV but no metrics.json): run `calculate_metrics.py`
4. Run enhanced `make_standard_evaluation_plots.py --analysis-report "$OUTPUT_DIR/analysis_report.json" --metrics-glob "results/*${EXPERIMENT_NAME}*/metrics.json" --out-dir "$OUTPUT_DIR"`
5. Write a summary status file: `$OUTPUT_DIR/analysis_complete.json` with timestamp, counts, paths

#### Step 2: Create helper wrapper `launch_experiment.sh`

Convenience script that:
1. Submits the experiment batch job
2. Captures the BATCH_JOB_ID
3. Automatically submits the watcher with `--dependency=afterany:$BATCH_JOB_ID`
4. Prints both job IDs for tracking

```bash
./launch_experiment.sh --config configs/automated/my_experiment.yaml
# Output:
#   Submitted experiment batch: 12345 (6 tasks)
#   Submitted post-analysis watcher: 12346 (depends on 12345)
#   Results will appear in: results/analysis_20260312_1430/
```

#### Step 3: Handle edge cases

- **Partial completion:** Some array tasks may fail (SLURM-level failure). The watcher runs `afterany` (not `afterok`), so it triggers regardless. The log analysis handles this.
- **No successful runs:** If all runs failed, the watcher still generates failure mode plots (just no accuracy plots).
- **Output directory naming:** `results/analysis_<experiment_name>_<YYYYMMDD_HHMM>/` with subdirs `plots/`, `tables/`, `analysis_report.json`
- **Timeout:** Watcher gets 30 min by default. If metrics calculation for many runs takes longer, user can override.

## Files to Create

| File | Purpose |
|------|---------|
| `run_post_experiment_analysis.sh` | Watcher sbatch script |
| `launch_experiment.sh` | Convenience wrapper that submits experiment + watcher |

## Files to Modify

| File | Change |
|------|--------|
| `calculate_metrics.py` | Ensure it can be called in batch mode (loop over directories) — may already work |

## Testing

- Submit a small test experiment (1-2 runs)
- Verify watcher triggers after completion
- Check output directory contains: analysis_report.json, plots/, tables/
- Test with all-fail scenario (should still produce failure plots)
- Test manual invocation of watcher (without sbatch dependency, for re-runs)
