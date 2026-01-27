#!/bin/bash
# =============================================================================
# Harmonia Experiment SBATCH Template - any-llm with OpenRouter
# =============================================================================
# This script runs the dou.csv harmonization experiment using the any-llm
# unified LLM provider interface with OpenRouter backend.
#
# Usage:
#   sbatch jobs/dou_harmonization_anyllm_openrouter.sh
# =============================================================================

#SBATCH --job-name=harmonia_anyllm_openrouter
#SBATCH --output=logs/dou_harmonization_anyllm_openrouter_%j.out
#SBATCH --error=logs/dou_harmonization_anyllm_openrouter_%j.err
#SBATCH --time=02:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
#SBATCH --gres=tmpspace:1G

# =============================================================================
# Environment Setup
# =============================================================================

set -e

echo "=============================================="
echo "Harmonia Experiment (any-llm): dou_harmonization_anyllm_openrouter"
echo "=============================================="
echo ""
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $(hostname)"
echo "Date: $(date)"
echo ""
echo "Backend: any-llm (unified LLM provider interface)"
echo "Provider: OpenRouter"
echo ""

# Change to project directory
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia

# Dynamic port based on job ID to avoid conflicts
PORT=$((8100 + (SLURM_JOB_ID % 100)))
echo "Using Beaker port: $PORT"

# Create logs directory
mkdir -p logs

# =============================================================================
# Verify any-llm is available
# =============================================================================

echo ""
echo "Verifying any-llm-sdk availability..."

ANY_LLM_PATH=/hpc/compgen/projects/llm_GEO_project/any-llm
if [ -d "$ANY_LLM_PATH" ]; then
    echo "  Found any-llm at: $ANY_LLM_PATH"
else
    echo "  ERROR: any-llm not found at $ANY_LLM_PATH"
    exit 1
fi

# =============================================================================
# Start Beaker Server
# =============================================================================

echo ""
echo "Starting Beaker server on port $PORT..."
echo "LLM Provider: anyllm:openrouter (any-llm unified interface)"
echo "LLM Model: xiaomi/mimo-v2-flash:free"

# Start Beaker server with any-llm mounted and in PYTHONPATH
# Note: Using --writable-tmpfs to allow temporary writes
apptainer exec \
    --writable-tmpfs \
    --bind .:/jupyter \
    --bind $ANY_LLM_PATH:/any-llm:ro \
    --pwd /jupyter \
    --bind /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem:/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem:ro \
    --env-file .env \
    --env JUPYTER_SERVER=http://localhost:$PORT \
    --env LLM_SERVICE_PROVIDER=openrouter \
    --env LLM_SERVICE_MODEL=xiaomi/mimo-v2-flash:free \
    --env LLM_PROVIDER_IMPORT_PATH=bdikit_context.llm.anyllm.AnyLLMModel \
    --env PYTHONPATH=/jupyter:/any-llm/src \
    jupyter.sif \
    beaker dev watch --ip 0.0.0.0 --port $PORT &

SERVER_PID=$!
echo "Beaker Server PID: $SERVER_PID"

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
echo "Waiting for Beaker server to start..."
MAX_WAIT=90
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/api" 2>/dev/null | grep -q "200\|401"; then
        echo "Beaker server is ready!"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo "  Waiting... ($WAITED/$MAX_WAIT seconds)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "ERROR: Beaker server failed to start within $MAX_WAIT seconds"
    exit 1
fi

# =============================================================================
# Run Experiment
# =============================================================================

echo ""
echo "Running experiment..."
echo "Config: experiments/configs/dou_harmonization_anyllm_openrouter.yaml"
echo ""

# Get token from env file
TOKEN=$(grep "^JUPYTER_TOKEN=" .env | cut -d '=' -f2)

# Run the experiment
python run_experiment.py \
    --config experiments/configs/dou_harmonization_anyllm_openrouter.yaml \
    --server http://localhost:$PORT \
    --token "$TOKEN" \
    --timeout 3600

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
