# Plan: Get Frontier OpenRouter Models Running (CodeAct + BDI-Tools Focus)

**Date:** 02_03_2026_1352  
**Scope owner:** execution-focused plan for immediate implementation and submission  
**Primary goal for today:** get tangible successful runs for 4 scenarios:
1. CodeAct + `google/gemini-3-flash-preview`
2. CodeAct + `anthropic/claude-sonnet-4.6`
3. BDI-tools agent + `google/gemini-3-flash-preview`
4. BDI-tools agent + `anthropic/claude-sonnet-4.6`

---

## 1) Constraints, assumptions, and non-negotiables

- Use exact OpenRouter model IDs exactly as provided:
  - `minimax/minimax-m2.5`
  - `google/gemini-3-flash-preview`
  - `deepseek/deepseek-v3.2`
  - `moonshotai/kimi-k2.5`
  - `anthropic/claude-sonnet-4.6`
- Use existing root key in `harmonia/.env` as source of truth for OpenRouter.
- For non-local providers, associated env files must be regenerated from root `.env` + config using existing `generate_env.py` workflow.
- Use simple CPU sbatch path (no GPU template for this workstream).
- Submit jobs (not dry-run only).
- Follow latest instructions in:
  - `.claude/CLAUDE.md`
  - `docs/codebase_descriptions/how_this_codebase_works_26_02_2026.md`

---

## 2) Inventory and discovery (do first)

1. Enumerate current config families in:
   - `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/`
   - `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/`
2. Identify naming conventions for:
   - model slug in filename
   - agent/context selector fields in YAML (CodeAct vs BDI tools)
3. Confirm how each context is selected and mapped:
   - `src/codeact_context/`
   - `src/bdikit_context/`
   - (optionally) `src/code_context/` for parity checks
4. Confirm whether any existing config is already OpenRouter + CodeAct or OpenRouter + BDI-tools, and clone closest templates.

Deliverable: short internal mapping table (template source -> new target config names).

---

## 3) Config creation tasks

## 3.1 New OpenRouter model coverage (manual + automated)

Create **new manual and automated configs** for all 5 requested models.

For each model, add:
- one config in `configs/automated/`
- one config in `configs/manual/`

Target IDs and context windows (document in YAML comments and plan notes):
- `minimax/minimax-m2.5` (196608)
- `google/gemini-3-flash-preview` (1048576)
- `deepseek/deepseek-v3.2` (~164k)
- `moonshotai/kimi-k2.5` (~262k)
- `anthropic/claude-sonnet-4.6` (~1M)

Required config fields:
- provider set to OpenRouter provider style already used in repo
- model set exactly to ID above
- context management tuned for large context where applicable (reuse working defaults from recent successful OpenRouter configs)

## 3.2 Priority 4 scenarios for immediate execution

Ensure explicit automated configs exist for these 4 runs:
- CodeAct + gemini-3-flash-preview
- CodeAct + claude-sonnet-4.6
- BDI-tools + gemini-3-flash-preview
- BDI-tools + claude-sonnet-4.6

If necessary, create dedicated filenames (recommended):
- `dou_harmonization_codeact_gemini-3-flash-preview.yaml`
- `dou_harmonization_codeact_claude-sonnet-4.6.yaml`
- `dou_harmonization_bdikit-tools_gemini-3-flash-preview.yaml`
- `dou_harmonization_bdikit-tools_claude-sonnet-4.6.yaml`

(Use exact local naming convention if existing style differs; consistency over these sample names.)

---

## 4) API key propagation and associated env regeneration

## 4.1 Regenerate associated env files

Run env generation for:
- all newly created configs
- all existing non-local configs that rely on cloud providers

Mechanism:
- use `generate_env.py`
- base env must be root `harmonia/.env`
- output remains side-by-side `{config_stem}_associated.env`

## 4.2 Verify correct token lineage

For each generated associated env (non-local):
- assert `LLM_SERVICE_PROVIDER` and `LLM_SERVICE_MODEL` match config
- assert `LLM_SERVICE_TOKEN` resolves from corresponding root provider key
- for OpenRouter configs specifically, verify token source is `OPENROUTER_API_KEY`

Add one audit log artifact (markdown table or CSV) listing:
- config file
- associated env file
- provider
- model
- token source var (not raw secret)
- pass/fail

---

## 5) Sbatch generation and submission (CPU)

## 5.1 Generate sbatch scripts for priority 4

Use existing `generate_jobs.py` with CPU template (`sbatch_template.sh`) and standard CPU resources.

Recommended baseline for today:
- account: `compgen`
- time: `02:00:00`
- mem: `20G`
- cpus-per-task: `2`
- tmpspace: template default unless needed

Generate 4 scripts into `jobs/`.

## 5.2 Submit and capture IDs

Submit all 4 scripts with `sbatch`.
Record:
- job id
- config name
- run id (from logs / `.experiment_id`)
- expected output directory

Create a single run ledger file in `docs/plans/` or `docs/processes/` with this mapping.

---

## 6) Execution monitoring and acceptance checks

For each of the 4 submitted jobs, verify:

