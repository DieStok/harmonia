---
title: "refactor: geo-harmonizer v2 Project Structure, CLAUDE.md Hierarchy, and Development Loop Enforcement"
type: refactor
status: active
date: 2026-04-07
origin: docs/research_output/deep_research_LLM_metadata_harmonisation_project_April_2026/Gene_Expression_Omnibench_Six_Month_Plan_Architecture_Roadmap_v2.md
---

# refactor: geo-harmonizer v2 Project Structure, CLAUDE.md Hierarchy, and Development Loop Enforcement

## Overview

Set up the new geo-harmonizer v2 codebase as a fresh git repository at `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/geo_harmonizer/`, alongside the existing harmonia codebase. This involves three coordinated deliverables:

1. **Directory structure** — full tree from architecture doc Section 2.2 with `code_to_use_for_porting.txt` reference files
2. **CLAUDE.md + AGENTS.md** — enforced brainstorm→plan→implement→review→compound development loop, adapted for Python/HPC
3. **CLAUDE.md hierarchy reorganization** — split the monolithic top-level CLAUDE.md into HPC-only shared rules + subproject-specific instructions

## Problem Statement / Motivation

The current project has a single CLAUDE.md at `/hpc/compgen/projects/llm_GEO_project/.claude/CLAUDE.md` that contains almost exclusively harmonia-specific instructions (experiment configs, Beaker workflows, Ollama management, model registries). This creates two problems:

1. **Scope pollution**: When working on any other subproject under `llm_GEO_project/` (SRAgent, valentine, bdi-kit, etc.), Claude receives harmonia-specific instructions that are irrelevant and waste context.
2. **No home for geo-harmonizer**: The new v2 codebase needs its own project-specific instructions, and stacking them into the same top-level CLAUDE.md would make it unmanageable.

Additionally, the existing workflow (brainstorm→plan→implement) exists informally in harmonia (7 brainstorm docs, 40+ plans) but has **no enforcement**. The geo-harmonizer codebase should enforce this discipline from day one via hooks and CLAUDE.md rules.

## Proposed Solution

### Architecture: Three-Layer CLAUDE.md Hierarchy

```
/hpc/compgen/projects/llm_GEO_project/
├── .claude/
│   ├── CLAUDE.md                          # Layer 1: HPC-only shared rules + Verification Protocol
│   ├── settings.local.json                # MODIFIED — Entire hooks removed, session-start info hook added
│   └── hooks/
│       ├── project-safe-commands.py       # Existing — updated with geo-harmonizer scripts
│       └── session-info.sh                # NEW — outputs cwd, model, Entire status
│
├── harmonia_metadata_agent/analysis/dstoker/
│   ├── harmonia/                           # EXISTING
│   │   ├── AGENTS.md                      # NEW — source of truth (the actual file)
│   │   ├── .claude/
│   │   │   ├── CLAUDE.md                  # Symlink → ../../AGENTS.md (NEW)
│   │   │   └── settings.json              # Existing Entire.dev hooks — unchanged
│   │   └── ...
│   │
│   └── geo_harmonizer/                     # NEW — the v2 codebase
│       ├── AGENTS.md                      # NEW — source of truth (the actual file)
│       ├── .claude/
│       │   ├── CLAUDE.md                  # Symlink → ../../AGENTS.md
│       │   ├── settings.json              # Hooks config (NEW — hooks commented out initially)
│       │   ├── hooks/
│       │   │   ├── enforce-plan-before-code.py   # (NEW)
│       │   │   └── check-tests-on-stop.py        # (NEW)
│       │   ├── agents/
│       │   │   └── adversarial-reviewer.md       # (NEW)
│       │   └── learnings/                        # (NEW — empty)
│       ├── docs/
│       │   └── deep_research_outputs/     # Copied from harmonia research output
│       └── ...
```

