# #!/bin/bash

# echo "========== ENVIRONMENT DIAGNOSTICS =========="
# echo "TMPDIR: $TMPDIR"
# echo "SLURM_JOB_ID: $SLURM_JOB_ID"
# echo "HOME: $HOME"

# if [ -z "$TMPDIR" ]; then
#     echo "ERROR: TMPDIR is not set!"
#     exit 1
# fi

# export APPTAINER_TMPDIR=$TMPDIR
# export APPTAINER_CACHEDIR=$TMPDIR

# # DEFINE SANDBOX_DIR!
# SANDBOX_DIR=$TMPDIR/sandbox

# echo "SANDBOX_DIR: $SANDBOX_DIR"

# # Clean up any previous attempt
# rm -rf $SANDBOX_DIR
# rm -f jupyter.sif

# echo "========== BUILDING SANDBOX =========="
# apptainer build --sandbox $SANDBOX_DIR jupyter.def

# # Check if sandbox looks valid
# echo "========== CHECKING SANDBOX =========="
# if [ -f "$SANDBOX_DIR/bin/sh" ]; then
#     echo "✓ /bin/sh exists in sandbox"
# else
#     echo "✗ /bin/sh missing - build failed!"
#     ls -la $SANDBOX_DIR/
#     exit 1
# fi

# echo "========== CONVERTING TO SIF =========="
# apptainer build jupyter.sif $SANDBOX_DIR

# echo "========== VERIFYING SIF =========="
# apptainer exec jupyter.sif ls -la /bin/sh
# apptainer exec jupyter.sif python --version

# echo "========== DONE =========="
# ls -lh jupyter.sif

# # Clean up sandbox
# rm -rf $SANDBOX_DIR

#!/bin/bash
# build_apptainer_diagnostic.sh
# Comprehensive diagnostic build script with ACTUAL package size checking

set -e

echo "=============================================="
echo "DIAGNOSTIC APPTAINER BUILD SCRIPT"
echo "=============================================="
echo ""

# ============================================
# PHASE 1: Environment Diagnostics
# ============================================
echo "========== PHASE 1: ENVIRONMENT =========="
echo "Date: $(date)"
echo "TMPDIR: $TMPDIR"
echo "SLURM_JOB_ID: $SLURM_JOB_ID"
echo "HOME: $HOME"
echo "PWD: $(pwd)"
echo ""

if [ -z "$TMPDIR" ]; then
    echo "ERROR: TMPDIR is not set! Run this inside an srun allocation."
    exit 1
fi

# ============================================
# PHASE 2: Space Diagnostics
# ============================================
echo "========== PHASE 2: CURRENT SPACE =========="

echo "--- Scratch space ($TMPDIR) ---"
df -h $TMPDIR
AVAILABLE_GB=$(df -BG $TMPDIR | tail -1 | awk '{print $4}' | sed 's/G//')
echo "Available: ${AVAILABLE_GB}GB"
echo ""

echo "--- Home directory ---"
df -h $HOME
echo ""

# ============================================
# PHASE 3: Calculate ACTUAL Package Sizes
# ============================================
echo "========== PHASE 3: CALCULATING ACTUAL PACKAGE SIZES =========="

# Create a Python script to query PyPI for package sizes
cat > /tmp/check_package_sizes.py << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
"""
Query PyPI API to get actual package download sizes.
"""
import urllib.request
import json
import sys

# Key packages that are large (PyTorch + CUDA ecosystem)
# These are the main space consumers
PACKAGES = [
    # PyTorch and CUDA
    ("torch", "2.9.1"),
    ("triton", "3.5.1"),
    ("nvidia-cublas-cu12", "12.8.4.1"),
    ("nvidia-cudnn-cu12", "9.10.2.21"),
    ("nvidia-cuda-nvrtc-cu12", "12.8.93"),
    ("nvidia-cuda-runtime-cu12", "12.8.90"),
    ("nvidia-cuda-cupti-cu12", "12.8.90"),
    ("nvidia-cufft-cu12", "11.3.3.83"),
    ("nvidia-curand-cu12", "10.3.9.90"),
    ("nvidia-cusolver-cu12", "11.7.3.90"),
    ("nvidia-cusparse-cu12", "12.5.8.93"),
    ("nvidia-cusparselt-cu12", "0.7.1"),
    ("nvidia-nccl-cu12", "2.27.5"),
    ("nvidia-nvjitlink-cu12", "12.8.93"),
    ("nvidia-nvtx-cu12", "12.8.90"),
    ("nvidia-cufile-cu12", "1.13.1.3"),
    ("nvidia-nvshmem-cu12", "3.3.20"),
    # ML packages
    ("transformers", None),
    ("tokenizers", None),
    ("safetensors", None),
    ("accelerate", None),
    # Scientific
    ("scipy", "1.12.0"),
    ("numpy", "1.26.4"),
    ("pandas", None),
    ("scikit-learn", None),
    ("matplotlib", "3.8.4"),
    # Flair and NLP
    ("flair", None),
    ("gensim", None),
    ("nltk", None),
    # Other significant packages
    ("pillow", None),
    ("lxml", None),
    ("cryptography", None),
]

