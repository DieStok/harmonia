# 02_03_2026 — Fix errors across different runs: implementation status

## Implemented code changes

1. **Cluster A (Nemotron startup / 2F)**
   - Updated `exec_apptainer_harmonia.sh` to bound Ollama pre-warm duration with `timeout` and model-aware default limits.
   - Added `HARMONIA_OLLAMA_PRELOAD_TIMEOUT_SECONDS` override and continued startup on warmup timeout instead of indefinite blocking.
   - Updated `sbatch_template_gpu.sh` to pass `--results-dir` and create deterministic per-run result folders, matching CPU template behavior.

2. **Cluster B (silent empty responses / 3G)**
   - Hardened websocket response handling in `src/automation/client.py`:
     - waits for `execute_reply`/`idle` or non-empty `llm_response` instead of stopping on first possibly-empty `llm_response`;
     - extracts fallback text fields (`content`, `message`) and preserves non-empty stream content;
     - adds final reverse-pass fallback extraction from raw messages.

3. **Cluster C (missing output artifacts / 5A)**
   - Added explicit required-artifact assertion in `run_experiment.py` for `dou_harmonized.csv` and mapping files when configured.
   - Runs now exit non-zero when required artifacts are missing.
   - Added prompt composition relocation: if `full_prompt_composition.json` is written at run parent level, copy it into the final timestamped run output directory.

## Deliverables generated

- Triage matrix CSV: `analysis/errors_02_03_2026_run_matrix.csv`
  - columns include run metadata, detected class IDs, trace/metrics flags, output presence indicator, and first error evidence.

## Validation performed

- `python -m py_compile src/automation/client.py run_experiment.py`
- Re-ran analyzer + diagnostics to build matrix from latest automated runs.
- Spot-checked trace files for empty `llm_response` instances in representative runs (gemini/minimax).

## Remaining execution step

- Submit targeted reruns to verify reductions in `2F`, `3G`, and `5A` under production workload and update before/after class counts in the matrix.