**Symlink direction (following [agents.md spec](https://agents.md/#examples)):**
- `AGENTS.md` at repo root is the **actual file** (source of truth)
- `.claude/CLAUDE.md` is a **symlink** pointing to `../../AGENTS.md`
- This ensures any AI coding tool (Claude Code, Cursor, Codex, etc.) finds the instructions

**How Claude resolves instructions**: When Claude Code runs inside `geo_harmonizer/`, it reads:
1. User's global `~/.claude/CLAUDE.md` (HPC quick reference — already exists)
2. Project-level `/hpc/compgen/projects/llm_GEO_project/.claude/CLAUDE.md` (HPC shared rules + Verification Protocol)
3. Subproject-level `geo_harmonizer/.claude/CLAUDE.md` → resolves via symlink to `AGENTS.md` (geo-harmonizer-specific)

All three layers compose. No conflicts because each layer has a distinct scope.

## Technical Approach

### Phase 1: Create geo-harmonizer Directory Structure

Create all directories from architecture doc Section 2.2, with every leaf directory containing a `code_to_use_for_porting.txt` file that includes:
- The priority level ([P1], [P2], or [P3])
- A brief description of the directory's purpose
- Pointers to relevant lines in the architecture doc
- Pointers to relevant files in the existing harmonia codebase (where applicable)

**Complete directory tree to create:**

```
geo_harmonizer/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   └── code_to_use_for_porting.txt     # Points to: tracing.py, config.py from harmonia
│   ├── search/
│   │   ├── geo_database/
│   │   │   └── code_to_use_for_porting.txt
│   │   ├── embeddings/
│   │   │   └── code_to_use_for_porting.txt
│   │   └── code_to_use_for_porting.txt
│   ├── harmonization/
│   │   ├── agents/
│   │   │   └── code_to_use_for_porting.txt  # Points to: harmonia src/ agent contexts
│   │   ├── prompts/
│   │   │   └── code_to_use_for_porting.txt
│   │   ├── tools/
│   │   │   └── code_to_use_for_porting.txt  # Points to: harmonia BDI-Kit tools
│   │   └── code_to_use_for_porting.txt
│   ├── evaluation/
│   │   └── code_to_use_for_porting.txt      # Points to: harmonia src/evaluation/
│   ├── dashboard/
│   │   └── code_to_use_for_porting.txt      # Points to: harmonia src/dashboard/
│   └── experiment/
│       └── code_to_use_for_porting.txt      # Points to: harmonia src/automation/
├── benchmark/
│   ├── tasks/
│   │   ├── single_table_gdc/
│   │   │   └── code_to_use_for_porting.txt
│   │   ├── two_table/
│   │   │   └── code_to_use_for_porting.txt
│   │   ├── n_table/
│   │   │   └── code_to_use_for_porting.txt
│   │   └── search_queries/
│   │       └── code_to_use_for_porting.txt
│   ├── baselines/
│   │   └── code_to_use_for_porting.txt
│   └── code_to_use_for_porting.txt
├── sandbox/
│   └── code_to_use_for_porting.txt          # Points to: harmonia Apptainer configs
├── experiments/
│   ├── configs/
│   │   └── code_to_use_for_porting.txt
│   ├── sweeps/
│   │   └── code_to_use_for_porting.txt
│   └── results/                              # gitignored
│       └── .gitkeep
├── scripts/
│   └── code_to_use_for_porting.txt
├── tests/
│   └── code_to_use_for_porting.txt
├── plans/
│   ├── brainstorm/
│   ├── specs/
│   └── reviews/
├── paper/
│   ├── figures/
│   │   └── .gitkeep
│   ├── tables/
│   │   └── .gitkeep
│   └── code_to_use_for_porting.txt
├── logs/                                     # gitignored
│   └── .gitkeep
├── .claude/
│   ├── CLAUDE.md                            # Symlink → ../../AGENTS.md
│   ├── settings.json                        # Hooks commented out initially
│   ├── hooks/
│   │   ├── enforce-plan-before-code.py
│   │   └── check-tests-on-stop.py
│   ├── agents/
│   │   └── adversarial-reviewer.md
│   └── learnings/
├── docs/
│   └── deep_research_outputs/               # Copied from harmonia research output
│       └── deep_research_LLM_metadata_harmonisation_project_April_2026/
│           └── [all files from harmonia research output]
├── AGENTS.md                                # Source of truth (the actual file)
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml
└── README.md
```

**Tasks:**

- [ ] `mkdir -p` all directories
- [ ] Write each `code_to_use_for_porting.txt` file with priority markers and references
- [ ] Create `.gitignore` (experiments/results/, logs/, .venv/, .phoenix/, *.sif*, *.pyc, .env, cache/, .entire/tmp/, .entire/metadata/, .entire/logs/, .entire/settings.local.json)
- [ ] Create minimal `pyproject.toml` (project name, Python >=3.11, dev deps: ruff, vulture, pytest)
- [ ] Copy `harmonia/docs/research_output/deep_research_LLM_metadata_harmonisation_project_April_2026/` into `geo_harmonizer/docs/deep_research_outputs/`
- [ ] `git init` the repo
- [ ] Create initial commit

### Phase 2: Write AGENTS.md for geo-harmonizer

The `AGENTS.md` at `geo_harmonizer/AGENTS.md` is the source of truth. `.claude/CLAUDE.md` is a symlink to it. It enforces the development loop and is adapted from the zip file's CLAUDE.md with these modifications:

**Adaptations from the template:**

| Template (JS/TS) | geo-harmonizer (Python/HPC) |
|---|---|
| `npm run *`, `npx *` | `.venv/bin/python *`, `uv pip install *` |
| `src/`, `lib/`, `app/` | `src/` only |
| `tests/**`, `test/**`, `__tests__/**` | `tests/` only |
| Docker references | Apptainer (`apptainer exec`, `apptainer instance`) |
| No mention of HPC | SLURM patterns, GPU partition for local LLMs |
| Generic function signatures | Python type hints, Pydantic models, dataclasses |
| prettier/black/rustfmt | `ruff format`, `ruff check` |
| Mermaid to `.mermaid` files | Mermaid in markdown (renderable in docs) |

**Key sections of the geo-harmonizer CLAUDE.md:**

1. **Core Philosophy** — 80% planning, 20% execution. No code without a plan.
2. **Mandatory Development Loop** — Phases 1-5 with enforcement:
   - Phase 1: Brainstorm (`/ce:brainstorm`) → `plans/brainstorm/<feature>.md`
   - Phase 2: Plan (`/ce:plan`) → `plans/specs/<feature>.md`
   - Phase 3: Implement with TDD (`/ce:work`) — tests first, then code
   - Phase 4: Adversarial Review (`/ce:review`) → `plans/reviews/<feature>-review.md`
   - Phase 5: Compound (`/ce:compound`) → `.claude/learnings/`
3. **Project-Specific Context:**
   - Python environment: always use `.venv/bin/python`, never conda
   - Run ID system: 8-char hex via `secrets.token_hex(4)`
   - Gold standard data: `../../raw/datasets_harmonia/` (relative path)
   - Architecture doc: pointer to the roadmap v2 doc
   - Key data contracts: BenchmarkTask, HarmonizationResult, SearchResult, ExperimentSuite
4. **Mermaid Diagram Requirements** — architecture, sequence, class, ER diagrams in plans
5. **Function Signature Requirements** — typed Python signatures before implementation
6. **Context Management** — `/compact` at 50%, never exceed 70%
7. **Model Usage** — Opus for planning/review, Sonnet for implementation

**What is NOT in this CLAUDE.md** (belongs in top-level or harmonia-specific):
- HPC directory structure rules (top-level)
- SLURM account/partition details (top-level)
- Beaker/Archytas experiment workflows (harmonia-specific)
- Ollama management (harmonia-specific)
- Model registry management (harmonia-specific)
- Entire.dev integration (harmonia-specific)

**Tasks:**

- [ ] Write `geo_harmonizer/AGENTS.md` — the actual file, adapted from template
- [ ] Create symlink: `geo_harmonizer/.claude/CLAUDE.md` → `../../AGENTS.md`

### Phase 3: Write Hooks and Settings (Inactive Initially)

**enforce-plan-before-code.py** — adapted for Python project:
- `enforced_dirs` = `["src/"]` (not lib/ or app/)
- Checks for `.md` files in `plans/specs/` that have YAML frontmatter with:
  - `status: active`
  - `date: YYYY-MM-DD` that is less than 8 days old (relative to today)
- Parses frontmatter between `---` delimiters, extracts `status` and `date` fields
- If no qualifying plan found, blocks with message explaining what's needed
- This prevents stale/completed plans from satisfying the gate

**check-tests-on-stop.py** — adapted for Python project:
- `impl_extensions` = `[".py"]` only
- `impl_dirs` = `["src/"]`
- Test file patterns: `test_*.py`, `*_test.py`, `tests/` mirror
- Uses `git diff --name-only HEAD` to find modified files

**settings.json** — hooks present but COMMENTED OUT:
- The `settings.json` includes the full hooks config but with the hooks section commented out using `"_hooks"` key (since JSON doesn't support comments, we use the underscore-prefix convention to disable)
- A `"_NOTE"` field explains: "Rename _hooks to hooks to activate enforcement after directory setup is complete"
- Permissions whitelist adapted for Python/HPC commands

```json
{
  "$schema": "https://code.claude.com/schemas/settings.json",
  "permissions": {
    "allow": [
      "Bash(git *)",
      "Bash(ls *)",
      "Bash(find *)",
      "Bash(mkdir *)",
      "Bash(cp *)",
      "Bash(mv *)",
      "Bash(.venv/bin/python *)",
      "Bash(uv pip *)",
      "Bash(ruff *)",
      "Bash(pytest *)",
      "Bash(entire *)",
      "Read(*)",
      "Edit(plans/**)",
      "Edit(.claude/**)",
      "Write(plans/**)",
      "Write(.claude/**)",
      "Write(tests/**)"
    ],
    "deny": []
  },
  "_NOTE": "Rename '_hooks' to 'hooks' to activate enforcement. Do this after the directory structure is set up and initial commit is done.",
  "_hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/enforce-plan-before-code.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/check-tests-on-stop.py"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/code-quality-on-stop.sh"
          }
        ]
      }
    ]
  }
}
```

**code-quality-on-stop.sh** — runs vulture (dead code detection) and ruff (linting + formatting) as a Stop hook:
- Runs `ruff check src/ tests/` for linting errors
- Runs `ruff format --check src/ tests/` for formatting violations
- Runs `vulture src/` for dead code detection
- Reports findings but does NOT block (informational, not gating)
- Only runs if `.venv/` exists (skips gracefully if no venv yet)

```bash
#!/bin/bash
# Stop hook: run code quality checks after each block of work
if [ ! -d ".venv" ]; then
    exit 0  # No venv yet, skip silently
fi

echo ""
echo "--- Code Quality Check ---"

# Ruff lint
echo ">> ruff check:"
.venv/bin/ruff check src/ tests/ 2>/dev/null || true

# Ruff format check
echo ">> ruff format --check:"
.venv/bin/ruff format --check src/ tests/ 2>/dev/null || true

# Vulture dead code detection
echo ">> vulture:"
.venv/bin/vulture src/ 2>/dev/null || true

echo "--- End Code Quality Check ---"
```

This hook is also initially under `_hooks` and gets activated alongside the other hooks.

**Hook activation:** After all phases are complete, the user will be prompted: "Directory structure is set up and committed. Ready to activate enforcement hooks? This will require a plan in `plans/specs/` before any code edits to `src/`, will check for test files at the end of each turn, and will run ruff + vulture after each block of work." If yes, rename `_hooks` to `hooks` in settings.json.

**Tasks:**

- [ ] Write `geo_harmonizer/.claude/hooks/enforce-plan-before-code.py` (adapted for Python)
- [ ] Write `geo_harmonizer/.claude/hooks/check-tests-on-stop.py` (adapted for Python)
- [ ] Write `geo_harmonizer/.claude/hooks/code-quality-on-stop.sh` (vulture + ruff)
- [ ] Write `geo_harmonizer/.claude/settings.json` (hooks commented out via `_hooks` key)
- [ ] `chmod +x` all hook scripts
- [ ] Write `geo_harmonizer/.claude/agents/adversarial-reviewer.md` (from template)

### Phase 4: Create harmonia-specific AGENTS.md

Copy the current harmonia-specific content from `/hpc/compgen/projects/llm_GEO_project/.claude/CLAUDE.md` into a new `AGENTS.md` at the harmonia repo root. Then symlink `.claude/CLAUDE.md` to it.

This file keeps ALL current harmonia-specific instructions:

- Before Starting Any Task (read latest instructions, check datasets)
- After Code Changes (codebase description updates)
- After Experiment Runs (log auditing)
- Project Overview + Key Paths
- Current State
- Experiment Types (Automated, Manual)
- Running Experiments (manual with --monitor, automated)
- Local LLM Jobs (GPU partition)
- Python Environment (.venv)
- Model Registry Management
- Practical Lessons

**Note:** Verification Protocol moves to the top-level CLAUDE.md (applies to all subprojects).

**Important:** The existing `harmonia/.claude/settings.json` (Entire.dev hooks) stays untouched. The new AGENTS.md is additive — it does not conflict with settings.json.

**Tasks:**

- [ ] Write `harmonia/AGENTS.md` with current harmonia-specific content (source of truth)
- [ ] Create symlink: `harmonia/.claude/CLAUDE.md` → `../../AGENTS.md`

### Phase 5: Slim Down Top-Level CLAUDE.md + Add Session-Info Hook

Replace `/hpc/compgen/projects/llm_GEO_project/.claude/CLAUDE.md` with HPC-only shared rules. Content to KEEP:

```markdown
# HPC Project Guidelines (llm_GEO_project)

## Subproject Navigation
| Subproject | Path | Instructions |
|------------|------|--------------|
| Harmonia (v1) | harmonia_metadata_agent/analysis/dstoker/harmonia/ | AGENTS.md (→ .claude/CLAUDE.md) |
| geo-harmonizer (v2) | harmonia_metadata_agent/analysis/dstoker/geo_harmonizer/ | AGENTS.md (→ .claude/CLAUDE.md) |

## Directory Structure (Mandatory)
[Keep the existing directory structure rules table]

## SLURM Commands
[Keep ALL existing SLURM content — srun, sbatch, squeue, seff, etc.]

## Environment Management
[Keep: use .venv not conda, uv for packages, no module load]

## Working on the HPC
[Keep: submit/transfer/compute node descriptions]

## Verification Protocol for Capability Claims
[Keep — applies to ALL subprojects]

## Restrictions
[Keep: no root/sudo, no SSHFS, no module load, home 5GB limit]
```

Content to REMOVE (moved to harmonia/AGENTS.md):
- Before Starting Any Task
- After Code Changes
- After Experiment Runs (Log Auditing)
- Project Overview
- Key Paths
- Current State
- Experiment Types
- Running Experiments
- Local LLM Jobs
- Python Environment (harmonia-specific paths)
- Model Registry Management
- Practical Lessons

**Session-Info Hook (parent level):**

Add a new hook to `/hpc/compgen/projects/llm_GEO_project/.claude/settings.local.json` that fires on `SessionStart` and outputs diagnostic information:

Script: `/hpc/compgen/projects/llm_GEO_project/.claude/hooks/session-info.sh`

```bash
#!/bin/bash
# Session start info hook — outputs working directory, model, and Entire status
echo "============================================"
echo "SESSION INFO"
echo "============================================"
echo "Working directory: $(pwd)"
echo "Git repo root:     $(git rev-parse --show-toplevel 2>/dev/null || echo 'NOT A GIT REPO')"
echo "Git branch:        $(git branch --show-current 2>/dev/null || echo 'N/A')"
echo ""
echo "--- Entire CLI Status ---"
if command -v entire &>/dev/null; then
    entire status --detailed 2>/dev/null || echo "Entire: not enabled in this directory"
else
    echo "Entire CLI: NOT INSTALLED"
fi
echo "============================================"
```

Register in `settings.local.json`:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash /hpc/compgen/projects/llm_GEO_project/.claude/hooks/session-info.sh"
          }
        ]
      }
    ]
  }
}
```

**Tasks:**

- [ ] Write the slimmed-down top-level CLAUDE.md (keep Verification Protocol)
- [ ] Verify harmonia/AGENTS.md has all moved content
- [ ] Write `/hpc/compgen/projects/llm_GEO_project/.claude/hooks/session-info.sh`
- [ ] `chmod +x` the session-info hook
- [ ] Update `settings.local.json`: remove hardcoded harmonia Entire hooks, add SessionStart info hook, keep Bash safety hook

## code_to_use_for_porting.txt File Format

Each reference file follows this format:

```
# <Directory Name>
Priority: [P1|P2|P3]

