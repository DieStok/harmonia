#!/bin/bash
# =============================================================================
# Harmonia Execution Script (Apptainer)
# =============================================================================
#
# Usage:
#   ./exec_apptainer_harmonia.sh                    # Default port 8100, uses .env
#   ./exec_apptainer_harmonia.sh 8101               # Custom port
#   ./exec_apptainer_harmonia.sh --port 8101
#   ./exec_apptainer_harmonia.sh --env path/to/custom.env  # Use custom .env file
#   ./exec_apptainer_harmonia.sh --config path/to/config.yaml  # Generate .env from config
#   ./exec_apptainer_harmonia.sh --config config.yaml --monitor  # With logging
#   ./exec_apptainer_harmonia.sh --image path/to/custom.sif  # Use custom image
#   ./exec_apptainer_harmonia.sh --job-name experiment_12345  # For consistent log naming
#   ./exec_apptainer_harmonia.sh --run-id a3f7b2c1            # Use specific run ID
#
# =============================================================================

set -e

# Get script directory (where harmonia is installed)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
HOSTNAME=$(hostname)

# Default paths for data and results (can be overridden via command line)
DEFAULT_DATA_DIR="/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia"
DEFAULT_RESULTS_DIR="/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/results"
DATA_BASE_DIR=""
RESULTS_DIR=""

# Ollama configuration
OLLAMA_DIR="/hpc/compgen/projects/ollama/ollama_run/analysis/dstoker"
# Dynamic Ollama port per SLURM job for isolation
# Interactive/manual use (no SLURM_JOB_ID) keeps default 11434
if [ -n "$SLURM_JOB_ID" ]; then
    OLLAMA_PORT=$((11434 + 1 + (SLURM_JOB_ID % 200)))
else
    OLLAMA_PORT=11434
fi
OLLAMA_STARTED_BY_US=false

# Logs directory
LOGS_DIR="${SCRIPT_DIR}/logs"
mkdir -p "$LOGS_DIR"

# Parse arguments
PORT=8100
ENV_FILE=""
CONFIG_FILE=""
MONITOR_MODE=false
SIF_IMAGE=""
JOB_NAME=""
EXPERIMENT_NAME=""
RUN_ID=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        --env|-e)
            ENV_FILE="$2"
            shift 2
            ;;
        --config|-c)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --monitor|-m)
            MONITOR_MODE=true
            shift
            ;;
        --image|-i)
            SIF_IMAGE="$2"
            shift 2
            ;;
        --job-name|-j)
            JOB_NAME="$2"
            shift 2
            ;;
        --data-dir|-d)
            DATA_BASE_DIR="$2"
            shift 2
            ;;
        --results-dir|-r)
            RESULTS_DIR="$2"
            shift 2
            ;;
        --run-id|-R)
            RUN_ID="$2"
            shift 2
            ;;
        [0-9]*)
            PORT="$1"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] [PORT]"
            echo ""
            echo "Options:"
            echo "  --port, -p PORT      Port to run Beaker on (default: 8100)"
            echo "  --env, -e FILE       Path to custom .env file"
            echo "  --config, -c FILE    Path to experiment config YAML (generates .env)"
            echo "  --monitor, -m        Enable logging monitor (requires --config)"
            echo "  --image, -i FILE     Path to Apptainer image (default: auto-detect)"
            echo "  --job-name, -j NAME  Job name for log file naming (e.g., experiment_12345)"
            echo "  --data-dir, -d DIR   Data directory to bind as /data (read-only)"
            echo "  --results-dir, -r DIR Results directory to bind as /results (read-write)"
            echo "  --run-id, -R ID      Unique 8-char hex run ID (auto-generated if not provided)"
            echo "  --help, -h           Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Use default .env"
            echo "  $0 --port 8101                        # Custom port"
            echo "  $0 --env configs/manual/my_config_associated.env"
            echo "  $0 --config configs/manual/dou_harmonization_manual_devstral.yaml"
            echo "  $0 --config configs/manual/my_config.yaml --monitor  # With logging"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate monitor mode requirements
if [ "$MONITOR_MODE" = true ] && [ -z "$CONFIG_FILE" ]; then
    echo "ERROR: --monitor requires --config to be specified"
    exit 1
fi

# Apply defaults for data and results directories if not specified
if [ -z "$DATA_BASE_DIR" ]; then
    DATA_BASE_DIR="$DEFAULT_DATA_DIR"
fi
if [ -z "$RESULTS_DIR" ]; then
    RESULTS_DIR="$DEFAULT_RESULTS_DIR"
fi

# Validate directories exist
if [ ! -d "$DATA_BASE_DIR" ]; then
    echo "ERROR: Data directory not found: $DATA_BASE_DIR"
    exit 1
fi

