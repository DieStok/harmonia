#!/bin/bash
# =============================================================================
# Harmonia Experiment SBATCH Template
# =============================================================================
# This template is used by generate_jobs.py to create individual job scripts.
# Variables in {{double_braces}} are replaced by the generator.
#
# Usage:
#   sbatch jobs/experiment_gpt4o.sh
#
# Or generate jobs first:
#   python generate_jobs.py --config experiments/configs/dou_harmonization.yaml
# =============================================================================

#SBATCH --job-name=harmonia_{{experiment_name}}
#SBATCH --output=logs/{{experiment_name}}_%j.out
#SBATCH --error=logs/{{experiment_name}}_%j.err
#SBATCH --time={{time_limit}}
#SBATCH --mem={{memory}}
#SBATCH --cpus-per-task={{cpus}}
#SBATCH --gres=tmpspace:{{tmpspace}}G

# =============================================================================
# Environment Setup
# =============================================================================

set -e

echo "=============================================="
echo "Harmonia Experiment: {{experiment_name}}"
echo "=============================================="
echo ""
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $(hostname)"
echo "Date: $(date)"
echo ""

# Change to project directory
cd {{project_dir}}

# Dynamic port based on job ID to avoid conflicts
PORT=$((8100 + (SLURM_JOB_ID % 100)))
echo "Using port: $PORT"

# Create logs directory
mkdir -p logs

# =============================================================================
# Start Beaker Server
# =============================================================================

echo ""
echo "Starting Beaker server on port $PORT..."

# Start server in background
apptainer exec \
    --bind .:/jupyter \
    --pwd /jupyter \
    {{ssl_bind}} \
    --env-file {{env_file}} \
    --env JUPYTER_SERVER=http://localhost:$PORT \
    jupyter.sif \
    beaker dev watch --ip 0.0.0.0 --port $PORT &

SERVER_PID=$!
echo "Server PID: $SERVER_PID"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Cleaning up..."
    if [ -n "$SERVER_PID" ]; then
        kill $SERVER_PID 2>/dev/null || true
        wait $SERVER_PID 2>/dev/null || true
    fi
    echo "Done."
}
trap cleanup EXIT

# Wait for server to be ready
echo "Waiting for server to start..."
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/api" 2>/dev/null | grep -q "200\|401"; then
        echo "Server is ready!"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo "  Waiting... ($WAITED/$MAX_WAIT seconds)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "ERROR: Server failed to start within $MAX_WAIT seconds"
    exit 1
fi

# =============================================================================
# Run Experiment
# =============================================================================

echo ""
echo "Running experiment..."
echo "Config: {{config_path}}"
echo ""

# Get token from env file
TOKEN=$(grep "^JUPYTER_TOKEN=" {{env_file}} | cut -d '=' -f2)

# Run the experiment
python run_experiment.py \
    --config {{config_path}} \
    --server http://localhost:$PORT \
    --token "$TOKEN" \
    --timeout {{timeout}}

EXIT_CODE=$?

# =============================================================================
# Completion
# =============================================================================

echo ""
echo "=============================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "Experiment completed successfully!"
else
    echo "Experiment failed with exit code: $EXIT_CODE"
fi
echo "=============================================="

exit $EXIT_CODE
