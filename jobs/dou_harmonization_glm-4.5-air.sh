#!/bin/bash
# =============================================================================
# Harmonia Experiment SBATCH Template - GPU with Ollama
# =============================================================================
# This template is used by generate_jobs.py to create GPU job scripts.
# Variables in {{double_braces}} are replaced by the generator.
#
# Usage:
#   sbatch jobs/experiment_ollama.sh
#
# Or generate jobs first:
#   python generate_jobs.py --config experiments/configs/dou_harmonization_nemotron.yaml --gpu
# =============================================================================

#SBATCH --job-name=harmonia_dou_harmonization_glm-4.5-air
#SBATCH --output=logs/dou_harmonization_glm-4.5-air_%j.out
#SBATCH --error=logs/dou_harmonization_glm-4.5-air_%j.err
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=2
#SBATCH --gres=tmpspace:1G
#SBATCH --partition=gpu
#SBATCH --gpus-per-node=1

# =============================================================================
# Environment Setup
# =============================================================================

set -e

echo "=============================================="
echo "Harmonia Experiment (GPU): dou_harmonization_glm-4.5-air"
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
echo "Using Beaker port: $PORT"

# Create logs directory
mkdir -p logs

# =============================================================================
# Start Ollama Server
# =============================================================================

echo ""
echo "Starting Ollama server..."

OLLAMA_DIR=/hpc/compgen/projects/ollama/ollama_run/analysis/dstoker

# Start Ollama server
$OLLAMA_DIR/start_ollama.sh &
OLLAMA_START_PID=$!

# Wait for Ollama to initialize and verify it's responding
echo "Waiting for Ollama to start..."
OLLAMA_READY=0
for i in {1..60}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        OLLAMA_READY=1
        echo "Ollama server is responding (waited ${i}s)"
        break
    fi
    sleep 1
done

if [ $OLLAMA_READY -eq 0 ]; then
    echo "ERROR: Ollama server not responding after 60 seconds"
    exit 1
fi

# Set Ollama endpoint for Beaker/Archytas
export LLM_BASE_URL=http://$(hostname):11434
export OLLAMA_HOST=http://$(hostname):11434

echo "Ollama endpoint: $LLM_BASE_URL"

# Pre-warm the model by loading it (prevents timeout on first request)
echo "Pre-loading model z-ai/glm-4.5-air:free..."
curl -s http://localhost:11434/api/generate -d "{\"model\": \"z-ai/glm-4.5-air:free\", \"prompt\": \"Hello\", \"stream\": false}" > /dev/null 2>&1 || echo "  Warning: Model pre-load may have failed"
echo "Model preloaded"

# =============================================================================
# Start Beaker Server
# =============================================================================

echo ""
echo "Starting Beaker server on port $PORT..."
echo "LLM Provider: openrouter"
echo "LLM Model: z-ai/glm-4.5-air:free"

# Start Beaker server
# Note: bdikit_context is pre-installed in the image with proper entry points
# --env flags override values from --env-file
apptainer exec \
    --nv \
    --bind .:/jupyter \
    --pwd /jupyter \
    --bind /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem:/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem:ro \
    --env-file .env \
    --env JUPYTER_SERVER=http://localhost:$PORT \
    --env LLM_SERVICE_PROVIDER=openrouter \
    --env LLM_SERVICE_MODEL=z-ai/glm-4.5-air:free \
    --env LLM_BASE_URL=$LLM_BASE_URL \
    --env OLLAMA_HOST=$OLLAMA_HOST \
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
    # Stop Ollama server
    echo "Stopping Ollama server..."
    $OLLAMA_DIR/stop_ollama.sh 2>/dev/null || true
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
echo "Config: experiments/configs/dou_harmonization_glm-4.5-air.yaml"
echo ""

# Get token from env file
TOKEN=$(grep "^JUPYTER_TOKEN=" .env | cut -d '=' -f2)

# Run the experiment
python run_experiment.py \
    --config experiments/configs/dou_harmonization_glm-4.5-air.yaml \
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