## Purpose
<1-2 sentence description from architecture doc>

## Architecture Doc References
- Gene_Expression_Omnibench_Six_Month_Plan_Architecture_Roadmap_v2.md
  - Section: <section name>
  - Lines: <line range>
  - Key components: <list of classes/functions described>

## Harmonia Codebase References
- <relative path from harmonia/> → <what to port/evolve>
  - Key files: <specific filenames>
  - What to keep: <what's battle-tested>
  - What to change: <what needs evolution>

## Data Contracts (if applicable)
- <dataclass name> — see architecture doc line <N>

## Dependencies
- Depends on: <other directories that must be built first>
- Depended on by: <directories that need this>
```

## Cross-Reference Map: Architecture Doc → Directory → Source Reports

Each `code_to_use_for_porting.txt` file should include the references below for its directory. All file references are relative to `docs/deep_research_outputs/deep_research_LLM_metadata_harmonisation_project_April_2026/`.

**Source Report Files:**

| Label | Filename |
|-------|----------|
| Roadmap | `Gene_Expression_Omnibench_Six_Month_Plan_Architecture_Roadmap_v2.md` |
| Report A | `Part_A_DeepResearch_Claude_LLM-based metadata harmonization for omics_state of the art and benchmark design.md` |
| Report B | `Part_B_DeepResearch_Claude_Designing a RAG search pipeline over GEO metadata for omics data harmonization.md` |
| Report C | `merged_Part_C_DeepResearch_Claude_optimal_agent_architecture_for_omics_metadata_harmonization.md` |
| Report D | `Part_D_with_QwenGemma_DeepResearch_Claude_Optimizing LLMs for Omics Metadata Harmonization A Comprehensive Methodological Guide.md` |
| Harbor | `harbor_usage_usability_analysis.md` |

### src/core/ [P1-P2]

| What | Source | Lines/Section |
|------|--------|---------------|
| Tracing (Phoenix/OTel) | Roadmap | Lines 619-633 (what to keep), lines 674-687 (observability stack) |
| OTel span hierarchy | Report C | Lines 275-281 |
| Platform comparison (Phoenix vs LangSmith vs W&B) | Report C | Lines 261-286 |
| Caching (SHA-256 LLM call cache) | Roadmap | Lines 518-519 |
| Config (phase-specific model overrides) | Roadmap | Lines 520-521 |
| Reproducibility (4-layer strategy) | Roadmap | Lines 689-702 |
| Inference backend (vLLM/SGLang) | Roadmap | Lines 634-672 |
| Inference framework comparison | Report D | Lines 11-34 |
| GPU deployment matrix | Report D | Lines 38-79 |
| Quantization (AWQ vs GPTQ) | Report D | Lines 82-103 |
| **Harmonia source** | `harmonia/src/` | `ensure_phoenix_server.py`, tracing config in experiment YAML |

### src/harmonization/agents/ [P1]

| What | Source | Lines/Section |
|------|--------|---------------|
| BDI-Kit agent (ReAct + tools) | Roadmap | Lines 443-444 (KEEP) |
| CodeAct agent | Roadmap | Lines 444 (KEEP) |
| Coding agent (frontier: Claude Code/Codex via Harbor) | Roadmap | Lines 498-506 |
| Harbor task format example | Harbor | Section 4.2 |
| ApptainerEnvironment implementation sketch | Harbor | Section 5.3 |
| Harbor full onboarding guide | Harbor | Full document |
| Compositional pipeline (Matchmaker reimpl.) | Roadmap | Lines 508-509 |
| Matchmaker/Magneto pipeline design | Report C | Lines 213-235 |
| Multi-agent (P3, interface only) | Roadmap | Lines 532-533 |
| SRAgent agent-as-tool-factory pattern | Report C | Lines 95-127 |
| 8-pattern SRAgent inventory | Report C | Lines 412-426 |
| Case against multi-agent as default | Report C | Lines 153-183 |
| Conditions when multi-agent earns overhead | Report C | Lines 173-183 |
| AutoAgent meta-optimization | Roadmap | Lines 223-225 |
| AutoAgent setup guide | Harbor | Section 4.5 |
| **Harmonia source** | `harmonia/src/` | `bdikit_context/`, `codeact_context/`, `code_context/` |

### src/harmonization/prompts/ [P1-P2]

| What | Source | Lines/Section |
|------|--------|---------------|
| Eleven-variable taxonomy (effect sizes) | Report A | Lines 131-149 |
| Context content ablation (ConStruM) | Roadmap | Lines 113, 217-219 |
| Prompt versioning (Langfuse) | Roadmap | Lines 696-699 |
| **Harmonia source** | `harmonia/src/` | `context_management/`, experiment YAML prompt fields |

### src/harmonization/tools/ [KEEP]

| What | Source | Lines/Section |
|------|--------|---------------|
| BDI-Kit 5 tools | Roadmap | Lines 411 |
| Structured output (Pydantic + retry) | Roadmap | Lines 524-525 |
| Regex-first extraction (SRAgent Pattern 5) | Report C | Lines 412-426 |
| **Harmonia source** | `harmonia/src/bdikit_context/` | Tool wrappers |

### src/evaluation/ [P1]

| What | Source | Lines/Section |
|------|--------|---------------|
| Metrics extension (value mapping, cross-table) | Roadmap | Lines 452-456, 632-633 |
| Benchmark task runner | Roadmap | Lines 454 |
| Statistical comparison (McNemar, bootstrap, Friedman) | Roadmap | Lines 455-456, 516-517 |
| Statistical test selection table | Report D | Lines 151-178 |
| Switching criteria for tests | Report D | Lines 169-178 |
| Failure taxonomy (20 classes, 6 categories) | Report A | Lines 153-167 |
| **Harmonia source** | `harmonia/src/evaluation/` | `metrics.py`, `calculate_metrics.py` |

### src/search/ [P2-P3]

| What | Source | Lines/Section |
|------|--------|---------------|
| GEO database (SQLite + FTS5) | Roadmap | Lines 435-436 |
| Embedding models comparison | Report B | Lines 80-101 |
| Reranker comparison | Report B | Lines 92-101 |
| Seven retrieval strategies | Report B | Lines 7-58 |
| HPC infrastructure for search pipeline | Report B | Lines 148-174 |
| Qdrant Apptainer deployment | Roadmap | Lines 703-725 |
| LightRAG vs GraphRAG | Report B | Lines 136-140 |
| Agentic RAG patterns (Adaptive, CRAG) | Report B | Lines 130-144 |
| Query expansion (BMQExpander) | Roadmap | Lines 126-128 |

### src/experiment/ [P1]

| What | Source | Lines/Section |
|------|--------|---------------|
| Sweep (successive halving methodology) | Roadmap | Lines 514-515 |
| Four-phase methodology | Report D | Lines 159-167 |
| Experimental design methodology | Report D | Lines 151-178 |
| **Harmonia source** | `harmonia/src/automation/` | `run_experiment.py`, `generate_jobs.py` |

### src/dashboard/ [KEEP+EXTEND]

| What | Source | Lines/Section |
|------|--------|---------------|
| 8-tab Plotly Dash structure | Roadmap | Lines 458, 626-627 |
| **Harmonia source** | `harmonia/src/dashboard/` | Full dashboard code |

### benchmark/ [P1]

| What | Source | Lines/Section |
|------|--------|---------------|
| BenchmarkTask dataclass | Roadmap | Lines 546-556 |
| Gold standard construction (B1) | Roadmap | Lines 189-192 |
| Task levels 1-5 | Roadmap | Lines 467-471 |
| Valentine baselines (S1) | Roadmap | Lines 195-196 |
| Schema matching systems with performance numbers | Report A | Lines 9-57 |
| Value mapping landscape | Report A | Lines 59-67 |
| Omics domain gap analysis | Report A | Lines 69-83 |

### sandbox/ [KEEP+EVOLVE]

| What | Source | Lines/Section |
|------|--------|---------------|
| Apptainer sandbox details | Report C | Lines 317-336 |
| Coding agent container setup | Report C | Lines 317-336 |
| "What to Avoid" guidance | Report C | Lines 391-397 |
| Four-phase architecture roadmap | Report C | Lines 377-408 |
| vLLM on SLURM with Apptainer | Roadmap | Lines 638-656 |
| **Harmonia source** | `harmonia/` | `exec_apptainer_harmonia.sh`, `*.def` files |

### experiments/ [EVOLVE]

| What | Source | Lines/Section |
|------|--------|---------------|
| P1 experiments (irreducible core) | Roadmap | Lines 186-212 |
| P2 experiments (strengthen paper) | Roadmap | Lines 213-229 |
| P3 experiments (stretch goals) | Roadmap | Lines 232-241 |
| Month-by-month timeline | Roadmap | Lines 264-358 |
| Contingency plans and go/no-go gates | Roadmap | Lines 360-390 |
| Venue requirements and timeline | Report D | Lines 200-230 |
| **Harmonia source** | `harmonia/experiments/` | YAML config format, `configs/automated/` |

### paper/ [Month 6]

| What | Source | Lines/Section |
|------|--------|---------------|
| Paper section mapping | Roadmap | Lines 248-261 |
| Target venues (NeurIPS, VLDB, BioDMS) | Roadmap | Lines 76-78, 155-157 |
| Resource requirements | Roadmap | Lines 391-403 |

## Implementation Phases

### Phase 1: Directory Structure [~30 min]

1. Create all directories with `mkdir -p`
2. Write all `code_to_use_for_porting.txt` files
3. Create `.gitignore`, `pyproject.toml`, minimal `README.md`
4. Copy deep research outputs from harmonia
5. `git init` + initial commit

**Success criteria:**

- [ ] All directories from Section 2.2 exist
- [ ] Every leaf directory has a `code_to_use_for_porting.txt` with priority markers
- [ ] `docs/deep_research_outputs/` contains the copied research folder
- [ ] `git init` succeeds with clean initial commit
- [ ] `.gitignore` excludes results/, logs/, .venv/, .phoenix/, *.sif*, cache/, .entire/ patterns

### Phase 2: AGENTS.md [~30 min]

1. Write `geo_harmonizer/AGENTS.md` (the actual file, source of truth)
2. Create symlink: `.claude/CLAUDE.md` → `../../AGENTS.md`
3. Verify symlink resolves correctly

**Success criteria:**

- [ ] `AGENTS.md` contains all 5 development loop phases
- [ ] Python/HPC adaptations are in place (not JS/TS references)
- [ ] Entire CLI commands reference section included
- [ ] Symlink works: `cat geo_harmonizer/.claude/CLAUDE.md` shows AGENTS.md content

### Phase 3: Hooks and Settings [~20 min]

1. Write both hook scripts (adapted for Python)
2. Write settings.json with permissions and hooks under `_hooks` key (commented out)
3. Write adversarial-reviewer.md agent
4. Make hooks executable

**Success criteria:**

- [ ] Hook scripts are executable (`chmod +x`)
- [ ] `python3 .claude/hooks/enforce-plan-before-code.py` runs without errors (when given mock stdin)
- [ ] `python3 .claude/hooks/check-tests-on-stop.py` runs without errors
- [ ] settings.json is valid JSON with `_hooks` key (not `hooks`)
- [ ] `_NOTE` field explains how to activate

### Phase 4: harmonia AGENTS.md [~15 min]

1. Write `harmonia/AGENTS.md` with all harmonia-specific content (source of truth)
2. Create symlink: `harmonia/.claude/CLAUDE.md` → `../../AGENTS.md`
3. Verify no conflict with existing settings.json

**Success criteria:**

- [ ] `harmonia/AGENTS.md` contains all harmonia-specific instructions
- [ ] Existing `harmonia/.claude/settings.json` is untouched
- [ ] Symlink works: `cat harmonia/.claude/CLAUDE.md` shows AGENTS.md content

### Phase 5: Slim Top-Level CLAUDE.md + Session-Info Hook [~15 min]

1. Replace top-level CLAUDE.md with HPC-only content + Verification Protocol
2. Add subproject navigation table
3. Write session-info.sh hook
4. Update settings.local.json (remove harmonia Entire hooks, add session-info hook)

**Success criteria:**

- [ ] No mention of Beaker, Ollama, model registries, experiment types in top-level CLAUDE.md
- [ ] Verification Protocol IS present in top-level CLAUDE.md
- [ ] SLURM, HPC node, directory structure rules preserved
- [ ] Subproject navigation table present
- [ ] `session-info.sh` outputs cwd, git branch, Entire status
- [ ] Parent `settings.local.json` has NO hardcoded harmonia Entire hooks
- [ ] Parent `settings.local.json` HAS SessionStart info hook + Bash safety hook

### Phase 6: Entire CLI + Hook Activation Prompt [~15 min]

1. Run `entire enable` in geo-harmonizer
2. Configure `.entire/settings.json` with `telemetry: false`
3. Add Entire hooks to geo-harmonizer `.claude/settings.json`
4. Prompt user to activate enforcement hooks (rename `_hooks` → `hooks`)

**Success criteria:**

- [ ] `entire status` reports enabled in geo-harmonizer
- [ ] Telemetry is off
- [ ] User has been prompted about hook activation

## System-Wide Impact

### Interaction Graph

- **Claude Code session in geo_harmonizer/**: Reads global CLAUDE.md → project CLAUDE.md (HPC-only + Verification Protocol) → `AGENTS.md` via `.claude/CLAUDE.md` symlink (geo-harmonizer-specific). The `.claude/settings.json` in geo_harmonizer controls permissions, enforcement hooks, and Entire.dev hooks.
- **Claude Code session in harmonia/**: Reads global CLAUDE.md → project CLAUDE.md (HPC-only + Verification Protocol) → `AGENTS.md` via `.claude/CLAUDE.md` symlink (harmonia-specific). The existing `.claude/settings.json` (Entire.dev hooks) continues to work.
- **Claude Code session at project root**: Reads global CLAUDE.md → project CLAUDE.md (HPC-only + Verification Protocol). Session-info hook fires, showing cwd and Entire status.
- **Parent settings.local.json**: The Bash safety hook (`project-safe-commands.py`), session-info hook, and permissions whitelist apply to all subprojects. No more hardcoded harmonia Entire hooks.

### Error Propagation

- If `enforce-plan-before-code.py` crashes (missing Python, import error): the hook returns a non-zero exit code, which Claude Code treats as "allow" by default. **Risk: enforcement silently fails.** Mitigation: test the hook with mock input during setup.
- If symlinks break (e.g., directory renamed): `.claude/CLAUDE.md` becomes dangling. **Risk: no instructions loaded.** Mitigation: use relative symlinks, not absolute. `AGENTS.md` at repo root is always the real file.
- If `session-info.sh` fails (e.g., `entire` not in PATH): session still starts, just no diagnostic output. Non-blocking.

### State Lifecycle Risks

- **Partial completion**: If only Phases 1-3 complete but Phase 4-5 don't, the top-level CLAUDE.md still has harmonia content AND harmonia/AGENTS.md also has it → duplication, not breakage. Safe to pause between phases.
- **Git init without .gitignore**: If .gitignore is missing, `git add .` could stage .venv/ or results/. Mitigation: create .gitignore before any `git add`.

### API Surface Parity

- Both harmonia and geo-harmonizer follow the same pattern: `AGENTS.md` (actual file) at repo root, `.claude/CLAUDE.md` symlinks to it
- Both are navigable from the top-level CLAUDE.md's subproject table

## Acceptance Criteria

### Functional Requirements

- [ ] `geo_harmonizer/` exists at `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/geo_harmonizer/`
- [ ] All directories from architecture doc Section 2.2 are created
- [ ] Each directory has a `code_to_use_for_porting.txt` with priority level and references
- [ ] `docs/deep_research_outputs/` contains the copied research output folder
- [ ] `geo_harmonizer/` is a git repo with clean initial commit
- [ ] `geo_harmonizer/AGENTS.md` is the source of truth (actual file) with 5-phase development loop
- [ ] `geo_harmonizer/.claude/CLAUDE.md` is a working symlink to `../../AGENTS.md`
- [ ] Hooks exist in `.claude/hooks/` and are in settings.json under `_hooks` (commented out)
- [ ] `adversarial-reviewer.md` is in `.claude/agents/`
- [ ] `harmonia/AGENTS.md` is the source of truth (actual file) with harmonia-specific instructions
- [ ] `harmonia/.claude/CLAUDE.md` is a working symlink to `../../AGENTS.md`
- [ ] Top-level CLAUDE.md contains HPC shared rules + Verification Protocol + subproject navigation
- [ ] Top-level CLAUDE.md does NOT contain harmonia-specific content
- [ ] Session-info hook exists and fires on SessionStart at parent level
- [ ] Parent `settings.local.json` has no hardcoded harmonia Entire hooks
- [ ] Entire CLI is enabled in geo-harmonizer with telemetry off
- [ ] User has been prompted to activate enforcement hooks

### Non-Functional Requirements

- [ ] Existing harmonia codebase is completely unmodified (except adding AGENTS.md + symlink in .claude/)
- [ ] Existing harmonia `.claude/settings.json` is untouched
- [ ] No files written to home directory (~/)
- [ ] All symlinks use relative paths (not absolute)
- [ ] `.gitignore` prevents accidental staging of large/generated files and .entire/ data

## Dependencies & Prerequisites

- **None blocking**: This is a greenfield directory setup with no code dependencies.
- **Harmonia repo**: Must not be broken — read-only interaction (copying content out of its CLAUDE.md). Only addition: AGENTS.md + symlink.
- **Parent .claude/**: The `settings.local.json` will be MODIFIED (Entire hooks removed, session-info hook added). The `hooks/project-safe-commands.py` stays as-is.

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Top-level CLAUDE.md edit breaks harmonia workflows | Medium | High | Phase 4 (harmonia CLAUDE.md) runs BEFORE Phase 5 (slim top-level). Harmonia gets its own copy before anything is removed from the top level. |
| Symlinks break on git clone | Low | Medium | Use relative symlinks. Document in README that symlinks require Unix. |
| Hooks crash silently | Medium | Low | Test hooks with mock stdin during Phase 3. Include error handling in scripts. |
| `code_to_use_for_porting.txt` references become stale | High | Low | These are starting-point references, not maintained artifacts. They get deleted once the code is actually ported. |
| Parent settings.local.json Bash hook blocks geo-harmonizer commands | Low | Medium | The safety hook allows standard commands (git, python3, ls, etc.). Only blocks dangerous commands. No conflict expected. |

## Phase 6: Entire CLI Integration

Install and configure [Entire CLI](https://docs.entire.io) in geo-harmonizer. Entire captures full agent conversation transcripts tied to each code change, providing an audit trail of all AI-assisted development.

### Setup

```bash
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/geo_harmonizer/
entire enable
```

### Configuration

Edit `.entire/settings.json` to disable telemetry and remote tracing:

```json
{
  "strategy": "manual-commit",
  "enabled": true,
  "telemetry": false
}
```

Add to `.gitignore`:
```
.entire/tmp/
.entire/settings.local.json
.entire/metadata/
.entire/logs/
```

### Entire.dev Hooks in settings.json

After Entire is enabled, add its hooks to `geo_harmonizer/.claude/settings.json` alongside the enforcement hooks. These are the same hooks harmonia uses, but scoped to geo-harmonizer:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Task",
        "hooks": [{"type": "command", "command": "entire hooks claude-code pre-task"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Task",
        "hooks": [{"type": "command", "command": "entire hooks claude-code post-task"}]
      },
      {
        "matcher": "TodoWrite",
        "hooks": [{"type": "command", "command": "entire hooks claude-code post-todo"}]
      }
    ],
    "SessionStart": [
      {"matcher": "", "hooks": [{"type": "command", "command": "entire hooks claude-code session-start"}]}
    ],
    "SessionEnd": [
      {"matcher": "", "hooks": [{"type": "command", "command": "entire hooks claude-code session-end"}]}
    ],
    "UserPromptSubmit": [
      {"matcher": "", "hooks": [{"type": "command", "command": "entire hooks claude-code user-prompt-submit"}]}
    ],
    "Stop": [
      {"matcher": "", "hooks": [{"type": "command", "command": "entire hooks claude-code stop"}]}
    ]
  }
}
```

