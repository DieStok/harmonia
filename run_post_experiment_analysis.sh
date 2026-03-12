#!/bin/bash
# =============================================================================
# Harmonia Post-Experiment Analysis Watcher
# =============================================================================
# Runs the full analysis pipeline after experiment jobs complete:
#   1. Log/trace analysis → analysis_report.json
#   2. calculate_metrics.py for each run (if not already calculated)
#   3. make_standard_evaluation_plots.py with failure mode integration
#   4. Summary status file
#
# Usage:
#   # Submit as dependency after experiment batch job:
#   sbatch --dependency=afterany:$BATCH_JOB_ID run_post_experiment_analysis.sh \
#       --experiment-name "my_experiment"
#
#   # Manual re-run (no sbatch dependency needed):
#   bash run_post_experiment_analysis.sh --experiment-name "my_experiment"
#
#   # With custom output directory:
#   bash run_post_experiment_analysis.sh --experiment-name "my_experiment" \
#       --output-dir results/analysis_custom/
# =============================================================================

#SBATCH --job-name=harmonia_post_analysis
#SBATCH --account=compgen
#SBATCH --time=00:30:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/post_analysis_%j.out
#SBATCH --error=logs/post_analysis_%j.err

set -euo pipefail

# =============================================================================
# Parse Arguments
# =============================================================================

EXPERIMENT_NAME=""
OUTPUT_DIR=""
METRICS_BACKEND="seaborn"
NUM_RUNS=50
VERBOSE=""

usage() {
    echo "Usage: $0 --experiment-name <pattern> [OPTIONS]"
    echo ""
    echo "Required:"
    echo "  --experiment-name <pattern>   Experiment name pattern for log analysis"
    echo ""
    echo "Optional:"
    echo "  --output-dir <dir>            Output directory (default: analysis/analysis_<experiment>_<timestamp>/)"
    echo "  --backend <seaborn|plotly>     Plot backend (default: seaborn)"
    echo "  --num-runs <N>                Number of recent runs to analyze (default: 50)"
    echo "  --verbose                     Enable verbose output"
    echo "  -h, --help                    Show this help message"
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --experiment-name)
            EXPERIMENT_NAME="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --backend)
            METRICS_BACKEND="$2"
            shift 2
            ;;
        --num-runs)
            NUM_RUNS="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE="--verbose"
            shift
            ;;
        -h|--help)
            usage 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1"
            usage 1
            ;;
    esac
done

if [[ -z "$EXPERIMENT_NAME" ]]; then
    echo "ERROR: --experiment-name is required"
    usage 1
fi

# =============================================================================
# Environment Setup
# =============================================================================

# Determine project directory (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON=".venv/bin/python"
LOG_ANALYSIS_CLI="code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py"
CALCULATE_METRICS="calculate_metrics.py"
MAKE_PLOTS="src/evaluation/make_standard_evaluation_plots.py"

# Set up output directory
if [[ -z "$OUTPUT_DIR" ]]; then
    TIMESTAMP=$(date -u +%Y%m%d_%H%M)
    OUTPUT_DIR="analysis/analysis_${EXPERIMENT_NAME}_${TIMESTAMP}"
fi

mkdir -p "$OUTPUT_DIR/plots" "$OUTPUT_DIR/tables"
mkdir -p logs

echo "=============================================="
echo "Harmonia Post-Experiment Analysis"
echo "=============================================="
echo ""
echo "Experiment:  $EXPERIMENT_NAME"
echo "Output dir:  $OUTPUT_DIR"
echo "Backend:     $METRICS_BACKEND"
echo "Num runs:    $NUM_RUNS"
echo "Date:        $(date)"
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    echo "SLURM Job:   $SLURM_JOB_ID"
fi
echo ""

# Track overall status
STEP_ERRORS=0

# =============================================================================
# Step 1: Log/Trace Analysis → analysis_report.json
# =============================================================================

echo "--- Step 1: Log/Trace Analysis ---"
echo ""

