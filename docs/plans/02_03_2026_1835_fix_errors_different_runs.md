# 02_03_2026_1835 — Detailed Plan to Diagnose and Fix Errors Across Different Run Types

## 1) Goal and scope

This plan defines a structured, reproducible workflow to:
1. Diagnose current failures across the newly launched model/context matrix.
2. Isolate root causes by failure cluster (not by single run anecdotes).
3. Apply minimal, high-confidence fixes.
4. Validate each fix with targeted reruns before full fan-out reruns.

Target run families in current batch:
- Models: `kimi-k2.5`, `minimax-m2.5`, `deepseek-v3.2`, `claude-sonnet-4.6`, `nemotron-3-nano`, plus `gemini-3-flash-preview` code-context.
- Contexts: `bdikit_context`, `code_context`, `codeact_context`.

---

## 2) Current observed failure clusters (from analyzer + logs)

### Cluster A — Nemotron startup failure
- Class: `2F` (critical): model pre-load timeout / Beaker never started.
- Runs: `8bd14bc6`, `754208dd` (nemotron bdikit/code-context).
- Symptom: `ERROR: Beaker server failed to start within 900 seconds`.
- Interpretation: Ollama model warm/preload/start path blocks server readiness.

### Cluster B — Silent empty responses
- Class: `3G` (warning): turns marked `llm_response` with empty agent response.
- Appears in multiple OpenRouter runs, strongest in `code_context` and some `bdikit_context` runs.
- Interpretation: response parsing/transport/prompt interaction issue (non-timeout, but content-free).

### Cluster C — No output artifacts
- Class: `5A` (warning): no `dou_harmonized.csv` even when trace exists.
- Interpretation: run progresses partially but fails output contract (write location, save instruction compliance, or tool outcome not materialized).

### Cluster D — Kernel state budget enforced notices
- Class: `6A` (info): kernel state budget truncation events.
- Not a direct failure alone, but can contribute to context degradation and silent behavior if too aggressive.

### Cluster E — Cleanup ZMQ timeout
- Class: `1C` (info): cleanup-time ZMQ read timeout.
- Usually non-fatal post-run noise; do not prioritize unless tied to early termination.

---

## 3) Investigation principles

1. **Cluster-first debugging**: fix one cluster root cause, not one run at a time.
2. **First-failure point analysis**: identify earliest causal break in each run.
3. **Minimal changes**: smallest fix that resolves root cause and preserves behavior.
4. **Targeted validation reruns** before broad reruns.
5. **Evidence parity**: every hypothesis must tie to concrete log + trace + config evidence.

---

## 4) Step-by-step analysis workflow

## Step 4.1 — Build triage matrix (single source of truth)

For each run in batch, collect:
- run_id, slurm_job_id, model, context, provider, node, start time
- analyzer classes detected (`2F`,`3G`,`5A`,`6A`,`1C`...)
- has_trace, has_metrics, has_output_csv
- first error line in `.out`
- output directory status

Data sources:
- `read_and_analyze_logs_and_traces_cli.py --diagnostics --json`
- `.experiment_id`
- `trace.json`
- `conversation.md`
- SLURM `.out/.err`

Deliverable:
- `analysis/errors_02_03_2026_run_matrix.csv`

## Step 4.2 — Cluster A deep RCA (Nemotron `2F`)

For each `2F` run:
1. Inspect corresponding `*_ollama.log` and `.out` startup section.
2. Measure time spent in:
   - ollama start
   - model preload
   - beaker readiness loop
3. Verify model presence and pull status in job-local Ollama instance.
4. Check if preload command blocks due to model size/warm-up limitations.
5. Compare with codeact nemotron run behavior (if partially started) to isolate context-independent startup issues.

Hypothesis to test:
- Beaker readiness is gated by long/blocking preload for `nemotron-3-nano:30b` under per-job isolated Ollama.

Candidate fixes:
- Increase preload timeout only for heavy Ollama models.
- Change the job sbatch script to request larger memory on the GPU node. 
- Make preload non-blocking with bounded warmup attempts.
- Add explicit fallback: continue startup if model exists but warmup not fully complete.
- Add readiness checks that distinguish "Ollama up" vs "model warmed".

Validation:
- rerun one nemotron context first (code-context), then bdikit/codeact.
- success criterion: server ready < threshold + turns start + trace produced.

## Step 4.3 — Cluster B deep RCA (Silent `3G` responses)

