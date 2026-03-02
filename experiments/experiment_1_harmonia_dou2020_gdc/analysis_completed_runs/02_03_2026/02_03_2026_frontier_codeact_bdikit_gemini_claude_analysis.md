# Frontier Runs Analysis (02-03-2026)

Analyzed runs launched earlier today:
1. CodeAct + Gemini (`b91e3682`, job `47434915`)
2. CodeAct + Claude Sonnet 4.6 (`ad2e3cac`, job `47434916`)
3. BDI-kit tools + Gemini (`bae7ba7a`, job `47434917`)
4. BDI-kit tools + Claude Sonnet 4.6 (`697fd603`, job `47434918`)

---

## 1) Observed correct behaviours

- All four jobs started, Beaker launched, and traces/conversations were produced.
- OpenRouter connectivity worked enough for substantial responses in all four runs.
- Both CodeAct runs produced harmonization artifacts under nested `results/` directories:
  - `dou_harmonized.csv`
  - `column_mapping.json`
  - `value_mapping.json`
- Automated diagnostics now capture high-signal RCA fields (`--diagnostics`) including duplicate turn IDs, first FileNotFound evidence, execution signal counts, and observability leakage hints.

---

## 2) Observed problems requiring fixes

### Cross-run major issues

1. **Wrong path used in prompt workflow (`4A`)**
   - Error evidence: `FileNotFoundError: data/one_metadata_table_gdc_schema/data/dou.csv`
   - Root problem: prompt path was relative/inconsistent with container mount (`/workspace/data/...`).

2. **Observability leak in `/workspace/results`**
   - Each run log shows ~206 lines of `/workspace/results/old/...` visibility.
   - Root problem: broad shared results mount exposed historical outputs.

3. **Infrastructure/runtime instability (`1C`)**
   - Repeated `Uncaught exception in ZMQStream callback` seen across runs.
   - Mostly cleanup/noisy, but high frequency indicates unstable shutdown/restart behavior under load.

4. **Disk-space pressure (`No space left on device`)**
   - Strongly present in BDI-kit runs and recent reruns.
   - Affects Beaker runtime metadata writes and likely contributes to cascading failures.

### Run-specific anomalies

- **CodeAct Gemini (`b91e3682`)**
  - Hit CodeAct max-turn fallback in turn 1 before recovery.
  - Duplicate turn entries in trace/conversation: 3, 5, 7, 12.

- **CodeAct Claude (`ad2e3cac`)**
  - Duplicate turn entries: 5, 8.
  - Additional context/empty-response style symptoms (`3E`, `3G`).

- **BDI-kit Gemini/Claude (`bae7ba7a`, `697fd603`)**
  - Severe failure mix: `4A`, `6A`, `3A`, `3G`, `5A`.
  - No final harmonized outputs at run root; analyzer marked no-output (some exacerbated by nested-layout expectations before analyzer fix + actual run instability).

---

## 3) Fixes already implemented

1. **Updated analyzer CLI with RCA diagnostics**
   - File: [`code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py)
   - Added `--diagnostics` output:
     - duplicate turn detection
     - codeact max-turn detection
     - first `FileNotFoundError` evidence
     - execution signal counts by turn
     - observability leakage hints from log content
     - output layout inspection (top-level vs nested `results/`)
   - Improved no-output check to accept nested `results/dou_harmonized.csv`.

2. **Explicit per-run `--results-dir` in sbatch template**
   - File: [`sbatch_template.sh`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/sbatch_template.sh)
   - Added `RUN_RESULTS_DIR` and passed `--results-dir "$RUN_RESULTS_DIR"` to `exec_apptainer_harmonia.sh`.

3. **Prompt path normalization in automated configs**
   - Updated all automated experiment prompts from:
     - `data/one_metadata_table_gdc_schema/data/dou.csv`
     to:
     - `/workspace/data/one_metadata_table_gdc_schema/data/dou.csv`
   - Directory touched: [`experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc/configs/automated)

4. **Decision logging/turn accounting fix (duplicate-turn bug)**
   - File: [`src/automation/runner.py`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/src/automation/runner.py)
   - Primary response is now logged before auto-decision follow-up; auto-decision logged as a separate turn with distinct turn ID.

---

## 4) Fixes not yet fully implemented / further analysis needed

