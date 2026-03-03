#!/bin/bash
# =============================================================================
# Ollama Management CLI for Harmonia Project
# =============================================================================
#
# Thin wrapper around the Ollama installation at the HPC shared directory.
# Provides install/update, model pull, and status commands without needing
# to remember the full path to the Ollama installation.
#
# Default install location:
#   /hpc/compgen/projects/ollama/ollama_run/analysis/dstoker
#
# Usage:
#   ./manage_ollama.sh install              # Install/update Ollama to latest version
#   ./manage_ollama.sh install --version 0.17.5  # Install specific version
#   ./manage_ollama.sh install --dry-run    # Preview what would happen
#   ./manage_ollama.sh pull <model>         # Pull a model (requires srun GPU session)
#   ./manage_ollama.sh list                 # List installed models (requires srun session)
#   ./manage_ollama.sh version              # Show installed Ollama version
#   ./manage_ollama.sh status               # Show install dir, version, model count
#
# Environment:
#   OLLAMA_INSTALL_DIR   Override the default install directory
#
# Note: 'pull' and 'list' require a running Ollama server. On the HPC,
# this means running inside an srun session. The script will start/stop
# Ollama automatically for pull operations.
# =============================================================================

set -euo pipefail

# --- Defaults ---

OLLAMA_INSTALL_DIR="${OLLAMA_INSTALL_DIR:-/hpc/compgen/projects/ollama/ollama_run/analysis/dstoker}"
OLLAMA_BIN="$OLLAMA_INSTALL_DIR/bin/ollama"
INSTALLER="$OLLAMA_INSTALL_DIR/ollama_installer_for_deridder_hpc_folder.sh"

# --- Helpers ---

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo ">>> $*"; }

check_binary() {
    [ -f "$OLLAMA_BIN" ] || die "Ollama binary not found at $OLLAMA_BIN. Run '$0 install' first."
}

# --- Commands ---

cmd_install() {
    if [ ! -f "$INSTALLER" ]; then
        die "Installer not found at $INSTALLER"
    fi
    info "Running Ollama installer at $OLLAMA_INSTALL_DIR"
    cd "$OLLAMA_INSTALL_DIR"
    exec "$INSTALLER" "$@"
}

cmd_pull() {
    [ $# -ge 1 ] || die "Usage: $0 pull <model> [model2 ...]"
    check_binary

    export OLLAMA_MODELS="$OLLAMA_INSTALL_DIR/ollama_models"
    export OLLAMA_HOST="0.0.0.0:11434"
    export OLLAMA_HOME="${TMPDIR:-/tmp}/ollama_pull_$$"
    mkdir -p "$OLLAMA_HOME"

    # Start Ollama server
    info "Starting Ollama server for model pull..."
    "$OLLAMA_BIN" serve &
    local serve_pid=$!
    sleep 5

    if ! kill -0 "$serve_pid" 2>/dev/null; then
        rm -rf "$OLLAMA_HOME"
        die "Failed to start Ollama server. Are you on a compute node (srun)?"
    fi

    local rc=0
    for model in "$@"; do
        info "Pulling $model ..."
        if "$OLLAMA_BIN" pull "$model"; then
            info "Successfully pulled $model"
        else
            echo "ERROR: Failed to pull $model" >&2
            rc=1
        fi
    done

    # Show updated list
    echo ""
    info "Installed models:"
    "$OLLAMA_BIN" list 2>/dev/null || true

    # Cleanup
    kill "$serve_pid" 2>/dev/null || true
    wait "$serve_pid" 2>/dev/null || true
    rm -rf "$OLLAMA_HOME"

    return $rc
}

cmd_list() {
    check_binary

    export OLLAMA_MODELS="$OLLAMA_INSTALL_DIR/ollama_models"
    export OLLAMA_HOST="0.0.0.0:11434"
    export OLLAMA_HOME="${TMPDIR:-/tmp}/ollama_list_$$"
    mkdir -p "$OLLAMA_HOME"

    "$OLLAMA_BIN" serve &
    local serve_pid=$!
    sleep 3

    if kill -0 "$serve_pid" 2>/dev/null; then
        "$OLLAMA_BIN" list
    else
        # Fallback: list model directories
        echo "Could not start server. Listing model manifests instead:"
        find "$OLLAMA_INSTALL_DIR/ollama_models/manifests" -name "latest" -o -name "*" -type f 2>/dev/null | head -50
    fi

    kill "$serve_pid" 2>/dev/null || true
    wait "$serve_pid" 2>/dev/null || true
    rm -rf "$OLLAMA_HOME"
}

cmd_version() {
    check_binary
    "$OLLAMA_BIN" --version 2>&1 | tail -1
}

cmd_status() {
    echo "Ollama Installation Status"
    echo "=========================="
    echo "Install dir:  $OLLAMA_INSTALL_DIR"

    if [ -f "$OLLAMA_BIN" ]; then
        local ver
        ver=$("$OLLAMA_BIN" --version 2>&1 | grep -oP 'is \K[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")
        echo "Version:      $ver"
    else
        echo "Version:      NOT INSTALLED"
    fi

    if [ -d "$OLLAMA_INSTALL_DIR/ollama_models/manifests" ]; then
        local n_models
        n_models=$(find "$OLLAMA_INSTALL_DIR/ollama_models/manifests" -mindepth 3 -maxdepth 3 -type d 2>/dev/null | wc -l)
        echo "Models:       $n_models installed"

        local total_size
        total_size=$(du -sh "$OLLAMA_INSTALL_DIR/ollama_models" 2>/dev/null | cut -f1)
        echo "Models size:  $total_size"
    else
        echo "Models:       none"
    fi

    # GPU backends
    echo ""
    echo "GPU backends:"
    for d in "$OLLAMA_INSTALL_DIR/lib/ollama"/cuda_* "$OLLAMA_INSTALL_DIR/lib/ollama"/vulkan; do
        [ -d "$d" ] && echo "  $(basename "$d")"
    done
}

# --- Main dispatch ---

show_help() {
    sed -n '/^# Usage:/,/^# =====/p' "$0" | grep -v '=====' | sed 's/^# \?//'
}

if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

COMMAND="$1"
shift

case "$COMMAND" in
    install|update)
        cmd_install "$@"
        ;;
    pull)
        cmd_pull "$@"
        ;;
    list|ls)
        cmd_list "$@"
        ;;
    version|--version|-v)
        cmd_version
        ;;
    status)
        cmd_status
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        die "Unknown command: $COMMAND. Use '$0 help' for usage."
        ;;
esac