ANALYSIS_REPORT="$OUTPUT_DIR/analysis_report.json"

if $PYTHON "$LOG_ANALYSIS_CLI" \
    --experiment "$EXPERIMENT_NAME" \
    --num-runs "$NUM_RUNS" \
    --json $VERBOSE > "$ANALYSIS_REPORT" 2>"$OUTPUT_DIR/log_analysis_stderr.log"; then
    echo "✓ Analysis report written to: $ANALYSIS_REPORT"

    # Quick summary from the report
    RUN_COUNT=$($PYTHON -c "
import json, sys
report = json.load(open('$ANALYSIS_REPORT'))
runs = report.get('runs', [])
has_metrics = sum(1 for r in runs if r.get('has_metrics', False))
has_output = sum(1 for r in runs if r.get('has_output', r.get('has_metrics', False)))
print(f'{len(runs)} runs found, {has_metrics} with metrics, {has_output} with output')
" 2>/dev/null || echo "unknown")
    echo "  $RUN_COUNT"
else
    echo "⚠ Log analysis failed (exit code $?). Continuing without analysis report."
    echo "  See: $OUTPUT_DIR/log_analysis_stderr.log"
    ANALYSIS_REPORT=""
    STEP_ERRORS=$((STEP_ERRORS + 1))
fi

echo ""

# =============================================================================
# Step 2: Calculate Metrics for Runs Missing metrics.json
# =============================================================================

echo "--- Step 2: Calculate Metrics ---"
echo ""

METRICS_CALCULATED=0
METRICS_SKIPPED=0
METRICS_FAILED=0

# Find results directories matching the experiment name that have output but no metrics
for results_dir in results/*"${EXPERIMENT_NAME}"*/; do
    [[ -d "$results_dir" ]] || continue

    # Check if this run has harmonized output
    has_output=false
    for csv_file in "$results_dir"/*harmonized*.csv; do
        if [[ -f "$csv_file" ]]; then
            has_output=true
            break
        fi
    done

    if [[ "$has_output" = false ]]; then
        continue
    fi

    # Check if metrics already exist
    if [[ -f "$results_dir/metrics.json" ]]; then
        METRICS_SKIPPED=$((METRICS_SKIPPED + 1))
        continue
    fi

    # Try to calculate metrics (using backfill strategy to discover gold standard paths)
    echo "  Calculating metrics for: $(basename "$results_dir")"
    if $PYTHON "$CALCULATE_METRICS" \
        --results-dir "$results_dir" \
        --backfill-row-values 2>>"$OUTPUT_DIR/metrics_stderr.log"; then
        # backfill-row-values only creates row_values.csv, we need full metrics
        # Try again with config from .experiment_id
        EXP_ID_FILE="$results_dir/.runtime/.experiment_id"
        if [[ ! -f "$EXP_ID_FILE" ]]; then
            EXP_ID_FILE="$results_dir/.experiment_id"
        fi

        if [[ -f "$EXP_ID_FILE" ]]; then
            CONFIG_PATH=$($PYTHON -c "
import json
data = json.load(open('$EXP_ID_FILE'))
print(data.get('config_path', ''))
" 2>/dev/null)

            if [[ -n "$CONFIG_PATH" && -f "$CONFIG_PATH" ]]; then
                if $PYTHON "$CALCULATE_METRICS" \
                    --results-dir "$results_dir" \
                    --config "$CONFIG_PATH" $VERBOSE 2>>"$OUTPUT_DIR/metrics_stderr.log"; then
                    echo "    ✓ Metrics calculated"
                    METRICS_CALCULATED=$((METRICS_CALCULATED + 1))
                else
                    echo "    ⚠ Metrics calculation failed"
                    METRICS_FAILED=$((METRICS_FAILED + 1))
                fi
            else
                echo "    ⚠ No config found, skipping full metrics"
                METRICS_FAILED=$((METRICS_FAILED + 1))
            fi
        else
            echo "    ⚠ No .experiment_id found, skipping"
            METRICS_FAILED=$((METRICS_FAILED + 1))
        fi
    else
        echo "    ⚠ Backfill failed"
        METRICS_FAILED=$((METRICS_FAILED + 1))
    fi
done

echo ""
echo "  Metrics: $METRICS_CALCULATED calculated, $METRICS_SKIPPED already present, $METRICS_FAILED failed"
echo ""

# =============================================================================
# Step 3: Generate Standard Evaluation Plots
# =============================================================================

echo "--- Step 3: Generate Plots ---"
echo ""

PLOT_ARGS=(
    --metrics-glob "results/*${EXPERIMENT_NAME}*/metrics.json"
    --out-dir "$OUTPUT_DIR"
    --backend "$METRICS_BACKEND"
    --backfill-row-values
)

