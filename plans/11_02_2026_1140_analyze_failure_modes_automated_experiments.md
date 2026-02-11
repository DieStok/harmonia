# Session Overview: Analyzing Failure Modes of Automated Experiments

**Date:** 11 February 2026, started ~10:00
**Continuation of:** 10 February 2026 session (SLURM job submission, log naming, initial log analysis)

---

## What We Discussed

### Phase 1: Log Naming and Job Relaunch (10 Feb, carried over)

**Problem:** SLURM logs had no timestamps in filenames, making it hard to distinguish runs.

**Decision:** Prepend `DD-MM-YYYY_HHMM` to all log filenames using `exec > redirect` pattern (since SBATCH directives don't support runtime variables).

**Implementation:**
- Modified `sbatch_template_gpu.sh` and `sbatch_template.sh`:
  - Set `#SBATCH --output=/dev/null` and `#SBATCH --error=/dev/null`
  - Added `exec > "logs/${LOG_TIMESTAMP}_{{experiment_name}}_${SLURM_JOB_ID}.out" 2> "logs/...err"`
- Fixed all 10 config YAMLs: changed `/data/one_metadata_table_gdc_schema/data/dou.csv` to `data/one_metadata_table_gdc_schema/data/dou.csv`
- Regenerated GPU jobs (6) and CPU jobs (4) separately
- Submitted all 10 jobs (46662631-46662640), cancelled stale job 46662630

### Phase 2: Log Analysis and Error Taxonomy (10-11 Feb)

**What we did:**
1. Read all 20 log files (10 `.out` + 10 `.err`)
2. Observed all `.err` files were empty
3. Created initial 5-category error taxonomy
4. Posed 5 Socratic questions to the user about error interpretation
5. User responded with corrections and directions

**User corrections to initial analysis:**
- `magneto_ft_bp` is NOT a hallucination — it's the default schema matching algorithm in bdikit (confirmed in `bdikit/schema_matching/matcher_factory.py`)
- `get_gdc_acceptable_values` is NOT a hallucination — it's a custom tool in `src/bdikit_context/agent.py:286` wrapping bdikit's `preview_domain()`
- kimi-k2 DOES support tool calling (confirmed via HuggingFace docs); the issue is the Ollama template missing `{{ .Tools }}`
- mimo-v2-flash free tier expired on OpenRouter — should be removed entirely

### Phase 3: Trace Cross-Referencing (11 Feb)

**What we did:**
1. Read trace.json files for all experiments in `results/` to determine LLM-side vs infrastructure-side timeouts
2. Discovered the "second wave" infrastructure timeout pattern: identical `[180, 300, 180, 180, 360, 600, 300, 120]` timeout signature across 4 experiments, caused by Beaker server hanging after first run
3. Found OpenRouter free-tier expiration (HTTP 404) for mimo-v2-flash
4. Found OpenRouter rate limiting (HTTP 429) for glm-4.5-air after turn 1
5. Confirmed devstral/anyllm_devstral never use Beaker tools — they output text guidance instead
6. Found qwen3-coder fabricated entirely unrelated project management data when file was missing (0% accuracy)
7. Found qwen3-coder run 2 crashed with WebSocket message size exceeded (5.78MB > 4MB limit)

### Phase 4: Documentation and Tooling (11 Feb, current)

**Output produced:**
- `documentation/processes/11_02_2026_interpreting_logs_and_traces.md` — comprehensive failure mode taxonomy with 13 categories, diagnostic flowchart, and remediations
- `plans/11_02_2026_1140_analyze_failure_modes_automated_experiments.md` — this document
- Starting: `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` — CLI tool for automated log/trace analysis
- Starting: `code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml` — machine-readable error taxonomy

---

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Remove mimo-v2-flash config | Free tier expired on OpenRouter, no longer usable |
| Fix olmo3 config to use `olmo-3:32b-think` | `olmo-3.1:32b` doesn't exist in Ollama registry; we have `olmo-3:32b-think` and `olmo-3:7b-instruct` downloaded |
| Investigate kimi-k2 with `huihui_ai/kimi-k2` community model | Standard Ollama kimi-k2 template lacks `{{ .Tools }}` block; community variant has it |
| Restructure container workspace with symlinks | Current mount strategy causes FileNotFoundError when kernel cwd != `/workspace` |
| Build CLI log analysis tool | Needed for systematic, repeatable analysis of experiment runs by both humans and agents |
| Use YAML-based problem taxonomy | Extensible, machine-readable, can be updated as new failure modes are discovered |

---

## Current Plans (Pending Implementation)

### Immediate (this session)

1. **CLI tool for log/trace analysis** (`read_and_analyze_logs_and_traces_cli.py`)
   - Analyze newest N runs from log folder
   - Cross-reference logs with trace.json
   - Categorize errors using YAML taxonomy
   - Output structured report suitable for agents and humans
   - Currently: discussing spec and edge cases

2. **YAML error taxonomy** (`types_of_log_and_trace_problems.yaml`)
   - Machine-readable version of the 13 failure modes documented
   - Keywords, regex patterns, example output for each
   - Specific remediations per category

### Next (after CLI tool)

3. **Remove mimo-v2-flash config**
   - Delete `experiments/.../configs/automated/dou_harmonization_mimo-v2-flash.yaml`
   - Delete `experiments/.../configs/automated/dou_harmonization_anyllm_openrouter.yaml` (also uses mimo-v2-flash:free)

4. **Fix olmo3 config**
   - Change model to `olmo-3:32b-think` or `olmo-3:7b-instruct`
   - Add comment about OLMo 3.1 32B availability on HuggingFace for custom Ollama import

5. **Fix kimi-k2 tool calling**
   - Option A: Pull `huihui_ai/kimi-k2` community model
   - Option B: Create custom Modelfile with tool template
   - Needs discussion about which approach

6. **Workspace symlink restructuring**
   - Modify `exec_apptainer_harmonia.sh` to create per-experiment workspace with:
     - Symlinks to dataset `data/` folders only (excluding solution files)
     - Symlink `results/` to the experiment-specific timestamped results folder
   - This should fix FileNotFoundError regardless of kernel cwd

7. **OLMo 3.1 32B custom model import**
   - Download GGUF from https://huggingface.co/allenai/Olmo-3.1-32B-Instruct
   - Create Modelfile and `ollama create olmo-3.1:32b`
   - User wants to discuss approach

---

## What Has Been Done (Completed Actions)

| Action | Status | Files Modified |
|--------|--------|----------------|
| Timestamp-prepended log naming | Done | `sbatch_template_gpu.sh`, `sbatch_template.sh` |
| Fix config YAML paths (`/data/` -> `data/`) | Done | All 10 config YAMLs in `configs/automated/` |
| Generate and submit GPU jobs | Done | 6 job scripts in `jobs/` |
| Generate and submit CPU jobs | Done | 4 job scripts in `jobs/` |
| Cancel stale job 46662630 | Done | N/A |
| Read and analyze all 20 log files | Done | N/A (analysis only) |
| Cross-reference traces for all experiments | Done | N/A (analysis only) |
| Verify bdikit API claims | Done | Confirmed `magneto_ft_bp` and `get_gdc_acceptable_values` are real |
| Investigate kimi-k2 tool calling docs | Done | Found root cause: Ollama template missing `{{ .Tools }}` |
| Write failure mode taxonomy doc | Done | `documentation/processes/11_02_2026_interpreting_logs_and_traces.md` |
| Write session overview | Done | This file |

---

## Key File Paths

| Resource | Path |
|----------|------|
| Failure mode taxonomy | `documentation/processes/11_02_2026_interpreting_logs_and_traces.md` |
| CLI tool (in progress) | `code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py` |
| Error taxonomy YAML (in progress) | `code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml` |
| SLURM logs | `logs/10-02-2026_*` |
| Experiment results/traces | `results/dou_harmonization_*_20260210_*/trace.json` |
| GPU SBATCH template | `sbatch_template_gpu.sh` |
| CPU SBATCH template | `sbatch_template.sh` |
| Container exec script | `exec_apptainer_harmonia.sh` |
| Config YAMLs | `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/` |
| bdikit agent source | `src/bdikit_context/agent.py` |

All paths relative to: `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/`