**Important:** These hooks do NOT `cd` into a hardcoded directory (unlike the parent `settings.local.json` which hardcodes the harmonia path). They run from the current working directory, which will be geo-harmonizer.

### Entire CLI Commands for Reviewing Agent Work

Add the following reference to the CLAUDE.md (and hence AGENTS.md via symlink) so agents know how to inspect the conversation history behind code changes:

```markdown
## Reviewing Agent Conversation History (Entire CLI)

Every Claude Code session is captured by Entire. Use these commands to review
what conversations led to each code change:

### List all checkpoints on the current branch
entire explain

### Explain a specific commit (what agent conversation produced it)
entire explain --commit <SHA>

### View full transcript of a checkpoint
entire explain --checkpoint <ID> --full

### Short summary of a checkpoint
entire explain --checkpoint <ID> --short

### Filter checkpoints by session
entire explain --session <session-id>

### Generate an AI summary of a checkpoint
entire explain --checkpoint <ID> --generate

### Check Entire status
entire status --detailed
```

### Parent settings.local.json Conflict Resolution

**Problem identified by SpecFlow analysis:** The parent `settings.local.json` contains hooks that hardcode `cd /hpc/.../harmonia && entire hooks ...`. When Claude Code runs from geo-harmonizer, these hooks fire and cd into harmonia — wrong context.

