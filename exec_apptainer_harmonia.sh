#!/bin/bash
# # Configuration
# HOSTNAME=$(hostname)
# PORT=8100
# TOKEN=89f73481102c46c0bc13b2998f9a4fce

# echo ""
# echo "=============================================="
# echo "Starting Harmonia (Beaker Dev Mode)"
# echo "=============================================="
# echo ""
# echo "📡 STEP 1: Set up SSH tunnel on your Mac"
# echo "   Open Terminal and run:"
# echo "   ssh -l dstoker hpcs05.op.umcutrecht.nl -D ${PORT}"
# echo ""
# echo "🦊 STEP 2: Configure FoxyProxy in Firefox"
# echo "   1. Open a NEW Firefox window"
# echo "   2. Click FoxyProxy icon in toolbar"
# echo "   3. Ensure proxy is configured:"
# echo "      - Type: SOCKS5 (or SOCKS4)"
# echo "      - Hostname: localhost"
# echo "      - Port: ${PORT}"
# echo "   4. Enable/activate the proxy"
# echo ""
# echo "🌐 STEP 3: Access Harmonia"
# echo "   In the Firefox window with FoxyProxy active:"
# echo "   http://${HOSTNAME}:${PORT}/?token=${TOKEN}"
# echo ""
# echo "=============================================="
# echo ""
# echo "📚 Example Usage:"
# echo "   See harmonization of dou.csv (as shown in paper):"
# echo "   Paper: https://arxiv.org/pdf/2502.07132"
# echo "   Demo:  https://www.youtube.com/watch?v=D25x0B_xs3c"
# echo ""

# # Run with beaker dev watch (keeps auto-reload)
# # Note: We use apptainer exec to pass port argument
# apptainer exec \
# --bind .:/jupyter \
# --pwd /jupyter \
# --env DEBUG=1 \
# --env JUPYTER_SERVER="http://localhost:${PORT}" \
# --env JUPYTER_TOKEN=$TOKEN \
# --env ENABLE_USER_PROMPT=true \
# --env OPENAI_API_KEY="$OPENAI_API_KEY" \
# --env ENABLE_CHECKPOINTS=true \
# --env PYTHONPATH=/jupyter \
# --env SSL_CERT_FILE= \
# jupyter.sif \
# beaker dev watch --ip 0.0.0.0 --port $PORT



#!/bin/bash

# Configuration
HOSTNAME=$(hostname)
PORT=8100

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

echo ""
echo "=============================================="
echo "Starting Harmonia (Beaker Dev Mode)"
echo "=============================================="
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
echo ""

# Run with beaker dev watch (keeps auto-reload)
# Use --env-file to load API keys from .env
apptainer exec \
--bind .:/jupyter \
--pwd /jupyter \
--env-file .env \
--env JUPYTER_SERVER="http://localhost:${PORT}" \
jupyter.sif \
beaker dev watch --ip 0.0.0.0 --port $PORT