def get_package_size(package_name, version=None):
    """Query PyPI JSON API for package size."""
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        # Get the specific version or latest
        if version and version in data.get("releases", {}):
            releases = data["releases"][version]
        else:
            releases = data.get("urls", [])
        
        # Find the manylinux x86_64 wheel (most common for these packages)
        for release in releases:
            filename = release.get("filename", "")
            if "manylinux" in filename and "x86_64" in filename and filename.endswith(".whl"):
                return release.get("size", 0), filename
        
        # Fallback to any wheel
        for release in releases:
            if release.get("filename", "").endswith(".whl"):
                return release.get("size", 0), release.get("filename", "")
        
        # Fallback to first available
        if releases:
            return releases[0].get("size", 0), releases[0].get("filename", "")
        
        return 0, "not found"
    except Exception as e:
        return 0, f"error: {e}"

def format_size(size_bytes):
    """Format bytes to human readable."""
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.2f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"

def main():
    print("Querying PyPI for actual package sizes...")
    print("-" * 70)
    print(f"{'Package':<35} {'Version':<12} {'Size':>12}")
    print("-" * 70)
    
    total_size = 0
    results = []
    
    for package, version in PACKAGES:
        size, filename = get_package_size(package, version)
        total_size += size
        version_str = version if version else "latest"
        results.append((package, version_str, size, filename))
        print(f"{package:<35} {version_str:<12} {format_size(size):>12}")
    
    print("-" * 70)
    print(f"{'TOTAL DOWNLOAD SIZE':<35} {'':<12} {format_size(total_size):>12}")
    print()
    
    # Estimate extraction overhead
    # Wheels typically expand 1.5-2x when extracted
    # Plus pip/uv temp files during install
    extraction_overhead = total_size * 2.5
    
    # Base image size
    base_image_size = 1024**3  # ~1GB for python:3.10
    
    # Total recommended
    total_recommended = total_size + extraction_overhead + base_image_size
    
    print("=" * 70)
    print("SPACE REQUIREMENTS ESTIMATE")
    print("=" * 70)
    print(f"  Download size:              {format_size(total_size):>12}")
    print(f"  Extraction overhead (2.5x): {format_size(int(extraction_overhead)):>12}")
    print(f"  Base image:                 {format_size(base_image_size):>12}")
    print(f"  Safety buffer (20%):        {format_size(int(total_recommended * 0.2)):>12}")
    print("-" * 70)
    print(f"  MINIMUM RECOMMENDED:        {format_size(int(total_recommended * 1.2)):>12}")
    print()
    
    # Return total in GB for bash script
    total_gb = (total_recommended * 1.2) / (1024**3)
    print(f"REQUIRED_GB={int(total_gb + 1)}")

if __name__ == "__main__":
    main()
PYTHON_SCRIPT

# Run the package size checker
echo ""
python3 /tmp/check_package_sizes.py | tee /tmp/package_sizes.txt
echo ""

# Extract the required GB
REQUIRED_GB=$(grep "REQUIRED_GB=" /tmp/package_sizes.txt | cut -d= -f2)
echo "========== SPACE COMPARISON =========="
echo "Available scratch space: ${AVAILABLE_GB}GB"
echo "Required space:          ${REQUIRED_GB}GB"
echo ""

if [ "$AVAILABLE_GB" -lt "$REQUIRED_GB" ]; then
    echo "⚠️  WARNING: Insufficient space!"
    echo "   You have ${AVAILABLE_GB}GB but need ~${REQUIRED_GB}GB"
    echo "   Request more with: --gres=tmpspace:${REQUIRED_GB}G"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborting."
        exit 1
    fi
