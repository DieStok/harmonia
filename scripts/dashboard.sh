#!/bin/bash
# Harmonia Experiment Dashboard — start/stop convenience script.
#
# Usage:
#   ./scripts/dashboard.sh start [--slurm] [--port PORT] [--phoenix-endpoint URL]
#   ./scripts/dashboard.sh stop
#   ./scripts/dashboard.sh status
#
# Default: runs on submit node. With --slurm, launches as a SLURM job.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$PROJECT_DIR/.venv/bin/python"
APP="$PROJECT_DIR/src/dashboard/app.py"
SCREEN_NAME="harmonia-dashboard"
SLURM_JOB_NAME="harmonia-dashboard"

PORT=8050
PHOENIX_ENDPOINT="http://localhost:6006"
RESULTS_DIR="$PROJECT_DIR/results"
USE_SLURM=false

# Parse arguments
ACTION="${1:-help}"
shift || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --slurm)
            USE_SLURM=true
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --phoenix-endpoint)
            PHOENIX_ENDPOINT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

case "$ACTION" in
    start)
        # Check if already running
        if screen -list 2>/dev/null | grep -q "$SCREEN_NAME"; then
            echo "Dashboard already running in screen session '$SCREEN_NAME'."
            echo "Use './scripts/dashboard.sh stop' to stop it first."
            exit 1
        fi

        if squeue -u "$USER" --name="$SLURM_JOB_NAME" -h 2>/dev/null | grep -q .; then
            echo "Dashboard already running as SLURM job."
            echo "Use './scripts/dashboard.sh stop' to cancel it first."
            exit 1
        fi

        if $USE_SLURM; then
            echo "Starting dashboard as SLURM job..."
            srun --job-name="$SLURM_JOB_NAME" \
                 --account=compgen \
                 --time=04:00:00 \
                 --mem=8G \
                 --cpus-per-task=2 \
                 "$VENV" "$APP" \
                 --phoenix-endpoint "$PHOENIX_ENDPOINT" \
                 --results-dir "$RESULTS_DIR" \
                 --port "$PORT" &
            sleep 2
            NODE=$(squeue -u "$USER" --name="$SLURM_JOB_NAME" -o "%N" -h 2>/dev/null)
            echo ""
            echo "Dashboard starting on compute node: $NODE"
            echo "Access via: ssh -L $PORT:$NODE:$PORT <submit-node>"
            echo "Then open: http://localhost:$PORT"
        else
            echo "Starting dashboard on submit node in screen session '$SCREEN_NAME'..."
            screen -dmS "$SCREEN_NAME" \
                "$VENV" "$APP" \
                --phoenix-endpoint "$PHOENIX_ENDPOINT" \
                --results-dir "$RESULTS_DIR" \
                --port "$PORT"
            echo ""
            echo "Dashboard started in screen session '$SCREEN_NAME'."
            echo "Access via: ssh -L $PORT:localhost:$PORT $(hostname)"
            echo "Then open: http://localhost:$PORT"
            echo ""
            echo "Attach to screen: screen -r $SCREEN_NAME"
        fi
        ;;

    stop)
        stopped=false

        # Stop screen session
        if screen -list 2>/dev/null | grep -q "$SCREEN_NAME"; then
            screen -S "$SCREEN_NAME" -X quit
            echo "Stopped screen session '$SCREEN_NAME'."
            stopped=true
        fi

        # Cancel SLURM job
        JOB_ID=$(squeue -u "$USER" --name="$SLURM_JOB_NAME" -o "%i" -h 2>/dev/null | head -1)
        if [ -n "$JOB_ID" ]; then
            scancel "$JOB_ID"
            echo "Cancelled SLURM job $JOB_ID."
            stopped=true
        fi

        if ! $stopped; then
            echo "No running dashboard found."
        fi
        ;;

    status)
        echo "=== Dashboard Status ==="

        # Check screen
        if screen -list 2>/dev/null | grep -q "$SCREEN_NAME"; then
            echo "Screen session: RUNNING"
            screen -list 2>/dev/null | grep "$SCREEN_NAME"
        else
            echo "Screen session: not running"
        fi

        # Check SLURM
        SLURM_INFO=$(squeue -u "$USER" --name="$SLURM_JOB_NAME" -o "%i %N %T %M" -h 2>/dev/null)
        if [ -n "$SLURM_INFO" ]; then
            echo "SLURM job: RUNNING"
            echo "  JobID Node State Runtime"
            echo "  $SLURM_INFO"
        else
            echo "SLURM job: not running"
        fi
        ;;

    help|*)
        echo "Usage: $0 {start|stop|status} [OPTIONS]"
        echo ""
        echo "Commands:"
        echo "  start     Start the dashboard"
        echo "  stop      Stop the dashboard"
        echo "  status    Check dashboard status"
        echo ""
        echo "Options:"
        echo "  --slurm                   Run as SLURM job (default: submit node)"
        echo "  --port PORT               Dashboard port (default: 8050)"
        echo "  --phoenix-endpoint URL    Phoenix server URL (default: http://localhost:6006)"
        ;;
esac
