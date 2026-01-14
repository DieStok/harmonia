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

#SBATCH --job-name=harmonia_dou_harmonization
#SBATCH --output=logs/dou_harmonization_%j.out
#SBATCH --error=logs/dou_harmonization_%j.err
#SBATCH --time=02:00:00
#SBATCH --mem=20G
#SBATCH --cpus-per-task=2
#SBATCH --gres=tmpspace:1G

# =============================================================================
# Environment Setup
# =============================================================================

set -e

echo "=============================================="
echo "Harmonia Experiment: dou_harmonization"
echo "=============================================="
echo ""
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $(hostname)"
echo "Date: $(date)"
echo ""

# Change to project directory
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia

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
echo "LLM Provider: openrouter"
echo "LLM Model: xiaomi/mimo-v2-flash:free"

# Start server in background
# Note: --env flags override values from --env-file
apptainer exec \
    --bind .:/jupyter \
    --pwd /jupyter \
    --bind /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem:/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem:ro \
    --env-file .env \
    --env JUPYTER_SERVER=http://localhost:$PORT \
    --env LLM_SERVICE_PROVIDER=openrouter \
    --env LLM_SERVICE_MODEL=xiaomi/mimo-v2-flash:free \
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
echo "Config: experiments/configs/dou_harmonization_mimo-v2-flash.yaml"
echo ""

# Get token from env file
TOKEN=$(grep "^JUPYTER_TOKEN=" .env | cut -d '=' -f2)

# Run the experiment
python run_experiment.py \
    --config experiments/configs/dou_harmonization_mimo-v2-flash.yaml \
    --server http://localhost:$PORT \
    --token "$TOKEN" \
    --timeout 300

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