else
    echo "✓ Sufficient space available"
fi
echo ""

# ============================================
# PHASE 4: Setup Build Environment
# ============================================
echo "========== PHASE 4: SETUP =========="

export APPTAINER_TMPDIR=$TMPDIR
export APPTAINER_CACHEDIR=$TMPDIR

SANDBOX_DIR=$TMPDIR/sandbox
BUILD_TMP=$TMPDIR/build_tmp

echo "APPTAINER_TMPDIR: $APPTAINER_TMPDIR"
echo "APPTAINER_CACHEDIR: $APPTAINER_CACHEDIR"
echo "SANDBOX_DIR: $SANDBOX_DIR"
echo "BUILD_TMP: $BUILD_TMP"
echo ""

# Clean up previous attempts
echo "Cleaning previous builds..."
rm -rf $SANDBOX_DIR
rm -rf $BUILD_TMP
rm -f jupyter.sif

# Create build temp directory
mkdir -p $BUILD_TMP
echo "Created $BUILD_TMP"

# Check space after cleanup
echo ""
echo "Space after cleanup:"
df -h $TMPDIR
echo ""

# ============================================
# PHASE 5: Build with Bind Mount
# ============================================
echo "========== PHASE 5: BUILDING SANDBOX =========="
echo "Using --bind to mount scratch as container's /tmp"
echo "Command: apptainer build --sandbox --bind $BUILD_TMP:/tmp $SANDBOX_DIR jupyter.def"
echo ""

# Monitor space usage during build in background
(
    while true; do
        sleep 30
        echo "[SPACE MONITOR] $(date +%H:%M:%S) - Scratch: $(df -h $TMPDIR | tail -1 | awk '{print $4}') free, Build tmp: $(du -sh $BUILD_TMP 2>/dev/null | cut -f1)"
    done
) &
MONITOR_PID=$!

# Trap to kill monitor on exit
trap "kill $MONITOR_PID 2>/dev/null" EXIT

# The key fix: bind mount scratch space to /tmp inside container
apptainer build --sandbox --bind $BUILD_TMP:/tmp $SANDBOX_DIR jupyter.def

# Stop the monitor
kill $MONITOR_PID 2>/dev/null || true

# ============================================
# PHASE 6: Verify Sandbox
# ============================================
echo "========== PHASE 6: VERIFY SANDBOX =========="

if [ -f "$SANDBOX_DIR/bin/sh" ]; then
    echo "✓ /bin/sh exists"
else
    echo "✗ /bin/sh missing!"
    echo "Sandbox contents:"
    ls -la $SANDBOX_DIR/ 2>/dev/null || echo "Sandbox directory doesn't exist"
    exit 1
fi

if [ -f "$SANDBOX_DIR/usr/local/bin/python3" ]; then
    echo "✓ Python exists"
else
    echo "✗ Python missing!"
fi

echo ""
echo "Sandbox size:"
du -sh $SANDBOX_DIR
echo ""

echo "Build temp usage:"
du -sh $BUILD_TMP
echo ""

echo "Final space status:"
df -h $TMPDIR
echo ""

# ============================================
# PHASE 7: Convert to SIF
# ============================================
echo "========== PHASE 7: CONVERT TO SIF =========="
apptainer build jupyter.sif $SANDBOX_DIR

# ============================================
# PHASE 8: Final Verification
# ============================================
echo "========== PHASE 8: FINAL VERIFICATION =========="
echo "Testing SIF image..."

apptainer exec jupyter.sif /bin/sh -c "echo '✓ Shell works'"
apptainer exec jupyter.sif python --version && echo "✓ Python works"
apptainer exec jupyter.sif python -c "import sys; print(f'✓ Python path: {sys.executable}')"

echo ""
echo "Final image size:"
ls -lh jupyter.sif

echo ""
echo "Space usage after build:"
df -h $TMPDIR

# ============================================
# PHASE 9: Cleanup
# ============================================
echo "========== PHASE 9: CLEANUP =========="
rm -rf $SANDBOX_DIR
rm -rf $BUILD_TMP
rm -f /tmp/check_package_sizes.py
rm -f /tmp/package_sizes.txt
echo "Cleaned up temporary directories"

echo ""
echo "=============================================="
echo "BUILD COMPLETE"
echo "=============================================="