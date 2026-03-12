#!/bin/bash
# =============================================================================
# Harmonia Experiment Launcher with Automatic Post-Analysis
# =============================================================================
# Convenience wrapper that:
#   1. Submits experiment job(s) via sbatch
#   2. Captures the SLURM job ID(s)
#   3. Automatically submits the post-analysis watcher with --dependency=afterany
#
# Usage:
#   # Submit a single job script with auto post-analysis:
#   ./launch_experiment.sh jobs/dou_harmonization_gpt4o.sh
#
#   # Submit multiple job scripts (watcher waits for all):
#   ./launch_experiment.sh jobs/dou_harmonization_gpt4o.sh jobs/dou_harmonization_claude.sh
#
#   # Submit all jobs in a directory:
#   ./launch_experiment.sh jobs/
#
#   # With custom experiment name for analysis grouping:
#   ./launch_experiment.sh --experiment-name "march12_batch" jobs/*.sh
#
#   # Skip the post-analysis watcher:
#   ./launch_experiment.sh --no-watcher jobs/dou_harmonization_gpt4o.sh
#
#   # Pass extra args to the watcher:
#   ./launch_experiment.sh --watcher-args "--backend plotly --verbose" jobs/*.sh
# =============================================================================

set -euo pipefail

# =============================================================================
# Parse Arguments
# =============================================================================

EXPERIMENT_NAME=""
NO_WATCHER=false
WATCHER_ARGS=""
JOB_SCRIPTS=()

usage() {
    echo "Usage: $0 [OPTIONS] <job_script.sh|job_dir/> [job_script2.sh ...]"
    echo ""
    echo "Options:"
    echo "  --experiment-name <name>    Experiment name for analysis grouping"
    echo "                              (default: inferred from first job script)"
    echo "  --no-watcher               Skip automatic post-analysis submission"
    echo "  --watcher-args <args>       Extra arguments to pass to the watcher script"
    echo "  -h, --help                  Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 jobs/dou_harmonization_gpt4o.sh"
    echo "  $0 jobs/"
    echo "  $0 --experiment-name 'march12' jobs/*.sh"
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --experiment-name)
            EXPERIMENT_NAME="$2"
            shift 2
            ;;
        --no-watcher)
            NO_WATCHER=true
            shift
            ;;
        --watcher-args)
            WATCHER_ARGS="$2"
            shift 2
            ;;
        -h|--help)
            usage 0
            ;;
        -*)
            echo "ERROR: Unknown option: $1"
            usage 1
            ;;
        *)
            # If argument is a directory, expand to all .sh files in it
            if [[ -d "$1" ]]; then
                for f in "$1"/*.sh; do
                    [[ -f "$f" ]] && JOB_SCRIPTS+=("$f")
                done
            elif [[ -f "$1" ]]; then
                JOB_SCRIPTS+=("$1")
            else
                echo "ERROR: Not a file or directory: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ ${#JOB_SCRIPTS[@]} -eq 0 ]]; then
    echo "ERROR: No job scripts specified"
    usage 1
fi

# =============================================================================
# Setup
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Infer experiment name from first job script if not provided.
# The experiment name is used as a SUBSTRING glob pattern to match results directories:
#   results/*${EXPERIMENT_NAME}*/metrics.json
# So "dou_harmonization" matches all runs like dou_harmonization_bdikit-tools_gpt4o_*.
# Use a broad name to aggregate across models, or a specific name for single-model analysis.
if [[ -z "$EXPERIMENT_NAME" ]]; then
    # Extract from generated job script by reading the experiment_name from the
    # RUN_RESULTS_DIR line (most reliable source)
    FIRST_SCRIPT="${JOB_SCRIPTS[0]}"
    EXPERIMENT_NAME=$(grep -oP 'results/\$\{TIMESTAMP\}_\K[^_$]+(?:_[^_$]+)*(?=_\$\{SLURM)' "$FIRST_SCRIPT" 2>/dev/null || true)

    # Fallback: use the job script filename
    if [[ -z "$EXPERIMENT_NAME" ]]; then
        EXPERIMENT_NAME=$(basename "$FIRST_SCRIPT" .sh)
    fi
fi

echo "=============================================="
echo "Harmonia Experiment Launcher"
echo "=============================================="
echo ""
echo "Experiment name: $EXPERIMENT_NAME"
echo "Job scripts:     ${#JOB_SCRIPTS[@]}"
echo "Post-analysis:   $(if $NO_WATCHER; then echo 'disabled'; else echo 'enabled'; fi)"
echo ""

# =============================================================================
# Submit Experiment Jobs
# =============================================================================

SUBMITTED_IDS=()
SUBMIT_ERRORS=0

for script in "${JOB_SCRIPTS[@]}"; do
    script_name=$(basename "$script")
    echo -n "  Submitting $script_name ... "

    if OUTPUT=$(sbatch "$script" 2>&1); then
        # Extract job ID from sbatch output: "Submitted batch job 12345"
        JOB_ID=$(echo "$OUTPUT" | grep -oP '\d+$')
        SUBMITTED_IDS+=("$JOB_ID")
        echo "OK (job $JOB_ID)"
    else
        echo "FAILED"
        echo "    $OUTPUT"
        SUBMIT_ERRORS=$((SUBMIT_ERRORS + 1))
    fi
done

echo ""
echo "Submitted ${#SUBMITTED_IDS[@]} of ${#JOB_SCRIPTS[@]} jobs"

if [[ ${#SUBMITTED_IDS[@]} -eq 0 ]]; then
    echo "ERROR: No jobs were submitted successfully"
    exit 1
fi

# =============================================================================
# Submit Post-Analysis Watcher
# =============================================================================

if $NO_WATCHER; then
    echo ""
    echo "Post-analysis watcher: SKIPPED (--no-watcher)"
    echo ""
    echo "Job IDs: ${SUBMITTED_IDS[*]}"
    echo ""
    echo "To manually run post-analysis later:"
    echo "  bash run_post_experiment_analysis.sh --experiment-name '$EXPERIMENT_NAME'"
    exit $SUBMIT_ERRORS
fi

# Build dependency string: afterany:id1:id2:id3
DEPENDENCY_STR=$(IFS=:; echo "${SUBMITTED_IDS[*]}")

echo ""
echo -n "  Submitting post-analysis watcher (depends on: $DEPENDENCY_STR) ... "

# shellcheck disable=SC2086
if WATCHER_OUTPUT=$(sbatch \
    --dependency="afterany:$DEPENDENCY_STR" \
    run_post_experiment_analysis.sh \
    --experiment-name "$EXPERIMENT_NAME" \
    $WATCHER_ARGS 2>&1); then
    WATCHER_ID=$(echo "$WATCHER_OUTPUT" | grep -oP '\d+$')
    echo "OK (job $WATCHER_ID)"
else
    echo "FAILED"
    echo "    $WATCHER_OUTPUT"
    echo ""
    echo "You can manually run post-analysis later:"
    echo "  bash run_post_experiment_analysis.sh --experiment-name '$EXPERIMENT_NAME'"
    exit 1
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
echo "=============================================="
echo "Launch Summary"
echo "=============================================="
echo ""
echo "  Experiment jobs: ${SUBMITTED_IDS[*]}"
echo "  Watcher job:     $WATCHER_ID (runs after all experiments complete)"
echo "  Experiment name: $EXPERIMENT_NAME"
echo ""
echo "  Track progress:  squeue -u \$USER"
echo "  Cancel all:      scancel ${SUBMITTED_IDS[*]} $WATCHER_ID"
echo ""

exit $SUBMIT_ERRORS