**Resolution:** The parent `settings.local.json` Entire.dev hooks should be removed or made conditional. Since harmonia already has its own `.claude/settings.json` with Entire.dev hooks, the parent-level hooks are redundant. The plan is:

1. Remove ALL Entire.dev hooks from `/hpc/compgen/projects/llm_GEO_project/.claude/settings.local.json` (the SessionStart, SessionEnd, Stop, UserPromptSubmit, PreToolUse Task, PostToolUse Task/TodoWrite hooks)
2. Keep ONLY the Bash safety hook (`project-safe-commands.py`) in the parent `settings.local.json`
3. Each subproject (harmonia, geo-harmonizer) manages its own Entire.dev hooks in its `.claude/settings.json`

This prevents cross-contamination between repos.

### Tasks

- [ ] Run `entire enable` in geo-harmonizer after git init
- [ ] Configure `.entire/settings.json` with `telemetry: false`
- [ ] Add `.entire/` patterns to `.gitignore`
- [ ] Add Entire.dev hooks to `geo_harmonizer/.claude/settings.json`
- [ ] Add "Reviewing Agent Conversation History" section to CLAUDE.md
- [ ] Remove Entire.dev hooks from parent `settings.local.json` (keep only Bash safety hook)
- [ ] Verify harmonia's `.claude/settings.json` already has its own Entire.dev hooks (it does)