1. **Disk-space remediation (critical blocker)**
   - Current runs show `No space left on device`; this is now a primary blocker for clean verification of runtime fixes.
   - Needs cleanup strategy and guardrails around log/runtime artifact growth.

2. **Validate per-run results-dir isolation with a clean rerun**
   - New template change is in place, but latest verification attempt was impacted by disk-space errors.
   - Need a clean post-cleanup rerun to confirm `/workspace/results/old/*` is no longer visible.

3. **Potential additional CodeAct loop guarding**
   - Even with correct path prompts, robust break conditions for repeated execution patterns would improve resilience.

4. **BDI-kit deep failure chain (`6A`, `3A`, `3G`, `5A`)**
   - Requires focused triage after storage/runtime stability is restored.
   - Some failures are likely secondary effects of early path/storage instability.

---

## 5) Run references (logs/results)

### Run A — CodeAct + Gemini
- Job: `47434915`
- Run ID: `b91e3682`
- Log: [`02-03-2026_1432_dou_harmonization_codeact_gemini-3-flash-preview_47434915_b91e3682.out`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs/02-03-2026_1432_dou_harmonization_codeact_gemini-3-flash-preview_47434915_b91e3682.out)
- Err: [`02-03-2026_1432_dou_harmonization_codeact_gemini-3-flash-preview_47434915_b91e3682.err`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs/02-03-2026_1432_dou_harmonization_codeact_gemini-3-flash-preview_47434915_b91e3682.err)
- Results: [`dou_harmonization_codeact_gemini-3-flash-preview_20260302_133318_b91e3682`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/results/dou_harmonization_codeact_gemini-3-flash-preview_20260302_133318_b91e3682)

### Run B — CodeAct + Claude Sonnet 4.6
- Job: `47434916`
- Run ID: `ad2e3cac`
- Log: [`02-03-2026_1432_dou_harmonization_codeact_claude-sonnet-4.6_47434916_ad2e3cac.out`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs/02-03-2026_1432_dou_harmonization_codeact_claude-sonnet-4.6_47434916_ad2e3cac.out)
- Err: [`02-03-2026_1432_dou_harmonization_codeact_claude-sonnet-4.6_47434916_ad2e3cac.err`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs/02-03-2026_1432_dou_harmonization_codeact_claude-sonnet-4.6_47434916_ad2e3cac.err)
- Results: [`dou_harmonization_codeact_claude-sonnet-4.6_20260302_133318_ad2e3cac`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/results/dou_harmonization_codeact_claude-sonnet-4.6_20260302_133318_ad2e3cac)

### Run C — BDI-kit + Gemini
- Job: `47434917`
- Run ID: `bae7ba7a`
- Log: [`02-03-2026_1432_dou_harmonization_bdikit-tools_gemini-3-flash-preview_47434917_bae7ba7a.out`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs/02-03-2026_1432_dou_harmonization_bdikit-tools_gemini-3-flash-preview_47434917_bae7ba7a.out)
- Err: [`02-03-2026_1432_dou_harmonization_bdikit-tools_gemini-3-flash-preview_47434917_bae7ba7a.err`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs/02-03-2026_1432_dou_harmonization_bdikit-tools_gemini-3-flash-preview_47434917_bae7ba7a.err)
- Results: [`dou_harmonization_bdikit-tools_gemini-3-flash-preview_20260302_133319_bae7ba7a`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/results/dou_harmonization_bdikit-tools_gemini-3-flash-preview_20260302_133319_bae7ba7a)

### Run D — BDI-kit + Claude Sonnet 4.6
- Job: `47434918`
- Run ID: `697fd603`
- Log: [`02-03-2026_1432_dou_harmonization_bdikit-tools_claude-sonnet-4.6_47434918_697fd603.out`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs/02-03-2026_1432_dou_harmonization_bdikit-tools_claude-sonnet-4.6_47434918_697fd603.out)
- Err: [`02-03-2026_1432_dou_harmonization_bdikit-tools_claude-sonnet-4.6_47434918_697fd603.err`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/logs/02-03-2026_1432_dou_harmonization_bdikit-tools_claude-sonnet-4.6_47434918_697fd603.err)
- Results: [`dou_harmonization_bdikit-tools_claude-sonnet-4.6_20260302_133319_697fd603`](/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/results/dou_harmonization_bdikit-tools_claude-sonnet-4.6_20260302_133319_697fd603)
