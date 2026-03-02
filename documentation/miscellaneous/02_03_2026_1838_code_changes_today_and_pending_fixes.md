# 02_03_2026_1838 — Code changes today and pending fixes

## Scope
- Time window: commits on 2026-03-02 (from `git log --since`).
- Includes committed work plus currently pending follow-up fixes identified during run analysis.

## Commits today (git log)
- `e1e018d` (2026-03-02 19:32:25 +0100) by Dieter Stoker: **Harden experiment reliability: add per-error retries, OpenRouter adapter guards, and config-wide retry policy**
  - Files changed: 51
- `0f3be13` (2026-03-02 18:19:57 +0100) by Dieter Stoker: **feat(frontier-runs+evaluation): harden Gemini/OpenRouter execution, add diagnostics, and implement visualization CLI with interactive backend support**
  - Files changed: 94

### Commit `e1e018d` — Harden experiment reliability: add per-error retries, OpenRouter adapter guards, and config-wide retry policy
- Full SHA: `e1e018d48bf4b6ec15bf8e5e945b2f81ca870e92`
- Date: 2026-03-02 19:32:25 +0100
- Author: Dieter Stoker + Codex5.3 via Copilot
- Changed files:
  - `analysis/02_03_2026_fix_errors_different_runs_implementation.md`
  - `analysis/errors_02_03_2026_run_matrix.csv`
  - `analysis/targeted_reruns_02_03_2026.csv`
  - `documentation/codebase_descriptions/how_this_codebase_works_02_03_2026.md`
  - `documentation/plans/02_03_2026_1835_fix_errors_different_runs.md`
  - `exec_apptainer_harmonia.sh`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/custom_js/custom.js`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral-small.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_glm-4.5-air.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_glm-4.7-flash.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_olmo3.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_qwen3-coder.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_step-3.5-flash.yaml`
  - `jobs/dou_harmonization_bdikit-tools_minimax-m2.5.sh`
  - `jobs/dou_harmonization_code-context_deepseek-v3.2.sh`
  - `jobs/dou_harmonization_code-context_gemini-3-flash-preview.sh`
  - `jobs/dou_harmonization_code-context_nemotron-3-nano.sh`
  - `run_experiment.py`
  - `sbatch_template_gpu.sh`
  - `scripts/update_config_yamls.py`
  - `src/automation/client.py`
  - `src/automation/config.py`
  - `src/automation/runner.py`
  - `src/bdikit_context/context.py`
  - `src/code_context/context.py`
  - `src/codeact_context/context.py`
  - `src/openrouter_hardening.py`

### Commit `0f3be13` — feat(frontier-runs+evaluation): harden Gemini/OpenRouter execution, add diagnostics, and implement visualization CLI with interactive backend support
- Full SHA: `0f3be130b7ece5854dde2c04316d0cad3c538c0d`
- Date: 2026-03-02 18:19:57 +0100
- Author: Dieter Stoker + Codex5.3 via Copilot
- Changed files:
  - `.runtime_contexts/codeact_context.json`
  - `analysis/visualizations_smoke/error_columns_summary.csv`
  - `analysis/visualizations_smoke/manifest.json`
  - `analysis/visualizations_smoke/plots/heatmap_accuracy_excl_empty_errors_only.png`
  - `analysis/visualizations_smoke/run_summary.csv`
  - `analysis/visualizations_smoke/top_errors_per_column.csv`
  - `analysis/visualizations_smoke2/manifest.json`
  - `analysis/visualizations_smoke2/plots/global_bar_avg_value_accuracy_excl_empty.png`
  - `analysis/visualizations_smoke2/plots/global_bar_avg_value_f1_excl_empty.png`
  - `analysis/visualizations_smoke2/plots/global_bar_column_mapping_accuracy.png`
  - `analysis/visualizations_smoke2/plots/heatmap_accuracy_excl_empty.png`
  - `analysis/visualizations_smoke2/tables/column_mapping.csv`
  - `analysis/visualizations_smoke2/tables/column_values.csv`
  - `analysis/visualizations_smoke2/tables/confusion.csv`
  - `analysis/visualizations_smoke2/tables/runs.csv`
  - `analysis/visualizations_smoke2/tables/top_errors_per_column.csv`
  - `build_harmonia_apptainer.sh`
  - `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`
  - `documentation/my_instructions/02_03_2026_1305_get_frontier_model_runs_working_openrouter.md`
  - `documentation/my_instructions/02_03_2026_1655_make_performance_visualizations.md`
  - `documentation/plans/02_03_2026_1352_make_frontier_models_work.md`
  - `documentation/plans/02_03_2026_1558_visualization_script_cli_implementation_plan.md`
  - `documentation/processes/02_03_2026_env_audit.csv`
  - `documentation/processes/02_03_2026_frontier_model_config_mapping.md`
  - `documentation/processes/02_03_2026_priority_run_ledger.csv`
  - `exec_apptainer_harmonia.sh`
  - `experiments/experiment_1_harmonia_dou2020_gdc/analysis_completed_runs/02_03_2026/02_03_2026_frontier_codeact_bdikit_gemini_claude_analysis.md`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/custom_js/custom.js`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral-small.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_glm-4.5-air.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_glm-4.7-flash.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_olmo3.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_qwen3-coder.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_step-3.5-flash.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_anthropic-claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_google-gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_moonshotai-kimi-k2.5.yaml`
  - `jobs/dou_harmonization_bdikit-tools_claude-sonnet-4.6.sh`
  - `jobs/dou_harmonization_bdikit-tools_deepseek-v3.2.sh`
  - `jobs/dou_harmonization_bdikit-tools_gemini-3-flash-preview.sh`
  - `jobs/dou_harmonization_bdikit-tools_kimi-k2.5.sh`
  - `jobs/dou_harmonization_bdikit-tools_minimax-m2.5.sh`
  - `jobs/dou_harmonization_bdikit-tools_nemotron-3-nano.sh`
  - `jobs/dou_harmonization_code-context_claude-sonnet-4.6.sh`
  - `jobs/dou_harmonization_code-context_deepseek-v3.2.sh`
  - `jobs/dou_harmonization_code-context_gemini-3-flash-preview.sh`
  - `jobs/dou_harmonization_code-context_kimi-k2.5.sh`
  - `jobs/dou_harmonization_code-context_minimax-m2.5.sh`
  - `jobs/dou_harmonization_code-context_nemotron-3-nano.sh`
  - `jobs/dou_harmonization_codeact_claude-sonnet-4.6.sh`
  - `jobs/dou_harmonization_codeact_deepseek-v3.2.sh`
  - `jobs/dou_harmonization_codeact_gemini-3-flash-preview.sh`
  - `jobs/dou_harmonization_codeact_kimi-k2.5.sh`
  - `jobs/dou_harmonization_codeact_minimax-m2.5.sh`
  - `jobs/dou_harmonization_codeact_nemotron-3-nano.sh`
  - `pyproject.toml`
  - `run_experiment.py`
  - `sbatch_template.sh`
  - `src/automation/runner.py`
  - `src/bdikit_context/agent.py`
  - `src/evaluation/visualization/__init__.py`
  - `src/evaluation/visualization/aggregate.py`
  - `src/evaluation/visualization/enrich.py`
  - `src/evaluation/visualization/io.py`
  - `src/evaluation/visualization/normalize.py`
  - `src/evaluation/visualization/plots.py`
  - `src/evaluation/visualization/report.py`
  - `src/evaluation/visualize_metrics_cli.py`