---

## SpecFlow Analysis — Gap Resolutions

The SpecFlow analyzer identified 5 gaps. Here are the resolutions:

### Gap 1: Parent settings.local.json hooks hardcode harmonia paths → RESOLVED

See "Parent settings.local.json Conflict Resolution" in Phase 6 above. Remove Entire.dev hooks from the parent; each subproject manages its own.

The `project-safe-commands.py` Bash safety hook stays at the parent level but needs updating: add geo-harmonizer-specific approved scripts (e.g., future `run_benchmark.py`, `build_geo_db.py`) to the `APPROVED_SCRIPTS` list. This can be done incrementally as scripts are added.

### Gap 2: CLAUDE.md hierarchy — which sections go where → RESOLVED

The split is defined explicitly in Phases 4 and 5:
- **Top-level (HPC-only + shared):** Directory structure rules, SLURM commands, environment management, HPC nodes, **Verification Protocol for Capability Claims**, restrictions, backup strategy, subproject navigation table
- **harmonia/AGENTS.md:** Before Starting Any Task, After Code Changes, After Experiment Runs, Project Overview, Key Paths, Current State, Experiment Types, Running Experiments, Local LLM Jobs, Python Environment, Model Registry Management, Practical Lessons
- **geo-harmonizer/AGENTS.md:** Development loop enforcement, Python environment (.venv), project architecture references, data contracts, mermaid requirements, Entire CLI reference