For representative runs (`code_context` first):
1. Compare prompt composition files (`full_prompt_composition.json`) across PASS-like and 3G runs. HOWEVER note that it seems that only one full_prompt_composition.json exists at /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/results/full_prompt_composition.json: make sure this file gets properly written the results directory of each run!
2. Inspect trace raw messages around first empty-response turn.
3. Verify whether LLM API response has empty content vs parser dropped content.
4. Compare provider setup (`anyllm:openrouter` vs `openrouter`) and model-specific response formats.
5. Check whether kernel state payload size/budget clipping correlates with first empty response.

Hypotheses to test:
- Parser/path mismatch for specific response payload shape.
- Prompt/context state causing no-content model replies.
- State budget truncation removing key context for response generation.

Candidate fixes:
- Harden response extraction path (content + alternate message fields).
- Add explicit guardrail retry when LLM returns empty content.
- Reduce/adjust state payload and ensure budget truncation preserves critical keys.
- Improve diagnostic logging for empty-content responses (capture provider raw structure safely).

Validation:
- targeted reruns on one model across two contexts where 3G reproducible.
- success criterion: no 3G class, meaningful non-empty agent outputs.

## Step 4.4 — Cluster C deep RCA (No-output `5A`)

For runs with trace but no output:
1. Confirm final save instruction in config messages.
2. Check whether outputs were written to unexpected path (nested or alternate names).
3. Verify `run_experiment.py` output detection path logic against actual artifacts.
4. Inspect conversation final turns for claimed save location vs real filesystem.

Hypothesis:
- Save-path mismatch or output contract drift between prompt instructions and pipeline checker.

Candidate fixes:
- Standardize save instructions to root run dir file names.
- Expand output detection to known alternates only if needed.
- Add explicit post-turn assertion for required artifacts before marking run success.

Validation:
- rerun one failing 5A case; verify `dou_harmonized.csv`, mapping files, metrics.

## Step 4.5 — Cluster D handling (`6A` budget notices)

Treat as tuning track, not immediate blocker unless linked to 3G/5A:
1. quantify frequency + correlation with 3G by run/context/model.
2. adjust budget thresholds for contexts where truncation is too aggressive.
3. verify preserved key variables/functions after truncation.

Validation:
- compare pre/post budget tuning on one affected run family.

## Step 4.6 — Cluster E handling (`1C` cleanup timeouts)

Low priority:
- confirm cleanup-only timing (post artifacts produced).
- if noisy, suppress or gracefully handle in shutdown logic.

---

## 5) Implementation order (strict)

1. Build triage matrix + confirm cluster membership.
2. Fix Cluster A (`2F`) startup path first (hard blocker).
3. Fix Cluster B (`3G`) empty response path.
4. Fix Cluster C (`5A`) output contract/path issues.
5. Tune Cluster D (`6A`) if still correlated with B/C.
6. Optionally reduce Cluster E (`1C`) noise.
7. Re-run targeted validation set.
8. Re-run full matrix only after targeted passes are clean.

---

## 6) Targeted validation set (minimal before full rerun)

- Nemotron code-context (tests `2F` fix)
- Deepseek code-context (tests `3G` path)
- Minimax bdikit-context (tests `5A` + `3G` interaction)
- Gemini code-context (regression guard; currently better than others)

Pass criteria for each targeted run:
- Beaker starts within timeout.
- trace + conversation + output CSV + mapping files present.
- metrics produced where expected.
- no critical/error classes in analyzer output (info warnings acceptable if understood).

---

## 7) Full rerun criteria

Proceed to broad reruns only when:
1. Targeted set passes consistently.
2. No new regression introduced in Gemini codeact/bdikit baselines.
3. Analyzer shows expected reduction in `2F`, `3G`, `5A`.

---

## 8) Reporting deliverables

After each phase:
- `analysis/errors_02_03_2026_run_matrix.csv` (updated)
- short markdown RCA note per cluster with:
  - root cause
  - fix
  - validation evidence
- consolidated summary with before/after class counts.

---

## 9) Integration with visualization workflow

Once stabilized runs complete:
1. regenerate run summary tables using visualization CLI.
2. produce global comparison bars and per-column heatmaps.
3. include error-only column subset plots to highlight residual weak points.
4. carry prompt/config metadata into plots to compare prompt/version effects.

---

## 10) Stretch goal: interactive trace exploration

Proposed stack:
- **Plotly + Dash** (best for linked timeline/table/code panes)
- Alternative rapid path: **Streamlit + Plotly**

Initial trace viewer MVP:
- turn timeline with status/error markers
- filter by turn type (tool call / llm response / timeout)
- code-cell viewer (show code emitted/executed)
- error panel (jump to turns with stack traces or analyzer classes)

This should reuse normalized trace tables from the same data preparation layer used by plotting.
