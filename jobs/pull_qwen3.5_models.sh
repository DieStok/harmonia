#!/bin/bash
# =============================================================================
# Pull qwen3.5:4b and qwen3.5:27b models via Ollama on GPU node
# =============================================================================
# After this completes, submit the 6 experiment jobs for these models.
# =============================================================================

#SBATCH --job-name=pull_qwen3.5_models
#SBATCH --output=/dev/null
#SBATCH --error=/dev/null
#SBATCH --time=01:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:quadro_rtx_6000:1,tmpspace:50G
#SBATCH --partition=gpu

set -e

# Redirect output to logs
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
mkdir -p logs

LOG_TIMESTAMP=$(date +%d-%m-%Y_%H%M)
LOG_OUT="logs/${LOG_TIMESTAMP}_pull_qwen3.5_models_${SLURM_JOB_ID}.out"
LOG_ERR="logs/${LOG_TIMESTAMP}_pull_qwen3.5_models_${SLURM_JOB_ID}.err"
exec > "$LOG_OUT" 2> "$LOG_ERR"

echo "=============================================="
echo "Pulling qwen3.5:4b and qwen3.5:27b models"
echo "=============================================="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $(hostname)"
echo "Date: $(date)"
echo ""

OLLAMA_DIR="/hpc/compgen/projects/ollama/ollama_run/analysis/dstoker"
OLLAMA_BIN="$OLLAMA_DIR/bin/ollama"
OLLAMA_PORT=11434

# Set environment for Ollama
export OLLAMA_MODELS="$OLLAMA_DIR/ollama_models"
export OLLAMA_HOME="$TMPDIR/ollama_pull_${SLURM_JOB_ID}"
export OLLAMA_HOST="0.0.0.0:${OLLAMA_PORT}"
mkdir -p "$OLLAMA_HOME"

echo "OLLAMA_MODELS: $OLLAMA_MODELS"
echo "OLLAMA_HOME: $OLLAMA_HOME"
echo "OLLAMA_HOST: $OLLAMA_HOST"
echo ""

# GPU check
echo "GPU check:"
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader 2>/dev/null
echo ""

# Start Ollama server
echo "Starting Ollama server..."
nohup "$OLLAMA_BIN" serve > "$OLLAMA_HOME/serve.log" 2>&1 &
OLLAMA_PID=$!
echo "Ollama PID: $OLLAMA_PID"

# Wait for server to be ready
echo "Waiting for Ollama to be ready..."
for i in {1..60}; do
    if curl -s "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
        echo "Ollama server ready after ${i}s"
        break
    fi
    sleep 1
done

if ! curl -s "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
    echo "ERROR: Ollama server failed to start"
    cat "$OLLAMA_HOME/serve.log"
    exit 1
fi

echo ""
echo "Current models:"
"$OLLAMA_BIN" list
echo ""

# Pull qwen3.5:4b
echo "=============================================="
echo "Pulling qwen3.5:4b..."
echo "=============================================="
"$OLLAMA_BIN" pull qwen3.5:4b
echo "qwen3.5:4b pull complete!"
echo ""

# Pull qwen3.5:27b
echo "=============================================="
echo "Pulling qwen3.5:27b..."
echo "=============================================="
"$OLLAMA_BIN" pull qwen3.5:27b
echo "qwen3.5:27b pull complete!"
echo ""

echo "=============================================="
echo "Models after pull:"
echo "=============================================="
"$OLLAMA_BIN" list
echo ""

# Stop Ollama
echo "Stopping Ollama..."
kill $OLLAMA_PID 2>/dev/null || true
wait $OLLAMA_PID 2>/dev/null || true

echo ""
echo "=============================================="
echo "Model pull complete! Now submit experiment jobs:"
echo "=============================================="
echo "  cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia"
echo "  sbatch jobs/dou_harmonization_bdikit-tools_qwen3.5-4b.sh"
echo "  sbatch jobs/dou_harmonization_code-context_qwen3.5-4b.sh"
echo "  sbatch jobs/dou_harmonization_codeact_qwen3.5-4b.sh"
echo "  sbatch jobs/dou_harmonization_bdikit-tools_qwen3.5-27b.sh"
echo "  sbatch jobs/dou_harmonization_code-context_qwen3.5-27b.sh"
echo "  sbatch jobs/dou_harmonization_codeact_qwen3.5-27b.sh"
echo ""
echo "Done at $(date)"