1. Logs are created under `logs/`.
2. Beaker startup succeeds.
3. No hard OpenRouter failures (`404`, `429`, auth, malformed provider/model).
4. Results directory is created under `results/` with run-id linkage.
5. Required outputs exist:
   - `trace.json`
   - `conversation.md`
   - harmonized output artifact(s) expected by experiment pipeline
   - `.experiment_id`

If any job fails, triage with taxonomy file before rerun.

---

## 7) Log reading and error analysis workflow (required)

Use:
- `code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml`
- latest logs in `logs/`
- `read_and_analyze_logs_and_traces_cli.py`

## 7.1 Error classes to explicitly watch today

From taxonomy and today’s objective, prioritize:
- OpenRouter availability/routing issues (`2D`-style model unavailable)
- OpenRouter rate limit (`2E` / 429)
- generic API/auth failures (invalid key, provider/model mismatch)
- infra startup failures preventing Beaker responsiveness
- no-output or partial-output completion issues

## 7.2 Required analysis outputs

Produce:
1. A concise per-job status summary (`PASS`, `FAIL`, `PARTIAL`).
2. A per-failure mode table:
   - problem class id
   - evidence line(s) / trace snippet path
   - likely root cause
   - exact remediation action
3. A rerun recommendation list (only where likely to succeed with deterministic fix).

---

## 8) Apptainer mount visibility CLI (new small tool)

Problem to diagnose: LLM sees more in `/results` than intended.

Implement a small CLI under:
- `code_development_tools_agents/monitoring_and_evaluation/`

Suggested filename:
- `inspect_apptainer_mount_visibility.py`

## 8.1 CLI contract

Inputs:
- expected host results dir
- expected container mount target (`/results`)
- optional allowlist/denylist patterns
- optional max-depth

Checks:
1. Parse and print effective bind/mount arguments used for apptainer launch (from sbatch script + `exec_apptainer_harmonia.sh` context).
2. Inspect host-side tree snapshot of intended visible files.
3. Execute an in-container listing command to capture what container can actually see.
4. Diff expected vs actual visibility.
5. Emit machine-readable JSON and human-readable markdown summary.

Outputs:
- visibility report with:
  - host_path
  - container_path
  - expected_count
  - actual_count
  - unexpected_entries
  - missing_entries
  - risk level

## 8.2 Minimal validation

Run CLI against one successful and one failing run directory.
Attach findings to run ledger.

---

## 9) Visualization script planning with user (post-success)

After at least one successful run per target agent type:

1. Inspect output schema in successful `trace.json` + result artifacts.
2. Draft visualization design options with user:
   - run timeline (turn durations, timeout markers)
   - tool usage heatmap (BDI-tools runs)
   - output quality summary table (once metrics available)
   - error/failure-mode stacked bars across runs
3. Implement initial script in `code_development_tools_agents/monitoring_and_evaluation/` or `src/evaluation/visualization/` depending on reusability.
4. Save PNG/HTML outputs to a dedicated `analysis/` output folder and document reproducible usage.

---

## 10) Ordered execution checklist (for a fresh Claude instance)

1. Read latest instructions + codebase description docs.
2. Inventory existing config patterns and agent selectors.
3. Create new manual+automated configs for all 5 OpenRouter models.
4. Ensure 4 priority automated configs (CodeAct/BDI-tools x Gemini/Claude) are ready.
5. Regenerate associated env files for all relevant non-local configs.
6. Audit env/provider/model/token-source mapping.
7. Generate CPU sbatch scripts for the 4 priority runs.
8. Submit all 4 jobs; capture job IDs and expected outputs.
9. Monitor logs/results until completion.
10. Run log/trace analysis CLI and classify issues per taxonomy.
11. Implement/run mount-visibility CLI and document discrepancies.
12. Summarize outcomes, fixes, and rerun decisions.
13. Start visualization-script co-design based on successful outputs.

---

## 11) Definition of done for today

Minimum success criteria:
- 4 priority jobs submitted and completed (or failed with clear diagnosed root cause).
- At least one successful output for each target agent type (CodeAct and BDI-tools) is strongly preferred.
- All newly added OpenRouter configs exist (manual + automated) and have regenerated associated env files.
- Non-local configs have updated associated envs aligned with root `.env` key setup.
- Mount-visibility CLI implemented and run at least once with actionable output.
- Log review documented using taxonomy classes and evidence.

---

## 12) Risk register and mitigations

- **Rate limits / 429**: stagger submissions, add small delay in scripted turns if needed, rerun failed jobs after cooldown.
- **Model slug drift / deprecation**: validate OpenRouter model availability pre-run with small smoke call.
- **Context overrun / huge state**: keep context management settings aligned with latest guardrails.
- **Unexpected `/results` visibility**: use mount-inspection CLI before broad reruns.
- **Silent partial runs**: require output artifact presence checks, not just job exit code.

---

## 13) Notes on implementation style

- Prefer cloning nearest known-working configs to avoid schema drift.
- Keep naming deterministic so run tracking is easy.
- Never store raw API secrets in plan/audit artifacts; only variable provenance.
- Keep all diagnostics reproducible (command logs + report outputs).
