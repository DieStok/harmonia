# WP-F: Shell Monolith -- Extract Ollama + VRAM into Python (Incremental)

**Date:** 2026-03-03
**Status:** Complete

## What was done

### F1 -- Created `src/automation/ollama_launcher.py`

New Python module (~300 lines) that extracts Ollama-related logic from `exec_apptainer_harmonia.sh`:

1. **`estimate_vram_usage(model_name, context_length)`** -- Python equivalent of the bash `estimate_vram_usage()` function. The bash version queries `nvidia-smi` for live GPU stats after model load; this Python version estimates from a model parameter lookup table for pre-flight planning (before GPU allocation). It includes:
   - A lookup table (`MODEL_PARAMETERS`) mapping model name patterns (regex) to approximate parameter counts in billions (covers devstral, qwen, llama, mistral/mixtral, gemma, phi, codellama, deepseek families)
   - A fallback regex extractor that tries to parse parameter count from the model name (e.g., "some_model:33b-q4" -> 33B)
   - VRAM calculation: `model_weight_gb = params_b * 0.5625` (Q4_K_M quantization) + `kv_cache_gb = (context / 1024) * 0.25`
   - Human-readable recommendations based on total estimated VRAM

2. **`get_ollama_port(job_id=None)`** -- Deterministic port calculation matching the bash formula: `11434 + 1 + (job_id % 200)`. When no job_id is provided (interactive use), returns a random port in range 11600-11800.

3. **`estimate_vram_nvidia_smi(context_length)`** -- Live GPU estimation using `nvidia-smi` (mirrors the bash version exactly). Used by the CLI when a GPU is available to show both offline and live estimates.

4. **CLI interface** -- Two subcommands:
   - `estimate-vram --model <name> --context <N> [--json]`
   - `get-port --job-id <id>`

### F2 -- Integrated into `exec_apptainer_harmonia.sh`

Two call sites were replaced:

1. **Port calculation (line ~37):** Replaced the `if/else` bash block with:
   ```bash
   OLLAMA_PORT=$(python3 "${SCRIPT_DIR}/src/automation/ollama_launcher.py" get-port --job-id "${SLURM_JOB_ID:-}") || {
       # Fallback to original bash logic if Python fails
       ...
   }
   ```
   The fallback preserves the original behavior if Python is not available.

2. **VRAM estimation call site (line ~668):** Replaced `estimate_vram_usage "$OLLAMA_CONTEXT_LENGTH"` with:
   ```bash
   python3 "${SCRIPT_DIR}/src/automation/ollama_launcher.py" estimate-vram \
       --model "$LLM_MODEL" --context "${OLLAMA_CONTEXT_LENGTH:-8192}" || \
       estimate_vram_usage "$OLLAMA_CONTEXT_LENGTH"
   ```
   Falls back to the original bash function if Python fails. The bash function definition is kept as-is.

### F3 -- Created `tests/test_ollama_launcher.py`

13 unit tests covering:
- `get_ollama_port`: deterministic calculation, modulo wrapping, large job IDs, random fallback, randomness variance
- `estimate_vram_usage`: return type, context scaling, model scaling, unknown models, parameter extraction from name, known model spot-checks, KV cache formula, case insensitivity

All 13 tests pass.

## Design decisions

1. **Offline estimation vs live GPU query:** The Python `estimate_vram_usage()` uses a model parameter lookup table rather than `nvidia-smi`, because it is called before GPU allocation. This is complementary to (not a replacement for) the bash version which queries live GPU state. The CLI shows both when nvidia-smi is available.

2. **Fallback pattern:** Both shell integration points use `command || fallback` so the script never breaks if Python is unavailable (e.g., inside the Apptainer container where `python3` might not be on PATH or the venv is not activated). The original bash logic is preserved as fallback.

3. **Model parameter lookup:** Uses regex pattern matching against model names, with most-specific patterns first. Falls back to extracting a number followed by 'b' from the name. Returns a clear "unknown model" response rather than guessing.

4. **Port calculation for empty SLURM_JOB_ID:** When `--job-id ""` is passed (the shell substitution `${SLURM_JOB_ID:-}` produces empty string when unset), the Python CLI treats it as no job_id and returns a random port. This matches the intended behavior for interactive use.

## Codebase description update needed

The file `documentation/codebase_descriptions/how_this_codebase_works_26_02_2026.md` needs these diffs for a new dated version:

1. In the file tree section (around line 316), after `exec_apptainer_harmonia.sh`, the `src/automation/` listing should include:
   ```
   │   ├── ollama_launcher.py  # Ollama port calculation + VRAM estimation (CLI + library)
   ```

2. In section "1. Automation Framework (`src/automation/`)" (around line 374), add a new subsection:
   ```markdown
   #### `ollama_launcher.py` - Ollama Utilities
   Extracted from exec_apptainer_harmonia.sh. Provides VRAM estimation from model
   parameter lookup tables and deterministic port calculation for per-job Ollama isolation.
   Can be used as a library or CLI (`python ollama_launcher.py estimate-vram|get-port`).
   ```

3. In the Ollama section (around line 1271), update the port calculation description to mention it now uses `ollama_launcher.py` with bash fallback.

4. Update the VRAM estimation description (around line 42) to note both offline (Python) and live (bash) estimation modes.

## Files changed

- `src/automation/ollama_launcher.py` (NEW)
- `tests/test_ollama_launcher.py` (NEW)
- `exec_apptainer_harmonia.sh` (MODIFIED -- two call sites replaced with Python-backed versions + fallbacks)
