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
#
# =============================================================================

set -e

# Get script directory (where harmonia is installed)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
HOSTNAME=$(hostname)

# Parse arguments
PORT=8100
ENV_FILE=""
CONFIG_FILE=""
MONITOR_MODE=false

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
echo "   http://${HOSTNAME}:${PORT}/?token=${TOKEN}"
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

# Build apptainer command
APPTAINER_CMD="apptainer exec"
APPTAINER_CMD="$APPTAINER_CMD --bind .:/jupyter"
APPTAINER_CMD="$APPTAINER_CMD --pwd /jupyter"

# Add SSL cert binding if available
if [ -n "$HOST_SSL_CERT" ]; then
    APPTAINER_CMD="$APPTAINER_CMD --bind ${HOST_SSL_CERT}:${HOST_SSL_CERT}:ro"
fi

APPTAINER_CMD="$APPTAINER_CMD --env-file ${ENV_FILE}"
APPTAINER_CMD="$APPTAINER_CMD --env JUPYTER_SERVER=http://localhost:${PORT}"
APPTAINER_CMD="$APPTAINER_CMD ${SCRIPT_DIR}/jupyter.sif"
APPTAINER_CMD="$APPTAINER_CMD beaker dev watch --ip 0.0.0.0 --port $PORT"

# Run based on mode
if [ "$MONITOR_MODE" = true ]; then
    echo "🔍 Monitor mode enabled - logging all interactions"
    echo ""

    # Start Beaker server in background
    eval $APPTAINER_CMD &
    BEAKER_PID=$!

    # Trap to clean up Beaker when monitor exits
    cleanup() {
        echo ""
        echo "Shutting down Beaker server (PID: $BEAKER_PID)..."
        kill $BEAKER_PID 2>/dev/null || true
        wait $BEAKER_PID 2>/dev/null || true
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
    python3 "${SCRIPT_DIR}/run_manual_experiment.py" \
        --config "$CONFIG_FILE" \
        --server "http://localhost:${PORT}" \
        --token "$TOKEN"

else
    # Run with beaker dev watch (keeps auto-reload) - normal mode
    eval $APPTAINER_CMD
fi
