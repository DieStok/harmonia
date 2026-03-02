#!/bin/bash
# =============================================================================
# Build Script for Harmonia Beaker LLM Agent Environment Apptainer Image
# =============================================================================
#
# This script builds the harmonia_beaker_LLM_agent_environment_apptainer.sif
# container image with litellm support for unified LLM provider access.
#
# Usage:
#   # Interactive build (recommended for first time/debugging)
#   srun -J apptainer_build_claude-code --time=02:00:00 --mem=32G --gres=tmpspace:100G bash
#   ./build_harmonia_apptainer.sh
#
#   # Or submit as batch job
#   sbatch --job-name=apptainer_build --time=02:00:00 --mem=32G --gres=tmpspace:100G ./build_harmonia_apptainer.sh
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
DEF_FILE="harmonia_beaker_LLM_agent_environment_apptainer.def"
SIF_FILE="harmonia_beaker_LLM_agent_environment_apptainer.sif"

echo "=============================================="
echo "Harmonia Apptainer Build Script"
echo "=============================================="
echo ""

# ============================================
# Phase 1: Environment Diagnostics
# ============================================
echo "========== PHASE 1: ENVIRONMENT =========="
echo "Date: $(date)"
echo "TMPDIR: $TMPDIR"
echo "SLURM_JOB_ID: $SLURM_JOB_ID"
echo "HOME: $HOME"
echo "PWD: $(pwd)"
echo "DEF_FILE: $DEF_FILE"
echo "SIF_FILE: $SIF_FILE"
echo ""

if [ -z "$TMPDIR" ]; then
    echo "ERROR: TMPDIR is not set! Run this inside an srun allocation."
    echo ""
    echo "Example:"
    echo "  srun -J apptainer_build_claude-code --time=02:00:00 --mem=32G --gres=tmpspace:100G bash"
    echo "  ./build_harmonia_apptainer.sh"
    exit 1
fi

# Verify def file exists
if [ ! -f "$DEF_FILE" ]; then
    echo "ERROR: Definition file not found: $DEF_FILE"
    exit 1
fi

# ============================================
# Phase 2: Space Diagnostics
# ============================================
echo "========== PHASE 2: SPACE CHECK =========="

echo "--- Scratch space ($TMPDIR) ---"
df -h $TMPDIR
AVAILABLE_GB=$(df -BG $TMPDIR | tail -1 | awk '{print $4}' | sed 's/G//')
echo "Available: ${AVAILABLE_GB}GB"
echo ""

# Recommend at least 50GB for the build
REQUIRED_GB=50
if [ "$AVAILABLE_GB" -lt "$REQUIRED_GB" ]; then
    echo "WARNING: Low disk space!"
    echo "   You have ${AVAILABLE_GB}GB but recommend ~${REQUIRED_GB}GB"
    echo "   Request more with: --gres=tmpspace:${REQUIRED_GB}G"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborting."
        exit 1
    fi
else
    echo "Sufficient space available"
fi
echo ""

# ============================================
# Phase 3: Setup Build Environment
# ============================================
echo "========== PHASE 3: SETUP =========="

export APPTAINER_TMPDIR=$TMPDIR
export APPTAINER_CACHEDIR=$TMPDIR

SANDBOX_DIR=$TMPDIR/sandbox_harmonia
BUILD_TMP=$TMPDIR/build_tmp_harmonia

echo "APPTAINER_TMPDIR: $APPTAINER_TMPDIR"
echo "APPTAINER_CACHEDIR: $APPTAINER_CACHEDIR"
echo "SANDBOX_DIR: $SANDBOX_DIR"
echo "BUILD_TMP: $BUILD_TMP"
echo ""

# Clean up previous attempts
echo "Cleaning previous builds..."
rm -rf $SANDBOX_DIR
rm -rf $BUILD_TMP

# Backup existing sif if present
if [ -f "$SIF_FILE" ]; then
    BACKUP_FILE="${SIF_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backing up existing $SIF_FILE to $BACKUP_FILE"
    mv "$SIF_FILE" "$BACKUP_FILE"
