"""
Ollama launcher utilities: VRAM estimation and port calculation.

This module extracts Ollama-related logic from exec_apptainer_harmonia.sh into
Python so it can be tested, reused, and extended more easily. It serves as the
first incremental step toward replacing shell-script orchestration with Python.

Can be used as a library (import the functions) or as a CLI:

    python ollama_launcher.py estimate-vram --model devstral:latest --context 32768
    python ollama_launcher.py get-port --job-id 12345
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Model parameter lookup table
# ---------------------------------------------------------------------------
# Maps model name patterns (regex) to approximate parameter counts in billions.
# Used for offline VRAM estimation when nvidia-smi is not available (e.g., in
# unit tests, pre-flight checks, or scheduling decisions before GPU allocation).
#
# The patterns are matched case-insensitively against the model name. First
# match wins, so more specific patterns should come first.
#
# Sources: Ollama model library, model cards, community benchmarks.
# ---------------------------------------------------------------------------
MODEL_PARAMETERS: list[tuple[str, float]] = [
    # Devstral variants
    (r"devstral.*small", 14.0),
    (r"devstral", 24.0),
    # Qwen variants
    (r"qwen.*2\.5.*72b", 72.0),
    (r"qwen.*2\.5.*32b", 32.0),
    (r"qwen.*2\.5.*14b", 14.0),
    (r"qwen.*2\.5.*7b", 7.0),
    (r"qwen.*2\.5.*3b", 3.0),
    (r"qwen.*2\.5.*1\.5b", 1.5),
    (r"qwen.*2\.5.*0\.5b", 0.5),
    (r"qwen.*72b", 72.0),
    (r"qwen.*32b", 32.0),
    (r"qwen.*14b", 14.0),
    (r"qwen.*7b", 7.0),
    # Llama variants
    (r"llama.*3\.3.*70b", 70.0),
    (r"llama.*3\.1.*405b", 405.0),
    (r"llama.*3\.1.*70b", 70.0),
    (r"llama.*3\.1.*8b", 8.0),
    (r"llama.*3.*70b", 70.0),
    (r"llama.*3.*8b", 8.0),
    (r"llama.*70b", 70.0),
    (r"llama.*13b", 13.0),
    (r"llama.*8b", 8.0),
    (r"llama.*7b", 7.0),
    # Mistral / Mixtral
    (r"mixtral.*8x22b", 141.0),
    (r"mixtral.*8x7b", 46.7),
    (r"mistral.*large", 123.0),
    (r"mistral.*nemo", 12.0),
    (r"mistral.*small", 22.0),
    (r"mistral.*7b", 7.0),
    (r"mistral", 7.0),
    # Gemma variants
    (r"gemma.*27b", 27.0),
    (r"gemma.*9b", 9.0),
    (r"gemma.*2b", 2.0),
    # Phi variants
    (r"phi.*4.*14b", 14.0),
    (r"phi.*3.*14b", 14.0),
    (r"phi.*3.*mini", 3.8),
    # CodeLlama
    (r"codellama.*70b", 70.0),
    (r"codellama.*34b", 34.0),
    (r"codellama.*13b", 13.0),
    (r"codellama.*7b", 7.0),
    # Deepseek
    (r"deepseek.*coder.*v2.*236b", 236.0),
    (r"deepseek.*coder.*33b", 33.0),
    (r"deepseek.*coder.*6\.7b", 6.7),
    (r"deepseek.*coder.*1\.3b", 1.3),
    (r"deepseek.*67b", 67.0),
    (r"deepseek.*7b", 7.0),
    # Catch-all: try to extract a number followed by 'b' from the model name
]

# Approximate bytes-per-parameter for common quantizations.
# Default assumes Q4_K_M (~4.5 bits per parameter).
BYTES_PER_PARAM_DEFAULT = 0.5625  # 4.5 bits / 8 = 0.5625 bytes

# KV cache overhead per 1K context tokens (in GB).
# Conservative estimate from the original bash script.
KV_CACHE_GB_PER_1K_TOKENS = 0.25


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class VRAMEstimate:
    """Result of a VRAM estimation."""

    vram_gb: float
    model_params_b: float
    model_weight_gb: float
    kv_cache_gb: float
    recommendation: str

    def to_dict(self) -> dict:
        return {
            "vram_gb": round(self.vram_gb, 2),
            "model_params_b": self.model_params_b,
            "model_weight_gb": round(self.model_weight_gb, 2),
            "kv_cache_gb": round(self.kv_cache_gb, 2),
            "recommendation": self.recommendation,
        }


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _lookup_model_params(model_name: str) -> Optional[float]:
    """Look up approximate parameter count (billions) for a model name.

    Returns None if no match is found in the lookup table.
    """
    name_lower = model_name.lower()

    # Try the lookup table first
    for pattern, params_b in MODEL_PARAMETERS:
        if re.search(pattern, name_lower):
            return params_b

    # Fallback: try to extract a number followed by 'b' from the name
    match = re.search(r"(\d+(?:\.\d+)?)b", name_lower)
    if match:
        return float(match.group(1))

    return None


def estimate_vram_usage(model_name: str, context_length: int) -> dict:
    """Estimate VRAM usage for a given model and context length.

    This is the Python equivalent of the bash estimate_vram_usage() function
    in exec_apptainer_harmonia.sh. The bash version queries nvidia-smi for
    current GPU usage after model load; this Python version estimates from
    model parameters for pre-flight planning.

    Args:
        model_name: Ollama model name (e.g., "devstral:latest", "qwen2.5:32b")
        context_length: Number of context tokens (e.g., 8192, 32768, 65536)

    Returns:
        Dictionary with keys: vram_gb, model_params_b, model_weight_gb,
        kv_cache_gb, recommendation
    """
    params_b = _lookup_model_params(model_name)

    if params_b is None:
        # Unknown model -- return a conservative estimate with a warning
        return VRAMEstimate(
            vram_gb=0.0,
            model_params_b=0.0,
            model_weight_gb=0.0,
            kv_cache_gb=0.0,
            recommendation=f"Unknown model '{model_name}': cannot estimate VRAM. "
            "Check Ollama model library for parameter count.",
        ).to_dict()

    # Model weights in GB (assumes default Q4_K_M quantization)
    model_weight_gb = params_b * BYTES_PER_PARAM_DEFAULT

    # KV cache estimate (same formula as the bash version)
    kv_cache_gb = (context_length / 1024.0) * KV_CACHE_GB_PER_1K_TOKENS

    # Total estimated VRAM
    total_vram_gb = model_weight_gb + kv_cache_gb

    # Generate recommendation
    if total_vram_gb > 80:
        recommendation = (
            f"Estimated {total_vram_gb:.1f} GB VRAM needed. "
            "Requires multi-GPU or A100 80GB. "
            "Consider smaller quantization or model."
        )
    elif total_vram_gb > 48:
        recommendation = (
            f"Estimated {total_vram_gb:.1f} GB VRAM needed. "
            "Requires A100 80GB or similar high-end GPU."
        )
    elif total_vram_gb > 24:
        recommendation = (
            f"Estimated {total_vram_gb:.1f} GB VRAM needed. "
            "Requires A100 40GB or better."
        )
    elif total_vram_gb > 12:
        recommendation = (
            f"Estimated {total_vram_gb:.1f} GB VRAM needed. "
            "Should fit on a 24GB GPU (e.g., RTX 3090/4090)."
        )
    else:
        recommendation = (
            f"Estimated {total_vram_gb:.1f} GB VRAM needed. "
            "Should fit on most modern GPUs."
        )

    return VRAMEstimate(
        vram_gb=total_vram_gb,
        model_params_b=params_b,
        model_weight_gb=model_weight_gb,
        kv_cache_gb=kv_cache_gb,
        recommendation=recommendation,
    ).to_dict()


def get_ollama_port(job_id: Optional[int] = None) -> int:
    """Calculate a deterministic Ollama port for a given SLURM job ID.

    Replicates the bash logic:
        OLLAMA_PORT=$((11434 + 1 + (SLURM_JOB_ID % 200)))

    When no job_id is provided (interactive use), returns a random port
    in the range 11600-11800 to avoid collisions with other users.

    Args:
        job_id: SLURM job ID. If None, a random port is chosen.

    Returns:
        Port number for Ollama to listen on.
    """
    if job_id is not None:
        return 11434 + 1 + (job_id % 200)
    else:
        return random.randint(11600, 11800)


def estimate_vram_nvidia_smi(context_length: int) -> Optional[dict]:
    """Live VRAM estimation using nvidia-smi (like the original bash version).

    Queries the GPU for current memory usage (model assumed already loaded),
    then adds estimated KV cache overhead for the given context length.

    Returns None if nvidia-smi is not available.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        line = result.stdout.strip().split("\n")[0]
        total_mib, used_mib = (int(x.strip()) for x in line.split(","))

    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None

    total_gb = total_mib / 1024.0
    used_gb = used_mib / 1024.0
    free_gb = (total_mib - used_mib) / 1024.0
    usage_pct = int((used_mib * 100) / total_mib) if total_mib > 0 else 0

    kv_cache_gb = (context_length / 1024.0) * KV_CACHE_GB_PER_1K_TOKENS
    estimated_total_gb = used_gb + kv_cache_gb
    estimated_pct = int((estimated_total_gb * 1024 * 100) / total_mib) if total_mib > 0 else 0

    if estimated_pct >= 100:
        recommendation = (
            f"WARNING: Estimated peak VRAM (~{estimated_total_gb:.1f} GB) "
            f"EXCEEDS GPU VRAM (~{total_gb:.1f} GB)! "
            "Model will likely be partially offloaded to CPU RAM."
        )
    elif estimated_pct >= 80:
        recommendation = (
            f"WARNING: Estimated peak VRAM (~{estimated_total_gb:.1f} GB) is "
            f"~{estimated_pct}% of GPU VRAM. May cause instability."
        )
    else:
        recommendation = "OK: VRAM headroom looks adequate."

    return {
        "gpu_total_gb": round(total_gb, 1),
        "gpu_used_gb": round(used_gb, 1),
        "gpu_free_gb": round(free_gb, 1),
        "gpu_usage_pct": usage_pct,
        "kv_cache_gb": round(kv_cache_gb, 1),
        "estimated_total_gb": round(estimated_total_gb, 1),
        "estimated_pct": estimated_pct,
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def _cli_estimate_vram(args: argparse.Namespace) -> None:
    """CLI handler for 'estimate-vram' subcommand."""
    result = estimate_vram_usage(args.model, args.context)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    # Human-readable output (mimics the bash version's format)
    if result["vram_gb"] == 0.0:
        print(f"   (VRAM estimation: {result['recommendation']})")
        return

    print()
    print("   === VRAM Estimation (offline) ===")
    print(f"   Model:                   {args.model}")
    print(f"   Model parameters:        ~{result['model_params_b']}B")
    print(f"   Model weights (Q4_K_M):  ~{result['model_weight_gb']:.1f} GB")
    print(f"   KV cache (ctx={args.context}):  ~{result['kv_cache_gb']:.1f} GB")
    print(f"   Est. total VRAM:         ~{result['vram_gb']:.1f} GB")
    print(f"   {result['recommendation']}")
    print("   =================================")
    print()

    # If nvidia-smi is available, also show live GPU state
    live = estimate_vram_nvidia_smi(args.context)
    if live:
        print("   === VRAM Estimation (live GPU) ===")
        print(f"   GPU VRAM total:          ~{live['gpu_total_gb']} GB")
        print(f"   GPU VRAM used (current): ~{live['gpu_used_gb']} GB ({live['gpu_usage_pct']}%)")
        print(f"   GPU VRAM free:           ~{live['gpu_free_gb']} GB")
        print(f"   KV cache (ctx={args.context}):    ~{live['kv_cache_gb']} GB")
        print(f"   Est. peak usage:         ~{live['estimated_total_gb']} GB (~{live['estimated_pct']}%)")
        print(f"   {live['recommendation']}")
        print("   ==================================")
        print()


def _cli_get_port(args: argparse.Namespace) -> None:
    """CLI handler for 'get-port' subcommand."""
    job_id = None
    if args.job_id:
        try:
            job_id = int(args.job_id)
        except ValueError:
            # Non-numeric job ID (e.g., empty string) -> use random
            pass

    port = get_ollama_port(job_id)
    print(port)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Ollama launcher utilities: VRAM estimation and port calculation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # estimate-vram subcommand
    vram_parser = subparsers.add_parser(
        "estimate-vram",
        help="Estimate VRAM usage for a model and context length",
    )
    vram_parser.add_argument(
        "--model", required=True, help="Ollama model name (e.g., devstral:latest)",
    )
    vram_parser.add_argument(
        "--context", type=int, default=8192, help="Context length in tokens (default: 8192)",
    )
    vram_parser.add_argument(
        "--json", action="store_true", help="Output as JSON instead of human-readable",
    )
    vram_parser.set_defaults(func=_cli_estimate_vram)

    # get-port subcommand
    port_parser = subparsers.add_parser(
        "get-port",
        help="Calculate Ollama port for a SLURM job ID",
    )
    port_parser.add_argument(
        "--job-id", default=None, help="SLURM job ID (omit for random port)",
    )
    port_parser.set_defaults(func=_cli_get_port)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