# Add analysis report if available
if [[ -n "$ANALYSIS_REPORT" && -f "$ANALYSIS_REPORT" ]]; then
    PLOT_ARGS+=(--analysis-report "$ANALYSIS_REPORT")
    echo "  Including failure mode plots from analysis report"
fi

if [[ -n "$VERBOSE" ]]; then
    PLOT_ARGS+=(--verbose)
fi

if $PYTHON "$MAKE_PLOTS" "${PLOT_ARGS[@]}" 2>>"$OUTPUT_DIR/plots_stderr.log"; then
    echo "✓ Plots generated in: $OUTPUT_DIR/plots/"
    echo "✓ Tables saved in: $OUTPUT_DIR/tables/"
else
    echo "⚠ Plot generation failed (exit code $?)"
    echo "  See: $OUTPUT_DIR/plots_stderr.log"
    STEP_ERRORS=$((STEP_ERRORS + 1))
fi

echo ""

# =============================================================================
# Step 4: Write Summary Status File
# =============================================================================

echo "--- Step 4: Summary ---"
echo ""

$PYTHON -c "
import json
from datetime import datetime, timezone
from pathlib import Path

output_dir = Path('$OUTPUT_DIR')
experiment = '$EXPERIMENT_NAME'

# Count outputs
plots = list((output_dir / 'plots').glob('*')) if (output_dir / 'plots').exists() else []
tables = list((output_dir / 'tables').glob('*.csv')) if (output_dir / 'tables').exists() else []
metrics_files = list(Path('results').glob(f'*{experiment}*/metrics.json'))

summary = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'experiment_name': experiment,
    'output_dir': str(output_dir),
    'slurm_job_id': '${SLURM_JOB_ID:-none}',
    'counts': {
        'metrics_files': len(metrics_files),
        'plots_generated': len(plots),
        'tables_generated': len(tables),
        'metrics_calculated': $METRICS_CALCULATED,
        'metrics_skipped': $METRICS_SKIPPED,
        'metrics_failed': $METRICS_FAILED,
        'step_errors': $STEP_ERRORS,
    },
    'paths': {
        'analysis_report': '$ANALYSIS_REPORT' if '$ANALYSIS_REPORT' else None,
        'plots_dir': str(output_dir / 'plots'),
        'tables_dir': str(output_dir / 'tables'),
    },
    'status': 'completed_with_errors' if $STEP_ERRORS > 0 else 'completed',
}

status_file = output_dir / 'analysis_complete.json'
status_file.write_text(json.dumps(summary, indent=2))
print(f'✓ Status file written to: {status_file}')
print()
print(f'  Metrics files found:    {len(metrics_files)}')
print(f'  Plots generated:        {len(plots)}')
print(f'  Tables generated:       {len(tables)}')
print(f'  Status:                 {summary[\"status\"]}')
" 2>/dev/null || echo "⚠ Failed to write summary status file"

echo ""
echo "=============================================="
if [[ $STEP_ERRORS -eq 0 ]]; then
    echo "Post-experiment analysis completed successfully!"
else
    echo "Post-experiment analysis completed with $STEP_ERRORS error(s)"
fi
echo "Output: $OUTPUT_DIR"
echo "=============================================="

exit $STEP_ERRORS