fi

# Create build temp directory
mkdir -p $BUILD_TMP
echo "Created $BUILD_TMP"

# Check space after cleanup
echo ""
echo "Space after cleanup:"
df -h $TMPDIR
echo ""

# ============================================
# Phase 4: Build Sandbox
# ============================================
echo "========== PHASE 4: BUILDING SANDBOX =========="
echo "Using --bind to mount scratch as container's /tmp"
echo "Command: apptainer build --sandbox --bind $BUILD_TMP:/tmp $SANDBOX_DIR $DEF_FILE"
echo ""

# Monitor space usage during build in background
(
    while true; do
        sleep 60
        echo "[SPACE MONITOR] $(date +%H:%M:%S) - Scratch: $(df -h $TMPDIR | tail -1 | awk '{print $4}') free"
    done
) &
MONITOR_PID=$!

# Trap to kill monitor on exit
trap "kill $MONITOR_PID 2>/dev/null || true" EXIT

# Build the sandbox
apptainer build --sandbox --bind $BUILD_TMP:/tmp $SANDBOX_DIR $DEF_FILE

# Stop the monitor
kill $MONITOR_PID 2>/dev/null || true

# ============================================
# Phase 5: Verify Sandbox
# ============================================
echo "========== PHASE 5: VERIFY SANDBOX =========="

if [ -f "$SANDBOX_DIR/bin/sh" ]; then
    echo "Shell exists"
else
    echo "ERROR: /bin/sh missing!"
    ls -la $SANDBOX_DIR/ 2>/dev/null || echo "Sandbox directory doesn't exist"
    exit 1
fi

if [ -f "$SANDBOX_DIR/usr/local/bin/python3" ]; then
    echo "Python exists"
else
    echo "WARNING: Python not at expected location"
fi

echo ""
echo "Sandbox size:"
du -sh $SANDBOX_DIR
echo ""

echo "Testing key imports in sandbox..."
apptainer exec $SANDBOX_DIR python3 -c "from bdikit_context.llm.litellm_model import LiteLLMModel; print('LiteLLMModel: OK')" || echo "FAILED: LiteLLMModel import"
apptainer exec $SANDBOX_DIR python3 -c "import litellm; print('litellm: OK')" || echo "FAILED: litellm import"
apptainer exec $SANDBOX_DIR python3 -c "from bdikit_context.context import BDIKitContext; print('BDIKitContext: OK')" || echo "FAILED: BDIKitContext import"
echo ""

# ============================================
# Phase 6: Convert to SIF
# ============================================
echo "========== PHASE 6: CONVERT TO SIF =========="
apptainer build $SIF_FILE $SANDBOX_DIR

# ============================================
# Phase 7: Final Verification
# ============================================
echo "========== PHASE 7: FINAL VERIFICATION =========="
echo "Testing SIF image..."

apptainer exec $SIF_FILE /bin/sh -c "echo 'Shell works'"
apptainer exec $SIF_FILE python --version && echo "Python works"
apptainer exec $SIF_FILE python -c "from bdikit_context.llm.litellm_model import LiteLLMModel; print('LiteLLMModel import: OK')"
apptainer exec $SIF_FILE python -c "import litellm; print('litellm import: OK')"

echo ""
echo "Final image size:"
ls -lh $SIF_FILE

# ============================================
# Phase 8: Cleanup
# ============================================
echo "========== PHASE 8: CLEANUP =========="
rm -rf $SANDBOX_DIR
rm -rf $BUILD_TMP
echo "Cleaned up temporary directories"

echo ""
echo "=============================================="
echo "BUILD COMPLETE"
echo "=============================================="
echo ""
echo "Image: $SIF_FILE"
echo "Size: $(ls -lh $SIF_FILE | awk '{print $5}')"
echo ""
echo "To use:"
echo "  ./exec_apptainer_harmonia.sh --config configs/manual/dou_harmonization_manual_devstral-small.yaml"