## Affected code areas (aggregated)
### .runtime_contexts
- Count: 1 files
  - `.runtime_contexts/codeact_context.json`

### Automated experiment configs
- Count: 31 files
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/custom_js/custom.js`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_bdikit-tools_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_code-context_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral-small.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_devstral.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_glm-4.5-air.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_glm-4.7-flash.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_kimi-k2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_nemotron-3-nano.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_olmo3.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_qwen3-coder.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_step-3.5-flash.yaml`

### Automation runner/client/config
- Count: 3 files
  - `src/automation/client.py`
  - `src/automation/config.py`
  - `src/automation/runner.py`

### Context/LLM integration
- Count: 4 files
  - `src/bdikit_context/agent.py`
  - `src/bdikit_context/context.py`
  - `src/code_context/context.py`
  - `src/codeact_context/context.py`

### Documentation/plans/codebase notes
- Count: 9 files
  - `documentation/codebase_descriptions/how_this_codebase_works_02_03_2026.md`
  - `documentation/my_instructions/02_03_2026_1305_get_frontier_model_runs_working_openrouter.md`
  - `documentation/my_instructions/02_03_2026_1655_make_performance_visualizations.md`
  - `documentation/plans/02_03_2026_1352_make_frontier_models_work.md`
  - `documentation/plans/02_03_2026_1558_visualization_script_cli_implementation_plan.md`
  - `documentation/plans/02_03_2026_1835_fix_errors_different_runs.md`
  - `documentation/processes/02_03_2026_env_audit.csv`
  - `documentation/processes/02_03_2026_frontier_model_config_mapping.md`
  - `documentation/processes/02_03_2026_priority_run_ledger.csv`

### Evaluation visualization CLI
- Count: 8 files
  - `src/evaluation/visualization/__init__.py`
  - `src/evaluation/visualization/aggregate.py`
  - `src/evaluation/visualization/enrich.py`
  - `src/evaluation/visualization/io.py`
  - `src/evaluation/visualization/normalize.py`
  - `src/evaluation/visualization/plots.py`
  - `src/evaluation/visualization/report.py`
  - `src/evaluation/visualize_metrics_cli.py`

### Execution + orchestration scripts
- Count: 4 files
  - `exec_apptainer_harmonia.sh`
  - `run_experiment.py`
  - `sbatch_template.sh`
  - `sbatch_template_gpu.sh`