### Gap 3: Hook activation mechanism → RESOLVED

Approach: The `settings.json` includes the full hooks config but under a `_hooks` key (disabled). After all phases complete, the user is prompted to activate by renaming `_hooks` to `hooks`. This keeps everything in one file and makes activation a single, visible edit.

### Gap 4: AGENTS.md and adversarial-reviewer.md placement → RESOLVED

Following the [agents.md specification](https://agents.md/#examples):
- `AGENTS.md` at repo root is the **actual file** (source of truth)
- `.claude/CLAUDE.md` is a **symlink** pointing to `../../AGENTS.md`
- `adversarial-reviewer.md` lives as a standalone file at `.claude/agents/adversarial-reviewer.md` (NOT embedded in AGENTS.md)
- This pattern applies to both harmonia and geo-harmonizer

### Gap 5: .venv creation → RESOLVED

Deferred intentionally. The `.venv/` directory is in `.gitignore`. A `pyproject.toml` with minimal metadata (project name, Python >=3.11) is created during Phase 1. Actual venv creation happens when the first Python code is written:

```bash
cd geo_harmonizer/
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
```

The CLAUDE.md will include this instruction so any AI session knows how to set up the environment.

---

## Future Considerations

- **Hook activation**: After Phase 1 completes, activate hooks by adding the hooks section to settings.json
- **Pre-commit hooks**: `.pre-commit-config.yaml` is created as a placeholder. Populated when code linting needs arise (ruff, mypy)
- **project-safe-commands.py updates**: As geo-harmonizer scripts are created, add them to the parent safety hook's APPROVED_SCRIPTS list

## Sources & References

### Origin

- **Architecture document:** [Gene_Expression_Omnibench_Six_Month_Plan_Architecture_Roadmap_v2.md](docs/research_output/deep_research_LLM_metadata_harmonisation_project_April_2026/Gene_Expression_Omnibench_Six_Month_Plan_Architecture_Roadmap_v2.md) — Section 2.2 (directory tree, lines 420-494), Section 2.3 (architectural changes, lines 497-537), Section 2.4 (data contracts, lines 539-617), Section 2.5 (what should not change, lines 619-633)
- **Claude Code enforcement template:** Extracted from `Claude_setup_new_directory.zip` in the same directory — CLAUDE.md, settings.json, enforce-plan-before-code.py, check-tests-on-stop.py, adversarial-reviewer.md, SETUP-GUIDE.md

### Internal References

- Current top-level CLAUDE.md: `/hpc/compgen/projects/llm_GEO_project/.claude/CLAUDE.md`
- Harmonia settings.json: `harmonia/.claude/settings.json` (Entire.dev hooks)
- Parent settings.local.json: `/hpc/compgen/projects/llm_GEO_project/.claude/settings.local.json`
- Existing brainstorms: `harmonia/docs/brainstorms/` (7 files, pattern to replicate)
- Existing plans: `harmonia/docs/plans/` (40+ files, pattern to replicate)

### External References

- Claude Code CLAUDE.md documentation: https://docs.anthropic.com/en/docs/claude-code
- Compound Engineering plugin: skills available via `/ce:brainstorm`, `/ce:plan`, `/ce:work`, `/ce:review`, `/ce:compound`