# Extract experiment name from config (used for URL, tab title, results dir)
if [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ]; then
    EXPERIMENT_NAME=$(python3 -c "
import yaml
with open('$CONFIG_FILE') as f:
    cfg = yaml.safe_load(f)
print(cfg.get('experiment', {}).get('name', 'unnamed'))
" 2>/dev/null || echo "unnamed")
fi

# Generate RUN_ID if not provided (manual mode generates here;
# automated/SBATCH mode passes it via --run-id flag)
if [ -z "$RUN_ID" ]; then
    RUN_ID=$(python3 -c "import secrets; print(secrets.token_hex(4))")
fi
export RUN_ID
echo "Run ID: ${RUN_ID}"

# For monitor mode, create experiment-specific results directory
# unless --results-dir was explicitly provided
if [ "$MONITOR_MODE" = true ] && [ "$RESULTS_DIR" = "$DEFAULT_RESULTS_DIR" ]; then
    TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
    RESULTS_DIR="${DEFAULT_RESULTS_DIR}/${EXPERIMENT_NAME}_${TIMESTAMP}_${RUN_ID}"
    # Also set job name for consistent log naming
    if [ -z "$JOB_NAME" ]; then
        JOB_NAME="${EXPERIMENT_NAME}_${TIMESTAMP}"
    fi
    echo "Results directory: ${RESULTS_DIR}"
fi

# Create results directory if it doesn't exist
mkdir -p "$RESULTS_DIR"

# If config file specified, generate .env from it
if [ -n "$CONFIG_FILE" ]; then
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "ERROR: Config file not found: $CONFIG_FILE"
        exit 1
    fi

    # Generate .env file from config
    echo "Generating .env from config: $CONFIG_FILE"
    python3 "${SCRIPT_DIR}/generate_env.py" --config "$CONFIG_FILE" --base-env "${SCRIPT_DIR}/.env"

    # Set ENV_FILE to the generated file
    CONFIG_BASENAME=$(basename "$CONFIG_FILE" .yaml)
    CONFIG_BASENAME=$(basename "$CONFIG_BASENAME" .yml)
    CONFIG_DIR=$(dirname "$CONFIG_FILE")
    ENV_FILE="${CONFIG_DIR}/${CONFIG_BASENAME}_associated.env"

    echo "Using generated .env: $ENV_FILE"
fi

# Determine which .env file to use
if [ -z "$ENV_FILE" ]; then
    # Default: look for .env in current directory, then script directory
    if [ -f ".env" ]; then
        ENV_FILE=".env"
    elif [ -f "${SCRIPT_DIR}/.env" ]; then
        ENV_FILE="${SCRIPT_DIR}/.env"
    else
        echo "ERROR: .env file not found!"
        echo ""
        echo "Please either:"
        echo "  1. Create a .env file with your API keys:"
        echo "     cp ${SCRIPT_DIR}/.env.template .env"
        echo "     nano .env"
        echo ""
        echo "  2. Specify a custom .env file:"
        echo "     $0 --env path/to/custom.env"
        echo ""
        echo "  3. Generate from an experiment config:"
        echo "     $0 --config path/to/experiment_config.yaml"
        echo ""
        exit 1
    fi
fi

# Validate .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env file not found: $ENV_FILE"
    exit 1
fi

# Convert to absolute path
ENV_FILE=$(realpath "$ENV_FILE")

# Read TOKEN from .env file if not set
if [ -z "$TOKEN" ]; then
    TOKEN=$(grep "^JUPYTER_TOKEN=" "$ENV_FILE" | cut -d '=' -f2)
fi

# Read SSL_CERT_FILE from .env
HOST_SSL_CERT=$(grep "^SSL_CERT_FILE=" "$ENV_FILE" | cut -d '=' -f2)

# Read LLM configuration from .env for display
LLM_PROVIDER=$(grep "^LLM_SERVICE_PROVIDER=" "$ENV_FILE" | cut -d '=' -f2)
LLM_MODEL=$(grep "^LLM_SERVICE_MODEL=" "$ENV_FILE" | cut -d '=' -f2)

# Set defaults if not specified
LLM_PROVIDER=${LLM_PROVIDER:-openai}
LLM_MODEL=${LLM_MODEL:-gpt-4o}

# Write .experiment_id metadata file into results directory
# This links the run_id to the experiment's log files and configuration
EXPERIMENT_MODE="manual"
if [ -n "$SLURM_JOB_ID" ]; then
    EXPERIMENT_MODE="automated"
fi

# Build log_files JSON based on mode
if [ "$EXPERIMENT_MODE" = "automated" ] && [ -n "$JOB_NAME" ]; then
    LOG_FILES_JSON=$(cat <<LOGEOF
    "log_files": {
      "stdout": "logs/${JOB_NAME}_${RUN_ID}.out",
      "stderr": "logs/${JOB_NAME}_${RUN_ID}.err"
    }
LOGEOF
    )
else
    LOG_FILES_JSON=$(cat <<LOGEOF
    "log_files": {
      "beaker": "logs/${EXPERIMENT_NAME:-unknown}_${RUN_ID}_beaker.log",
      "ollama": "logs/${EXPERIMENT_NAME:-unknown}_${RUN_ID}_ollama.log"
    }
LOGEOF
    )
fi

cat > "${RESULTS_DIR}/.experiment_id" <<EXPEOF
{
  "schema_version": "1.0",
  "run_id": "${RUN_ID}",
  "experiment_name": "${EXPERIMENT_NAME:-unknown}",
  "mode": "${EXPERIMENT_MODE}",
  "slurm_job_id": ${SLURM_JOB_ID:-null},
  "config_path": "${CONFIG_FILE:-null}",
  "timestamp_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "llm_provider": "${LLM_PROVIDER}",
  "llm_model": "${LLM_MODEL}",
  "hostname": "${HOSTNAME}",
  "beaker_port": ${PORT},
${LOG_FILES_JSON}
}
EXPEOF
echo "Wrote .experiment_id to ${RESULTS_DIR}/.experiment_id"

# =============================================================================
# Check if this is a local LLM provider that needs Ollama
# =============================================================================
is_local_llm_provider() {
    local provider="$1"
    case "$provider" in
        ollama|anyllm:ollama|local|anyllm:local)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Function to start Ollama server
start_ollama_server() {
    # Generate log file name based on job name or timestamp
    if [ -n "$JOB_NAME" ]; then
        # Use job name for consistent naming with experiment logs
        OLLAMA_LOG_FILE="${LOGS_DIR}/${JOB_NAME}_ollama.log"
    else
        # Fallback to timestamp if no job name provided
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        OLLAMA_LOG_FILE="${LOGS_DIR}/ollama_${TIMESTAMP}.log"
    fi

    echo ""
    echo "🦙 Local LLM detected (provider: $LLM_PROVIDER)"
    echo "   Ollama port: ${OLLAMA_PORT}"

    # --- Per-job isolation setup (SLURM batch mode) ---
    if [ -n "$SLURM_JOB_ID" ]; then
        echo "   SLURM job detected (ID: $SLURM_JOB_ID) - using per-job Ollama isolation"

        # Per-job PID file
        OLLAMA_PID_FILE="${OLLAMA_DIR}/.ollama_${SLURM_JOB_ID}.pid"
        export OLLAMA_PID_FILE

        # Per-job OLLAMA_HOME for runtime data isolation
        if [ -n "$TMPDIR" ]; then
            export OLLAMA_HOME="$TMPDIR/ollama_${SLURM_JOB_ID}"
        else
            export OLLAMA_HOME="${OLLAMA_DIR}/ollama_home_${SLURM_JOB_ID}"
        fi
        mkdir -p "$OLLAMA_HOME"
        echo "   OLLAMA_HOME: ${OLLAMA_HOME}"
        echo "   OLLAMA_PID_FILE: ${OLLAMA_PID_FILE}"

        # Set OLLAMA_HOST for this job's unique port
        export OLLAMA_HOST="0.0.0.0:${OLLAMA_PORT}"

    else
        echo "   Interactive mode - checking if Ollama server is running on this node ($(hostname))..."

        # --- Interactive/manual mode: keep original sharing logic ---
        OLLAMA_PROCESS_RUNNING=false
        if pgrep -f "ollama serve" > /dev/null 2>&1; then
            OLLAMA_PROCESS_RUNNING=true
        fi

        if [ "$OLLAMA_PROCESS_RUNNING" = true ] && curl -s "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
            echo "   ✓ Ollama server already running on port ${OLLAMA_PORT} (this node)"

            # Check if the required model is available in this Ollama instance
            if ! curl -s "http://localhost:${OLLAMA_PORT}/api/tags" | grep -q "\"name\":\"${LLM_MODEL}\""; then
                echo "   ⚠ Model '${LLM_MODEL}' not found in running Ollama instance"
                echo "     Stopping existing Ollama and starting fresh with model preload..."
                pkill -f "ollama serve" 2>/dev/null || true
                sleep 2
                OLLAMA_PROCESS_RUNNING=false
            else
                echo "   ✓ Model '${LLM_MODEL}' is available"
                if [ -n "$JOB_NAME" ]; then
                    OLLAMA_LOG_FILE="${LOGS_DIR}/${JOB_NAME}_ollama_shared.log"
                else
                    OLLAMA_LOG_FILE="${LOGS_DIR}/ollama_shared_${TIMESTAMP}.log"
                fi
                echo "   Ollama log: ${OLLAMA_LOG_FILE}"
                echo "[$(date)] Ollama server already running on $(hostname) with model ${LLM_MODEL}" > "${OLLAMA_LOG_FILE}"

                export LLM_BASE_URL="http://$(hostname):${OLLAMA_PORT}"
                export OLLAMA_HOST="http://$(hostname):${OLLAMA_PORT}"
                echo "   LLM_BASE_URL: ${LLM_BASE_URL}"
                echo "   OLLAMA_HOST:  ${OLLAMA_HOST}"

                return 0
            fi
        fi

        # If API responds but no local process, it might be from another node - ignore it
        if curl -s "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1 && [ "$OLLAMA_PROCESS_RUNNING" = false ]; then
            echo "   ⚠ Ollama API responds but no local process found"
            echo "     (May be from another HPC node - starting fresh instance)"
        fi
    fi

    # Check if the Ollama start script exists
    if [ ! -f "${OLLAMA_DIR}/start_ollama.sh" ]; then
        echo "   ERROR: Ollama start script not found at ${OLLAMA_DIR}/start_ollama.sh"
        echo ""
        echo "   To use local LLMs, you need:"
        echo "   1. Ollama installed at ${OLLAMA_DIR}"
        echo "   2. Or switch to a cloud provider (openrouter, openai, anthropic)"
        echo ""
        return 1
    fi

    echo "   Starting Ollama server..."
    echo "   Ollama log: ${OLLAMA_LOG_FILE}"

    # Determine per-job serve log name
    OLLAMA_SERVE_LOG="${OLLAMA_DIR}/ollama_serve_${SLURM_JOB_ID:-default}.log"

    # Start Ollama with logging - capture stdout and stderr
    {
        echo "=============================================="
        echo "Ollama Server Log"
        echo "=============================================="
        echo "Started: $(date)"
        echo "Provider: ${LLM_PROVIDER}"
        echo "Model: ${LLM_MODEL}"
        echo "Port: ${OLLAMA_PORT}"
        echo "Host: $(hostname)"
        if [ -n "$SLURM_JOB_ID" ]; then
            echo "SLURM Job ID: ${SLURM_JOB_ID}"
            echo "OLLAMA_HOME: ${OLLAMA_HOME}"
            echo "OLLAMA_PID_FILE: ${OLLAMA_PID_FILE}"
        fi
        echo "=============================================="
        echo ""
    } > "${OLLAMA_LOG_FILE}"

    # Export OLLAMA_SERVE_LOG so start_ollama.sh can use it
    export OLLAMA_SERVE_LOG

    # Start Ollama in background with output redirected to log
    "${OLLAMA_DIR}/start_ollama.sh" >> "${OLLAMA_LOG_FILE}" 2>&1 &
    OLLAMA_START_PID=$!

    # Wait for the start script to complete
    wait $OLLAMA_START_PID 2>/dev/null || true

    # Wait for Ollama to be ready (up to 60 seconds)
    echo "   Waiting for Ollama to be ready..."
    OLLAMA_READY=0
    for i in {1..60}; do
        if curl -s "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
            OLLAMA_READY=1
            echo "   ✓ Ollama server is ready (waited ${i}s)"
            echo "[$(date)] Ollama server ready after ${i}s" >> "${OLLAMA_LOG_FILE}"
            break
        fi
        sleep 1
    done

    if [ $OLLAMA_READY -eq 0 ]; then
        echo "   ERROR: Ollama server failed to start within 60 seconds"
        echo "   Check logs at: ${OLLAMA_LOG_FILE}"
        echo "[$(date)] ERROR: Ollama server failed to start within 60 seconds" >> "${OLLAMA_LOG_FILE}"
        return 1
    fi

    OLLAMA_STARTED_BY_US=true

    # Set environment variables for the container
    export LLM_BASE_URL="http://$(hostname):${OLLAMA_PORT}"
    export OLLAMA_HOST="http://$(hostname):${OLLAMA_PORT}"

    echo "   LLM_BASE_URL: ${LLM_BASE_URL}"
    echo "   OLLAMA_HOST:  ${OLLAMA_HOST}"
    echo ""

    # Log endpoint info
    {
        echo ""
        echo "[$(date)] Endpoints configured:"
        echo "  LLM_BASE_URL: ${LLM_BASE_URL}"
        echo "  OLLAMA_HOST:  ${OLLAMA_HOST}"
        echo ""
    } >> "${OLLAMA_LOG_FILE}"

    # Show available models
    echo "   Available Ollama models:"
    curl -s "http://localhost:${OLLAMA_PORT}/api/tags" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    models = data.get('models', [])
    if models:
        for m in models:
            print(f\"     - {m.get('name', 'unknown')}\")
    else:
        print('     (no models installed)')
except:
    print('     (could not list models)')
" 2>/dev/null || echo "     (could not list models)"
    echo ""

    # Log available models
    {
        echo "[$(date)] Available models:"
        curl -s "http://localhost:${OLLAMA_PORT}/api/tags" 2>/dev/null || echo "  (could not retrieve)"
        echo ""
    } >> "${OLLAMA_LOG_FILE}"

    # Pre-warm the model if specified (blocking - wait for model to load)
    if [ -n "$LLM_MODEL" ]; then
        echo "   Pre-loading model: ${LLM_MODEL}..."
        echo "[$(date)] Pre-loading model: ${LLM_MODEL}" >> "${OLLAMA_LOG_FILE}"
        # This call blocks until the model is loaded into memory
        if curl -s "http://localhost:${OLLAMA_PORT}/api/generate" \
            -d "{\"model\": \"${LLM_MODEL}\", \"prompt\": \"Hello\", \"stream\": false}" \
            >> "${OLLAMA_LOG_FILE}" 2>&1; then
            echo "   ✓ Model preloaded successfully"
            echo "[$(date)] Model preloaded successfully" >> "${OLLAMA_LOG_FILE}"
        else
            echo "   Warning: Model pre-load may have failed"
            echo "[$(date)] Warning: Model pre-load may have failed" >> "${OLLAMA_LOG_FILE}"
        fi
    fi

    # Start background process to tail ollama serve log to our log file
    if [ -f "${OLLAMA_SERVE_LOG}" ]; then
        {
            echo ""
            echo "=============================================="
            echo "Ollama Server Output (from ${OLLAMA_SERVE_LOG})"
            echo "=============================================="
        } >> "${OLLAMA_LOG_FILE}"
        # Tail the per-job ollama_serve log in background
        tail -f "${OLLAMA_SERVE_LOG}" >> "${OLLAMA_LOG_FILE}" 2>&1 &
        OLLAMA_TAIL_PID=$!
    fi

    return 0
}

# Function to stop Ollama server (if we started it)
stop_ollama_server() {
    # Kill the tail process if running
    if [ -n "$OLLAMA_TAIL_PID" ]; then
        kill $OLLAMA_TAIL_PID 2>/dev/null || true
    fi

    if [ "$OLLAMA_STARTED_BY_US" = true ]; then
        echo ""
        echo "🦙 Stopping Ollama server (port ${OLLAMA_PORT})..."
        if [ -n "$OLLAMA_LOG_FILE" ]; then
            echo "[$(date)] Stopping Ollama server (port ${OLLAMA_PORT})..." >> "${OLLAMA_LOG_FILE}"
        fi

        if [ -n "$SLURM_JOB_ID" ] && [ -n "$OLLAMA_PID_FILE" ] && [ -f "$OLLAMA_PID_FILE" ]; then
            # Per-job cleanup: kill our specific process only
            local pid=$(cat "$OLLAMA_PID_FILE")
            echo "   Killing Ollama PID $pid (job-specific)..."
            kill $pid 2>/dev/null || true
            sleep 2
            kill -9 $pid 2>/dev/null || true
            rm -f "$OLLAMA_PID_FILE"
            # Clean up per-job monitor PID file too
            rm -f "${OLLAMA_PID_FILE%.pid}_monitor.pid"
        else
            # Interactive mode: use shared stop script
            if [ -f "${OLLAMA_DIR}/stop_ollama.sh" ]; then
                "${OLLAMA_DIR}/stop_ollama.sh" 2>/dev/null || true
            fi
        fi

        if [ -n "$OLLAMA_LOG_FILE" ]; then
            echo "[$(date)] Ollama server stopped." >> "${OLLAMA_LOG_FILE}"
        fi
        echo "   Done."
    fi
}

# Start Ollama if needed
if is_local_llm_provider "$LLM_PROVIDER"; then
    if ! start_ollama_server; then
        echo "ERROR: Failed to start Ollama server"
        exit 1
    fi
fi

# Validate SSL certificate path
if [ -n "$HOST_SSL_CERT" ] && [ ! -f "$HOST_SSL_CERT" ]; then
    echo "WARNING: SSL certificate not found at ${HOST_SSL_CERT}"
    echo "         (specified in .env file)"
    echo "         API calls may fail with SSL errors"
    echo ""
    # Clear the variable so we don't try to bind a non-existent file
    HOST_SSL_CERT=""
fi

echo ""
echo "=============================================="
echo "Starting Harmonia (Beaker Dev Mode)"
echo "=============================================="
echo ""
echo "📁 Using .env file: ${ENV_FILE}"
echo ""
echo "🤖 LLM Configuration:"
echo "   LLM_SERVICE_PROVIDER:     ${LLM_PROVIDER}"
echo "   LLM_SERVICE_MODEL:        ${LLM_MODEL}"
echo "   Ollama Port:              ${OLLAMA_PORT}"
# Read additional LLM config from .env
LLM_IMPORT_PATH=$(grep "^LLM_PROVIDER_IMPORT_PATH=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
LLM_TEMPERATURE=$(grep "^LLM_TEMPERATURE=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
LLM_MAX_TOKENS=$(grep "^LLM_MAX_TOKENS=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
OPENROUTER_KEY=$(grep "^OPENROUTER_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
OPENAI_KEY=$(grep "^OPENAI_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
ANTHROPIC_KEY=$(grep "^ANTHROPIC_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2)
echo "   LLM_PROVIDER_IMPORT_PATH: ${LLM_IMPORT_PATH:-auto-detected}"
echo "   LLM_TEMPERATURE:          ${LLM_TEMPERATURE:-0.0}"
echo "   LLM_MAX_TOKENS:           ${LLM_MAX_TOKENS:-4096}"
echo ""
echo "   API Keys configured:"
if [ -n "$OPENROUTER_KEY" ] && [ "$OPENROUTER_KEY" != "your_openrouter_api_key_here" ]; then
    echo "     OPENROUTER_API_KEY:     ${OPENROUTER_KEY:0:20}..."
fi
if [ -n "$OPENAI_KEY" ] && [ "$OPENAI_KEY" != "your_openai_api_key_here" ]; then
    echo "     OPENAI_API_KEY:         ${OPENAI_KEY:0:20}..."
fi
if [ -n "$ANTHROPIC_KEY" ] && [ "$ANTHROPIC_KEY" != "your_anthropic_api_key_here" ]; then
    echo "     ANTHROPIC_API_KEY:      ${ANTHROPIC_KEY:0:20}..."
fi
echo ""
echo "📡 STEP 1: Set up SSH tunnel on your Mac"
echo "   Open Terminal and run:"
echo "   ssh -l dstoker hpcs05.op.umcutrecht.nl -D ${PORT}"
echo ""
echo "🦊 STEP 2: Configure FoxyProxy in Firefox"
echo "   1. Open a NEW Firefox window"
echo "   2. Click FoxyProxy icon in toolbar"
echo "   3. Ensure proxy is configured:"
echo "      - Type: SOCKS5 (or SOCKS4)"
echo "      - Hostname: localhost"
echo "      - Port: ${PORT}"
echo "   4. Enable/activate the proxy"
echo ""
echo "🌐 STEP 3: Access Harmonia"
echo "   In the Firefox window with FoxyProxy active:"
if [ -n "$EXPERIMENT_NAME" ] && [ "$EXPERIMENT_NAME" != "unnamed" ]; then
    echo "   http://${HOSTNAME}:${PORT}/?token=${TOKEN}&experiment=${EXPERIMENT_NAME}"
else
    echo "   http://${HOSTNAME}:${PORT}/?token=${TOKEN}"
fi
echo ""
echo "=============================================="
echo ""
echo "📚 Example Usage:"
echo "   See harmonization of dou.csv (as shown in paper):"
echo "   Paper: https://arxiv.org/pdf/2502.07132"
echo "   Demo:  https://www.youtube.com/watch?v=D25x0B_xs3c"
echo ""
echo "Features:"
echo "  ✓ Auto-reload on code changes"
echo "  ✓ Full Beaker AI agent capabilities"
echo "  ✓ Harmonia data harmonization tools"
echo "  ✓ Multi-provider LLM support (OpenAI, OpenRouter, Anthropic, Ollama, etc.)"
echo ""

if [ -n "$HOST_SSL_CERT" ]; then
    echo "🔐 SSL Certificates: ${HOST_SSL_CERT}"
    echo ""
fi

# =============================================================================
# Determine which Apptainer image to use
# =============================================================================
# Priority order:
# 1. --image argument
# 2. harmonia_beaker_LLM_agent_environment_apptainer.sif (new, with any-llm)
# 3. jupyter.sif (legacy)

if [ -z "$SIF_IMAGE" ]; then
    if [ -f "${SCRIPT_DIR}/harmonia_beaker_LLM_agent_environment_apptainer.sif" ]; then
        SIF_IMAGE="${SCRIPT_DIR}/harmonia_beaker_LLM_agent_environment_apptainer.sif"
        echo "📦 Using new Harmonia image (with any-llm support)"
    elif [ -f "${SCRIPT_DIR}/jupyter.sif" ]; then
        SIF_IMAGE="${SCRIPT_DIR}/jupyter.sif"
        echo "📦 Using legacy jupyter.sif image"
        echo "   Note: For anyllm:* providers, build the new image:"
        echo "         ./build_harmonia_apptainer.sh"
    else
        echo "ERROR: No Apptainer image found!"
        echo "Expected: ${SCRIPT_DIR}/harmonia_beaker_LLM_agent_environment_apptainer.sif"
        echo "      or: ${SCRIPT_DIR}/jupyter.sif"
        echo ""
        echo "Build with: ./build_harmonia_apptainer.sh"
        exit 1
    fi
else
    if [ ! -f "$SIF_IMAGE" ]; then
        echo "ERROR: Specified image not found: $SIF_IMAGE"
        exit 1
    fi
    echo "📦 Using specified image: $SIF_IMAGE"
fi
echo ""

# =============================================================================
# Build apptainer command
# =============================================================================
APPTAINER_CMD="apptainer exec"

# =============================================================================
# Container binding strategy:
# - The container has source code baked in at /jupyter (from build)
# - We create /workspace as the working directory for the LLM
# - /workspace/data → datasets (read-only)
# - /workspace/results → experiment results (read-write)
# - Beaker runs from /workspace (clean environment for LLM)
# =============================================================================

# Create workspace directory on host (will be bound into container)
WORKSPACE_HOST_DIR="${SCRIPT_DIR}/workspace_mount"
mkdir -p "$WORKSPACE_HOST_DIR"

# Bind workspace structure into container
# We bind to /workspace which becomes the working directory
APPTAINER_CMD="$APPTAINER_CMD --bind ${DATA_BASE_DIR}:/workspace/data:ro"
APPTAINER_CMD="$APPTAINER_CMD --bind ${RESULTS_DIR}:/workspace/results"
APPTAINER_CMD="$APPTAINER_CMD --pwd /workspace"

echo "📂 Workspace structure (LLM working directory):"
echo "   /workspace/           ← pwd (working directory)"
echo "   ├── data/    → ${DATA_BASE_DIR} (read-only)"
echo "   └── results/ → ${RESULTS_DIR} (read-write)"
echo ""
echo "   Example paths for LLM:"
echo "   - Input:  data/one_metadata_table_gdc_schema/data/dou.csv"
echo "   - Output: results/"
echo ""
echo "   Or with absolute paths:"
echo "   - Input:  /workspace/data/one_metadata_table_gdc_schema/data/dou.csv"
echo "   - Output: /workspace/results/"

# Add SSL cert binding if available
if [ -n "$HOST_SSL_CERT" ]; then
    APPTAINER_CMD="$APPTAINER_CMD --bind ${HOST_SSL_CERT}:${HOST_SSL_CERT}:ro"
fi

echo ""

# Create Beaker log file
if [ -n "$JOB_NAME" ]; then
    BEAKER_LOG_FILE="${LOGS_DIR}/${JOB_NAME}_beaker.log"
else
    BEAKER_LOG_FILE="${LOGS_DIR}/beaker_${TIMESTAMP}.log"
fi
echo "📝 Beaker log: ${BEAKER_LOG_FILE}"
echo ""

# Create runtime context mappings for contexts not baked into the image
# This allows new contexts (like code_context) to work without rebuilding
RUNTIME_CONTEXTS_DIR="${SCRIPT_DIR}/.runtime_contexts"
mkdir -p "${RUNTIME_CONTEXTS_DIR}"

# Create bdikit_context.json (from container)
cat > "${RUNTIME_CONTEXTS_DIR}/bdikit_context.json" << 'EOF'
{
    "slug": "bdikit_context",
    "package": "bdikit_context.context",
    "class_name": "BDIKitContext"
}
EOF

# Create code_context.json mapping
cat > "${RUNTIME_CONTEXTS_DIR}/code_context.json" << 'EOF'
{
    "slug": "code_context",
    "package": "code_context.context",
    "class_name": "CodeContext"
}
EOF

# Bind the runtime contexts to overlay the container's contexts dir
APPTAINER_CMD="$APPTAINER_CMD --bind ${RUNTIME_CONTEXTS_DIR}:/usr/local/share/beaker/contexts:ro"

# Bind src directory so code_context can be imported
# (bdikit_context is already installed in the container, but code_context needs this)
APPTAINER_CMD="$APPTAINER_CMD --bind ${SCRIPT_DIR}/src:/opt/harmonia_src:ro"
APPTAINER_CMD="$APPTAINER_CMD --env PYTHONPATH=/opt/harmonia_src:\${PYTHONPATH}"

# Generate custom.js for browser tab title (if experiment name is available)
if [ -n "$EXPERIMENT_NAME" ] && [ "$EXPERIMENT_NAME" != "unnamed" ]; then
    # Write custom.js into a subfolder next to the config file
    if [ -n "$CONFIG_FILE" ]; then
        CUSTOM_JS_DIR="$(cd "$(dirname "$CONFIG_FILE")" && pwd)/custom_js"
    else
        CUSTOM_JS_DIR="${SCRIPT_DIR}/.custom_js"
    fi
    mkdir -p "${CUSTOM_JS_DIR}"
    cat > "${CUSTOM_JS_DIR}/custom.js" << JSEOF
// Auto-generated by exec_apptainer_harmonia.sh
// Sets the browser tab title to the experiment name
(function() {
    var experimentName = "${EXPERIMENT_NAME}";
    document.title = experimentName;
    // Intercept any attempts by Beaker/Jupyter to overwrite the title
    var titleEl = document.querySelector('title');
    if (titleEl) {
        new MutationObserver(function() {
            if (document.title !== experimentName) {
                document.title = experimentName;
            }
        }).observe(titleEl, {childList: true, characterData: true, subtree: true});
    }
})();
JSEOF
    echo "🏷  Tab title: ${EXPERIMENT_NAME}"
    echo "   custom.js: ${CUSTOM_JS_DIR}/custom.js"
    # Bind into the container at Jupyter's custom.js location
    APPTAINER_CMD="$APPTAINER_CMD --bind ${CUSTOM_JS_DIR}:/root/.jupyter/custom:ro"
fi

APPTAINER_CMD="$APPTAINER_CMD --env-file ${ENV_FILE}"
APPTAINER_CMD="$APPTAINER_CMD --env JUPYTER_SERVER=http://localhost:${PORT}"
APPTAINER_CMD="$APPTAINER_CMD --env DATA_DIR=/workspace/data"
APPTAINER_CMD="$APPTAINER_CMD --env RESULTS_DIR=/workspace/results"
APPTAINER_CMD="$APPTAINER_CMD --env WORKSPACE_DIR=/workspace"

# Add Ollama environment variables if using local LLM
if [ -n "$LLM_BASE_URL" ]; then
    APPTAINER_CMD="$APPTAINER_CMD --env LLM_BASE_URL=${LLM_BASE_URL}"
fi
if [ -n "$OLLAMA_HOST" ]; then
    APPTAINER_CMD="$APPTAINER_CMD --env OLLAMA_HOST=${OLLAMA_HOST}"
fi

# =============================================================================
# Show the workspace directory tree as the LLM will see it (inside the container)
# =============================================================================
echo ""
echo "🗂  Workspace directory tree (as seen by the LLM inside the container):"
echo "   pwd = /workspace"
echo ""
apptainer exec \
    --bind ${DATA_BASE_DIR}:/workspace/data:ro \
    --bind ${RESULTS_DIR}:/workspace/results \
    --pwd /workspace \
    ${SIF_IMAGE} \
    find /workspace -maxdepth 4 2>/dev/null | sort | sed 's|^|   |' \
    || echo "   (could not list workspace)"
echo ""

APPTAINER_CMD="$APPTAINER_CMD ${SIF_IMAGE}"
APPTAINER_CMD="$APPTAINER_CMD beaker dev watch --ip 0.0.0.0 --port $PORT"

# Run based on mode
if [ "$MONITOR_MODE" = true ]; then
    echo "🔍 Monitor mode enabled - logging all interactions"
    echo ""

    # Start Beaker server in background, logging to file
    eval $APPTAINER_CMD 2>&1 | tee -a "${BEAKER_LOG_FILE}" &
    BEAKER_PID=$!

    # Trap to clean up Beaker and Ollama when monitor exits
    cleanup() {
        echo ""
        echo "Shutting down Beaker server (PID: $BEAKER_PID)..."
        kill $BEAKER_PID 2>/dev/null || true
        wait $BEAKER_PID 2>/dev/null || true
        stop_ollama_server
        echo "Done."
    }
    trap cleanup EXIT INT TERM

    # Wait for server to be ready
    echo "Waiting for Beaker server to start..."
    sleep 5

    # Check if server is running
    for i in {1..30}; do
        if curl -s "http://localhost:${PORT}/api/sessions" -H "Authorization: token ${TOKEN}" >/dev/null 2>&1; then
            echo "Beaker server is ready!"
            break
        fi
        if ! kill -0 $BEAKER_PID 2>/dev/null; then
            echo "ERROR: Beaker server failed to start"
            exit 1
        fi
        echo "  Waiting... ($i/30)"
        sleep 2
    done

    # Start the monitor in foreground
    echo ""
    echo "Starting experiment monitor..."
    echo ""

    # Export environment variables for the monitor
    export JUPYTER_SERVER="http://localhost:${PORT}"
    export JUPYTER_TOKEN="${TOKEN}"

    # Run the monitor (this blocks until Ctrl+C)
    # Pass --output-dir to use experiment-specific results directory
    # Use apptainer to run the monitor with the same Python environment as Beaker
    # (host Python may be too old - needs Python 3.7+ for dataclasses)
    CONFIG_REL_PATH=$(realpath --relative-to="${SCRIPT_DIR}" "$CONFIG_FILE")
    apptainer exec \
        --bind "${SCRIPT_DIR}:/harmonia:ro" \
        --bind "${RESULTS_DIR}:/results" \
        ${SIF_IMAGE} \
        python3 /harmonia/run_manual_experiment.py \
        --config "/harmonia/${CONFIG_REL_PATH}" \
        --server "http://localhost:${PORT}" \
        --token "$TOKEN" \
        --output-dir "/results"

else
    # Run with beaker dev watch (keeps auto-reload) - normal mode
    # Set up cleanup trap for Ollama
    cleanup_normal() {
        stop_ollama_server
    }
    trap cleanup_normal EXIT INT TERM

    # Run Beaker, logging to file while also showing in terminal
    eval $APPTAINER_CMD 2>&1 | tee -a "${BEAKER_LOG_FILE}"
fi