### Generated job scripts
- Count: 18 files
  - `jobs/dou_harmonization_bdikit-tools_claude-sonnet-4.6.sh`
  - `jobs/dou_harmonization_bdikit-tools_deepseek-v3.2.sh`
  - `jobs/dou_harmonization_bdikit-tools_gemini-3-flash-preview.sh`
  - `jobs/dou_harmonization_bdikit-tools_kimi-k2.5.sh`
  - `jobs/dou_harmonization_bdikit-tools_minimax-m2.5.sh`
  - `jobs/dou_harmonization_bdikit-tools_nemotron-3-nano.sh`
  - `jobs/dou_harmonization_code-context_claude-sonnet-4.6.sh`
  - `jobs/dou_harmonization_code-context_deepseek-v3.2.sh`
  - `jobs/dou_harmonization_code-context_gemini-3-flash-preview.sh`
  - `jobs/dou_harmonization_code-context_kimi-k2.5.sh`
  - `jobs/dou_harmonization_code-context_minimax-m2.5.sh`
  - `jobs/dou_harmonization_code-context_nemotron-3-nano.sh`
  - `jobs/dou_harmonization_codeact_claude-sonnet-4.6.sh`
  - `jobs/dou_harmonization_codeact_deepseek-v3.2.sh`
  - `jobs/dou_harmonization_codeact_gemini-3-flash-preview.sh`
  - `jobs/dou_harmonization_codeact_kimi-k2.5.sh`
  - `jobs/dou_harmonization_codeact_minimax-m2.5.sh`
  - `jobs/dou_harmonization_codeact_nemotron-3-nano.sh`

### Monitoring + diagnostics tooling
- Count: 1 files
  - `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`

### Utility scripts
- Count: 1 files
  - `scripts/update_config_yamls.py`

### analysis
- Count: 18 files
  - `analysis/02_03_2026_fix_errors_different_runs_implementation.md`
  - `analysis/errors_02_03_2026_run_matrix.csv`
  - `analysis/targeted_reruns_02_03_2026.csv`
  - `analysis/visualizations_smoke/error_columns_summary.csv`
  - `analysis/visualizations_smoke/manifest.json`
  - `analysis/visualizations_smoke/plots/heatmap_accuracy_excl_empty_errors_only.png`
  - `analysis/visualizations_smoke/run_summary.csv`
  - `analysis/visualizations_smoke/top_errors_per_column.csv`
  - `analysis/visualizations_smoke2/manifest.json`
  - `analysis/visualizations_smoke2/plots/global_bar_avg_value_accuracy_excl_empty.png`
  - `analysis/visualizations_smoke2/plots/global_bar_avg_value_f1_excl_empty.png`
  - `analysis/visualizations_smoke2/plots/global_bar_column_mapping_accuracy.png`
  - `analysis/visualizations_smoke2/plots/heatmap_accuracy_excl_empty.png`
  - `analysis/visualizations_smoke2/tables/column_mapping.csv`
  - `analysis/visualizations_smoke2/tables/column_values.csv`
  - `analysis/visualizations_smoke2/tables/confusion.csv`
  - `analysis/visualizations_smoke2/tables/runs.csv`
  - `analysis/visualizations_smoke2/tables/top_errors_per_column.csv`

### build_harmonia_apptainer.sh
- Count: 1 files
  - `build_harmonia_apptainer.sh`

### experiments
- Count: 6 files
  - `experiments/experiment_1_harmonia_dou2020_gdc/analysis_completed_runs/02_03_2026/02_03_2026_frontier_codeact_bdikit_gemini_claude_analysis.md`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_anthropic-claude-sonnet-4.6.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_deepseek-v3.2.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_google-gemini-3-flash-preview.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_minimax-m2.5.yaml`
  - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_moonshotai-kimi-k2.5.yaml`

### pyproject.toml
- Count: 1 files
  - `pyproject.toml`

### src
- Count: 1 files
  - `src/openrouter_hardening.py`

## Key functional additions/fixes made today
- Reliability hardening: bounded Ollama prewarm behavior, per-run results-dir plumbing, stricter required artifact checks in runner path.
- Diagnostics hardening: richer run/trace/log analysis outputs and RCA-focused classification support.
- Evaluation tooling: full visualization CLI + normalization/aggregation helpers with static + interactive backends and error-focused views.
- Metadata normalization: pull run metadata from `.experiment_id` and carry prompt/config provenance into tidy tables.
- Retry and adapter resilience: config-driven retries per error-code family, plus OpenRouter adapter hardening (null-thought coercion + metadata/raw error logging).

## What is still pending fixing (from current analysis)
- Nemotron code-context targeted run still shows startup failure class `2F` (Beaker readiness after Ollama/model preload).
- Minimax bdikit-tools still fails output contract (`5A`): only `column_mapping.json` appears, `dou_harmonized.csv` and `value_mapping.json` missing.
- Deepseek code-context improved (produces `dou_harmonized.csv`) but still misses mapping JSON artifacts in targeted rerun.
- Gemini code-context targeted rerun still has `3A/5A` symptoms (partial/no final artifacts).
- Need to confirm newly relaunched jobs `47438431` (deepseek) and `47438432` (minimax) after retry-policy + adapter hardening complete.
- `mount-visibility-cli` todo remains pending (implement + run minimal validation against one pass and one fail run).

## Current workspace note
- Uncommitted items currently visible in working tree:
  - `M experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/custom_js/custom.js`
