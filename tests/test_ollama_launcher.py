"""
Unit tests for src/automation/ollama_launcher.py.

Tests the VRAM estimation and port calculation functions that were extracted
from exec_apptainer_harmonia.sh into Python.

Run with:
    cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia
    .venv/bin/python -m pytest tests/test_ollama_launcher.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from automation.ollama_launcher import estimate_vram_usage, get_ollama_port

# ---------------------------------------------------------------------------
# get_ollama_port tests
# ---------------------------------------------------------------------------

def test_get_port_deterministic():
    """Port calculation matches the bash formula: 11434 + 1 + (job_id % 200)."""
    assert get_ollama_port(job_id=100) == 11535  # 11434 + 1 + 100
    assert get_ollama_port(job_id=0) == 11435    # 11434 + 1 + 0


def test_get_port_wraps_at_200():
    """Job IDs above 200 wrap around via modulo."""
    assert get_ollama_port(job_id=200) == 11435  # same as job_id=0
    assert get_ollama_port(job_id=201) == 11436  # same as job_id=1
    assert get_ollama_port(job_id=399) == 11634  # 11434 + 1 + 199


def test_get_port_large_job_id():
    """Large SLURM job IDs are handled correctly."""
    port = get_ollama_port(job_id=1234567)
    assert 11435 <= port <= 11634  # within the valid range


def test_get_port_no_job_id():
    """When no job_id is given, a random port in 11600-11800 is returned."""
    port = get_ollama_port()
    assert 11600 <= port <= 11800


def test_get_port_no_job_id_varies():
    """Multiple calls without job_id should not always return the same port."""
    ports = {get_ollama_port() for _ in range(20)}
    # With 201 possible values and 20 draws, we expect at least 2 distinct values
    assert len(ports) > 1


# ---------------------------------------------------------------------------
# estimate_vram_usage tests
# ---------------------------------------------------------------------------

def test_vram_estimate_returns_dict():
    """Result contains the expected keys."""
    result = estimate_vram_usage("devstral:latest", 32768)
    assert "vram_gb" in result
    assert "recommendation" in result
    assert "model_params_b" in result
    assert "model_weight_gb" in result
    assert "kv_cache_gb" in result
    assert result["vram_gb"] > 0


def test_vram_estimate_context_scales():
    """Larger context length should produce higher VRAM estimates."""
    r1 = estimate_vram_usage("devstral:latest", 8192)
    r2 = estimate_vram_usage("devstral:latest", 65536)
    assert r2["vram_gb"] > r1["vram_gb"]


def test_vram_estimate_model_scales():
    """Larger models should produce higher VRAM estimates at same context."""
    r_small = estimate_vram_usage("llama3.1:8b", 8192)
    r_large = estimate_vram_usage("llama3.1:70b", 8192)
    assert r_large["vram_gb"] > r_small["vram_gb"]


def test_vram_estimate_unknown_model():
    """Unknown model names return 0 VRAM with a warning recommendation."""
    result = estimate_vram_usage("totally_unknown_model", 8192)
    assert result["vram_gb"] == 0.0
    assert "Unknown model" in result["recommendation"]


def test_vram_estimate_extracts_params_from_name():
    """Model names with explicit parameter count (e.g., '33b') are handled."""
    result = estimate_vram_usage("some_new_model:33b-q4", 8192)
    assert result["model_params_b"] == 33.0
    assert result["vram_gb"] > 0


def test_vram_estimate_known_models():
    """Spot-check a few known models for reasonable estimates."""
    # devstral:latest -> 24B params
    r = estimate_vram_usage("devstral:latest", 8192)
    assert r["model_params_b"] == 24.0
    # Weight at Q4_K_M: 24 * 0.5625 = 13.5 GB
    assert 13.0 < r["model_weight_gb"] < 14.0

    # qwen2.5:72b -> 72B params
    r = estimate_vram_usage("qwen2.5:72b", 8192)
    assert r["model_params_b"] == 72.0

    # mistral:latest -> 7B params
    r = estimate_vram_usage("mistral:latest", 8192)
    assert r["model_params_b"] == 7.0


def test_vram_estimate_kv_cache_formula():
    """KV cache follows the formula: (context / 1024) * 0.25 GB."""
    result = estimate_vram_usage("llama3.1:8b", 8192)
    expected_kv = (8192 / 1024.0) * 0.25  # = 2.0 GB
    assert abs(result["kv_cache_gb"] - expected_kv) < 0.01


def test_vram_estimate_case_insensitive():
    """Model name matching is case-insensitive."""
    r1 = estimate_vram_usage("Devstral:Latest", 8192)
    r2 = estimate_vram_usage("devstral:latest", 8192)
    assert r1["model_params_b"] == r2["model_params_b"]
