#!/bin/bash
# =============================================================================
# Harmonia Execution Script (Apptainer)
# =============================================================================
#
# Usage:
#   ./exec_apptainer_harmonia.sh           # Default port 8100
#   ./exec_apptainer_harmonia.sh 8101      # Custom port
#   ./exec_apptainer_harmonia.sh --port 8101
#
# =============================================================================

set -e

# Configuration
HOSTNAME=$(hostname)

# Parse port argument (supports both positional and --port flag)
PORT=8100
while [[ $# -gt 0 ]]; do
    case $1 in
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        [0-9]*)
            PORT="$1"
            shift
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: $0 [--port PORT] [PORT]"
            exit 1
            ;;
    esac
done

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo ""
    echo "Please create a .env file with your API keys."
    echo "You can copy .env.template and fill in your keys:"
    echo "  cp .env.template .env"
    echo "  nano .env  # or use your preferred editor"
    echo ""
    exit 1
fi

# Read TOKEN from .env file if not set
if [ -z "$TOKEN" ]; then
    TOKEN=$(grep "^JUPYTER_TOKEN=" .env | cut -d '=' -f2)
fi

# Read SSL_CERT_FILE from .env
HOST_SSL_CERT=$(grep "^SSL_CERT_FILE=" .env | cut -d '=' -f2)

# Read LLM configuration from .env for display
LLM_PROVIDER=$(grep "^LLM_SERVICE_PROVIDER=" .env | cut -d '=' -f2)
LLM_MODEL=$(grep "^LLM_SERVICE_MODEL=" .env | cut -d '=' -f2)

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
echo "🤖 LLM Configuration (from .env):"
echo "   LLM_SERVICE_PROVIDER:     ${LLM_PROVIDER}"
echo "   LLM_SERVICE_MODEL:        ${LLM_MODEL}"
# Read additional LLM config from .env
LLM_IMPORT_PATH=$(grep "^LLM_PROVIDER_IMPORT_PATH=" .env 2>/dev/null | cut -d '=' -f2)
LLM_TEMPERATURE=$(grep "^LLM_TEMPERATURE=" .env 2>/dev/null | cut -d '=' -f2)
LLM_MAX_TOKENS=$(grep "^LLM_MAX_TOKENS=" .env 2>/dev/null | cut -d '=' -f2)
OPENROUTER_KEY=$(grep "^OPENROUTER_API_KEY=" .env 2>/dev/null | cut -d '=' -f2)
OPENAI_KEY=$(grep "^OPENAI_API_KEY=" .env 2>/dev/null | cut -d '=' -f2)
ANTHROPIC_KEY=$(grep "^ANTHROPIC_API_KEY=" .env 2>/dev/null | cut -d '=' -f2)
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

APPTAINER_CMD="$APPTAINER_CMD --env-file .env"
APPTAINER_CMD="$APPTAINER_CMD --env JUPYTER_SERVER=http://localhost:${PORT}"
APPTAINER_CMD="$APPTAINER_CMD jupyter.sif"
APPTAINER_CMD="$APPTAINER_CMD beaker dev watch --ip 0.0.0.0 --port $PORT"

# Run with beaker dev watch (keeps auto-reload)
eval $APPTAINER_CMD
