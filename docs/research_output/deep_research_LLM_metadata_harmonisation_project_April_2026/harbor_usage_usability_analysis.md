# Harbor Framework: Usage, Usability, and Applicability Analysis for Gene Expression Omnibench

---

## Document Index

| Line | Section |
|------|---------|
| 16   | 1. What Harbor Is |
| 57   | 2. What AutoAgent Is |
| 96   | 3. Harbor Architecture Deep Dive |
| 98   | 3.1 Task Format |
| 134  | 3.2 Agent System |
| 174  | 3.3 Environment System and Apptainer Compatibility |
| 223  | 3.4 Jobs, Trials, and Sweeps |
| 259  | 3.5 ATIF Trajectory Format |
| 280  | 3.6 Evaluation and Verification |
| 310  | 4. Onboarding Guide |
| 312  | 4.1 Installation |
| 329  | 4.2 Writing a Gene Expression Omnibench Task in Harbor Format |
| 402  | 4.3 Running Agents Against Tasks |
| 437  | 4.4 Analyzing Results |
| 460  | 4.5 Using AutoAgent for Meta-Optimization |
| 503  | 5. Mapping to the Roadmap |
| 505  | 5.1 Where Harbor Fits Well |
| 546  | 5.2 Where Harbor Does Not Fit |
| 571  | 5.3 The Apptainer Backend Question |
| 614  | 5.4 AutoAgent as Experiment S6b |
| 649  | 6. Recommended Integration Strategy |
| 700  | 7. Risks and Mitigations |

---

## 1. What Harbor Is

Harbor is a framework from the creators of Terminal-Bench for evaluating and optimizing AI agents in containerized environments. It was released in January 2026 and is actively developed (MIT-adjacent license, 50+ benchmark adapters, 17+ built-in agents).

**Core capabilities:**

Harbor provides five things that are directly relevant to the Gene Expression Omnibench project: (1) a standardized task format that packages an instruction, a container environment, and a verifier into a portable unit, (2) built-in support for the exact coding agents we plan to evaluate — Claude Code, Codex CLI, OpenCode, Aider, and others — with full trajectory capture, (3) a sweeps system for running parameter variations across tasks, (4) an ATIF (Agent Trajectory Interchange Format) specification for structured analysis of agent runs, and (5) a results viewer for browsing jobs, comparing agent performance, and inspecting trajectories.

**What Harbor is NOT:**

Harbor is not a general-purpose experiment framework for arbitrary Python pipelines. It evaluates *agents* — programs that receive a natural-language instruction, work inside a sandbox, and produce artifacts that a verifier checks. It does not natively support running a custom Python pipeline (like our ReAct+BDI-Kit agent or Matchmaker reimplementation) unless that pipeline is wrapped as a Harbor agent. Harbor also does not provide observability (no OTel/Phoenix integration), prompt versioning (no Langfuse), or statistical comparison utilities (no McNemar/Friedman). These remain the responsibility of our existing infrastructure.

**Scale of the ecosystem:**

Harbor has adapters for 50+ benchmarks including SWE-Bench (and 6 variants), Terminal-Bench, DABStep (structured data tasks), GAIA, BFCL (function calling), LiveCodeBench, SpreadsheetBench, and domain-specific benchmarks for finance (FinanceAgent), medicine (MedAgentBench), and law (LawBench). The DABStep and SpreadsheetBench adapters are particularly relevant as they evaluate agents on structured data tasks — the closest existing Harbor benchmarks to metadata harmonization.

**Project links:**
- Repository: https://github.com/laude-institute/harbor (previously harbor-framework/harbor)
- Documentation: https://harborframework.com/docs
- Cookbook: https://github.com/harbor-framework/harbor-cookbook

---

## 2. What AutoAgent Is

AutoAgent (https://github.com/kevinrgu/autoagent) is a meta-agent optimization layer built on top of Harbor. It implements a simple but powerful idea: instead of hand-engineering an agent harness, let a coding agent (the "meta-agent") iteratively improve the harness by running benchmarks, diagnosing failures, editing the harness code, and hill-climbing on the score.

**How it works:**

The repo has two key files: `agent.py` (the harness under test — a single-file agent with an editable section and a fixed Harbor adapter boundary) and `program.md` (instructions for the meta-agent defining what kind of agent to build and how to run the optimization loop). The human programs `program.md`; the meta-agent programs `agent.py`.

The experiment loop is:
1. Run the benchmark suite via Harbor (`harbor run -p tasks/ --agent-import-path agent:AutoAgent`)
2. Read task-level results and verifier logs
3. Diagnose failures and group by root cause
4. Choose one general harness improvement (system prompt, tools, orchestration)
5. Edit `agent.py`, commit, rebuild, rerun
6. If score improved → keep; if not → discard
7. Repeat until the human stops the loop

**Key design principles:**
- The meta-agent must improve a *class* of failures, not hack a single task (overfitting rule)
- Simplicity criterion: equal performance with simpler code is a real improvement
- The meta-agent modifies everything above the "FIXED ADAPTER BOUNDARY" — system prompt, tools, agent construction, orchestration — but not the Harbor integration code
- Every experiment is logged to `results.tsv` with commit hash, score, cost, and status (keep/discard/crash)

**The `agent.py` harness** starts minimal: a system prompt ("You are an agent that executes tasks"), a single `run_shell` tool, and default configuration. The meta-agent adds specialized tools, modifies prompts, adds sub-agents via `agent.as_tool()`, and changes orchestration — all driven by benchmark feedback.

**Relevance to Gene Expression Omnibench:** AutoAgent provides a concrete methodology for experiment S6b — automated optimization of the coding agent harness for metadata harmonization tasks. Instead of hand-crafting CLAUDE.md, let a meta-agent discover the optimal system prompt, tool set, and orchestration for GEO→GDC harmonization.

---

## 3. Harbor Architecture Deep Dive

### 3.1 Task Format

A Harbor task is a directory with a fixed structure:

```
my-task/
├── task.toml           # Configuration (timeouts, resources, metadata)
├── instruction.md      # Natural-language task description sent to the agent
├── environment/
│   └── Dockerfile      # Container environment definition
├── tests/
│   ├── test.sh         # Entry point — runs verifier, writes reward
│   └── test.py         # Verification logic (deterministic or LLM-as-judge)
├── solution/           # (optional) Reference solution
│   └── solve.sh
└── files/              # (optional) Reference files mounted into container
```

**task.toml** specifies:
```toml
version = "1.0"

[task]
name = "geo-omnibench/single-table-gse12345"

[metadata]
difficulty = "hard"
category = "data-harmonization"
tags = ["omics", "schema-matching", "gdc"]

[agent]
timeout_sec = 300.0      # Max agent execution time

[verifier]
timeout_sec = 120.0      # Max verification time

[verifier.env]           # Environment vars for verifier (e.g., API keys for LLM-as-judge)

[environment]
build_timeout_sec = 600.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
gpus = 0
allow_internet = true    # Agent can call APIs
```

**instruction.md** contains the natural-language task description. For harmonization tasks, this would describe the source table, the target schema, and what output to produce.

**tests/test.sh** is the verifier entry point. It runs after the agent finishes, checks the agent's output, and writes a reward score (0.0-1.0) to `/logs/verifier/reward.txt` or a JSON object with named metrics to `/logs/verifier/reward.json`. The verifier can use deterministic checks (exact match, F1 computation) or LLM-as-judge evaluation.

### 3.2 Agent System

Harbor's agent system has a clean abstraction:

```python
class BaseAgent(ABC):
    SUPPORTS_ATIF: bool = False  # Set True for trajectory capture

    @staticmethod
    @abstractmethod
    def name() -> str: ...

    @abstractmethod
    def version(self) -> str | None: ...

    @abstractmethod
    async def setup(self, environment: BaseEnvironment) -> None: ...

    @abstractmethod
    async def run(self, instruction: str, environment: BaseEnvironment,
                  context: AgentContext) -> None: ...
```

**Built-in agents** (17+): `claude-code`, `codex`, `opencode`, `aider`, `openhands`, `openhands-sdk`, `goose`, `gemini-cli`, `hermes`, `qwen-coder`, `cursor-cli`, `cline-cli`, `mini-swe-agent`, `swe-agent`, `kimi-cli`, `rovodev-cli`, `trae-agent`.

**The Claude Code agent implementation** (`src/harbor/agents/installed/claude_code.py`, 1092 lines) is particularly mature. It handles: installation inside the container, model name resolution (including Bedrock mode), CLI flag management (max_turns, reasoning_effort, max_budget_usd, fallback_model, allowed/disallowed tools), session directory management, skills and memory registration, MCP server configuration, and full ATIF trajectory extraction from Claude Code's JSONL session logs. This is significantly more sophisticated than the thin wrapper we planned for `coding_agent.py`.

**The Codex agent** (`src/harbor/agents/installed/codex.py`, 677 lines) similarly handles Codex CLI installation, execution in full-auto mode, and trajectory extraction.

**Custom agents** can be registered via `--agent-import-path agent:MyAgent`, which is how AutoAgent integrates — it defines an `AutoAgent` class that implements `BaseAgent` and delegates to the OpenAI Agents SDK.

**Key implication for our project:** Instead of building `coding_agent.py` from scratch, we could use Harbor's built-in Claude Code and Codex agents directly, inheriting their mature trajectory capture, error handling, and configuration management. Our `coding_agent.py` becomes a thin adapter that calls `harbor run` or, alternatively, we implement our own bespoke pipeline agents as Harbor `BaseAgent` subclasses.

### 3.3 Environment System and Apptainer Compatibility

Harbor's environment system abstracts container runtimes behind `BaseEnvironment`:

```python
class BaseEnvironment(ABC):
    async def start(self, force_build: bool) -> None: ...
    async def stop(self, delete: bool) -> None: ...
    async def exec(self, command: str, cwd=None, env=None,
                   timeout_sec=None, user=None) -> ExecResult: ...
    async def upload_file(self, source_path, target_path) -> None: ...
    async def upload_dir(self, source_dir, target_dir) -> None: ...
    async def download_dir(self, remote_path, local_path) -> None: ...
```

**Built-in environments:** Docker (default), Daytona, Modal, E2B, Runloop, GKE, Apple Container.

**The Docker environment** (`src/harbor/environments/docker/docker.py`, 521 lines) uses `docker compose` CLI commands — NOT the Docker Python SDK. It calls `docker compose build`, `docker compose up --detach`, `docker compose exec`, `docker compose cp`, and `docker compose down` via `asyncio.create_subprocess_exec`. This CLI-level coupling makes it relatively straightforward to create an alternative backend.

**Apptainer compatibility assessment:**

The image format conversion is trivial — `apptainer build image.sif docker://...` converts any Dockerfile into an Apptainer `.sif` image. The project already does this for vLLM and Qdrant containers.

The runtime integration requires implementing `BaseEnvironment` for Apptainer. The mapping is:

| Harbor Docker operation | Apptainer equivalent |
|------------------------|---------------------|
| `docker compose build` | `apptainer build task.sif docker-daemon://task:latest` or from Dockerfile via `apptainer build --fakeroot` |
| `docker compose up --detach` | `apptainer instance start [--nv] [--bind ...] task.sif task_instance` |
| `docker compose exec main bash -c "cmd"` | `apptainer exec instance://task_instance bash -c "cmd"` |
| `docker compose cp src main:dst` | Bind mount at start, or `apptainer exec instance://task_instance cp /host/src /dst` |
| `docker compose down` | `apptainer instance stop task_instance` |
| Environment variables | `apptainer exec --env KEY=VAL` or `--env-file` |
| User switching | `apptainer exec --fakeroot` or run as current user (Apptainer runs unprivileged by default) |
| GPU passthrough | `--nv` flag |
| Network isolation | `--net --network none` (requires root or `--fakeroot`) |

**Effort estimate for an Apptainer backend:** 2-3 days for a basic implementation, 1 week for production-quality with proper error handling, GPU support, and bind mount management. The existing Apptainer patterns in the project (vLLM deployment, Qdrant deployment, agent sandboxing) provide templates.

**Key caveats:**
- Apptainer instances don't have the same lifecycle semantics as Docker Compose services. Docker Compose manages multi-container stacks; Apptainer instances are single-container.
- Network isolation requires `--fakeroot` or root, which may not be available on all HPC nodes. For benchmark tasks that need `allow_internet = true` (API-calling agents), this is fine — the agent calls APIs from the container. For tasks that should be isolated, the existing Apptainer sandboxing approach (no outbound from compute nodes) provides natural isolation.
- `docker compose cp` has no direct Apptainer equivalent. The solution is pre-staging files via bind mounts, which the project already does.

**Recommendation:** Implement an `ApptainerEnvironment` class as a **P1 infrastructure prerequisite** — the HPC has no Docker-capable nodes, so this is required before any Harbor-based experiments can run. Estimated effort: 2-3 days for basic implementation, 1 week for production quality. The existing Apptainer patterns in the project (vLLM deployment, Qdrant deployment, agent sandboxing) provide templates. This unlocks Harbor for all experiments, not just coding agent baselines.

### 3.4 Jobs, Trials, and Sweeps

**A trial** is a single execution of an agent on a task — essentially one rollout that produces a reward. Trials are the atomic unit of evaluation.

**A job** is a collection of trials, potentially spanning multiple agents, tasks, models, and attempt counts. Jobs can be configured via YAML:

```yaml
# job.yaml
dataset: "geo-omnibench/v1"
agents:
  - name: claude-code
    model: anthropic/claude-sonnet-4-6
  - name: codex
    model: openai/o3
  - name: opencode
    model: anthropic/claude-sonnet-4-6
n_attempts: 3
n_concurrent: 4
```

**Sweeps** provide a higher-level abstraction: successive rounds of evaluation where tasks that are solved in one sweep are dropped from subsequent sweeps. This is designed for training workflows where you want to focus compute on unsolved tasks. Harbor's sweep system also supports exporting traces as HuggingFace DatasetDict with success/failure splits — useful for RL fine-tuning.

The sweeps concept maps to a subset of our successive halving methodology (Report D, lines 159-167), but is oriented toward agent improvement rather than configuration comparison. Our `sweep.py` handles the full model × architecture × prompt × quantization sweep space, while Harbor's sweeps handle the agent × task × attempt space.

**Results structure:**
```
jobs/job-name/
├── config.json           # Job configuration
├── result.json           # Aggregated results
├── trial-name/
│   ├── config.json       # Trial configuration
│   ├── result.json       # Trial result (reward, duration, tokens)
│   ├── agent/
│   │   ├── trajectory.json   # ATIF trajectory
│   │   └── recording.cast    # Terminal recording (if available)
│   └── verifier/
│       ├── reward.txt        # Score (0.0-1.0)
│       ├── ctrf.json         # Test framework results
│       ├── test-stdout.txt
│       └── test-stderr.txt
```

### 3.5 ATIF Trajectory Format

ATIF (Agent Trajectory Interchange Format) is Harbor's standardized format for capturing agent execution traces:

```json
{
  "schema_version": "ATIF-v1.6",
  "session_id": "...",
  "agent": {"name": "claude-code", "version": "1.0.18", "model_name": "claude-sonnet-4-6"},
  "steps": [
    {
      "step_id": 1,
      "timestamp": "2026-04-05T12:00:00Z",
      "source": "user",
      "message": "Harmonize this GEO metadata table to GDC schema..."
    },
    {
      "step_id": 2,
      "timestamp": "2026-04-05T12:00:05Z",
      "source": "agent",
      "message": "I'll analyze the source table and GDC schema...",
      "reasoning_content": "...",
      "model_name": "claude-sonnet-4-6"
    },
    {
      "step_id": 3,
      "source": "agent",
      "message": "Tool: run_shell",
      "tool_calls": [{"function_name": "bash", "arguments": {"command": "python3 harmonize.py"}}],
      "observation": {"results": [{"content": "Mapping complete: 15/17 columns matched"}]}
    }
  ],
  "final_metrics": {
    "total_prompt_tokens": 45000,
    "total_completion_tokens": 12000,
    "total_cost_usd": 0.23,
    "total_steps": 15,
    "extra": {"duration_ms": 45000}
  }
}
```

ATIF trajectories capture the full agent reasoning chain, tool calls with arguments and observations, token usage, and cost. This is complementary to our Phoenix/OTel tracing — ATIF captures the agent-level trace, while Phoenix captures the LLM-call-level trace. For the coding agent experiments (S6), ATIF provides richer agent-level analysis than our current trajectory capture.

### 3.6 Evaluation and Verification

Harbor's verification system is flexible:

**Deterministic verification** (for schema matching): Write a Python test that loads the agent's output mapping, compares against the gold standard, computes F1/precision/recall, and writes the score to `reward.json`:

```python
# tests/test_mapping.py
import json
from pathlib import Path

gold = json.loads(Path("/tests/gold_mapping.json").read_text())
pred = json.loads(Path("/workspace/mapping.json").read_text())

correct = sum(1 for k, v in gold.items() if pred.get(k) == v)
precision = correct / len(pred) if pred else 0
recall = correct / len(gold) if gold else 0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

Path("/logs/verifier/reward.json").write_text(json.dumps({
    "f1": f1, "precision": precision, "recall": recall, "correct": correct, "total": len(gold)
}))
```

**LLM-as-judge** (for value mapping quality): Harbor supports passing API keys to the verifier via `[verifier.env]` in `task.toml`. A judge script sends the agent's output to an LLM for semantic evaluation. This is directly applicable to value mapping tasks where "correct" is fuzzy (e.g., "NSCLC tumor" vs. "Lung").

**Multi-metric evaluation**: `reward.json` supports arbitrary named metrics, so a single task can report F1, precision, recall, and value mapping accuracy simultaneously.

---

## 4. Onboarding Guide

### 4.1 Installation

```bash
# Install Harbor CLI
uv tool install harbor
# or
pip install harbor

# Verify installation
harbor --help

# List available agents
harbor run --help

# List registered datasets
harbor datasets list
```

**For AutoAgent:**
```bash
git clone https://github.com/kevinrgu/autoagent.git
cd autoagent
uv sync

# Set API keys
cat > .env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
EOF

# Build base image (Docker required for initial setup)
docker build -f Dockerfile.base -t autoagent-base .
```

**For HPC with Apptainer (until a dedicated backend exists):**
```bash
# Convert Harbor task Dockerfiles to Apptainer images
apptainer build task_env.sif docker-daemon://autoagent-base:latest

# Or build directly from Dockerfile (requires --fakeroot)
apptainer build --fakeroot task_env.sif docker://autoagent-base:latest
```

### 4.2 Writing a Gene Expression Omnibench Task in Harbor Format

Here is a complete example of a single-table schema matching task packaged as a Harbor task:

**Directory structure:**
```
tasks/geo-omnibench-L1-GSE12345/
├── task.toml
├── instruction.md
├── environment/
│   └── Dockerfile
├── tests/
│   ├── test.sh
│   └── evaluate_mapping.py
└── files/
    ├── source_table.csv
    ├── gdc_schema.json
    └── gold_mapping.json
```

**task.toml:**
```toml
version = "1.0"

[task]
name = "geo-omnibench/L1-GSE12345"
authors = ["Gene Expression Omnibench Team"]
keywords = ["omics", "schema-matching", "gdc", "geo"]

[metadata]
difficulty = "hard"
category = "data-harmonization"
tags = ["schema-matching", "geo-metadata", "gdc", "cancer-genomics"]

[agent]
timeout_sec = 600.0        # 10 minutes for agent execution

[verifier]
timeout_sec = 60.0

[environment]
build_timeout_sec = 600.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
gpus = 0
allow_internet = true      # Agent can call LLM APIs
```

**instruction.md:**
```markdown
# Task: Harmonize GEO Metadata to GDC Schema

You are given a metadata table from GEO series GSE12345 (breast cancer RNA-seq)
and the GDC (Genomic Data Commons) target schema.

## Input files
- `/workspace/source_table.csv` — Source metadata table (17 columns, 190 rows)
- `/workspace/gdc_schema.json` — Target GDC schema with property names, descriptions,
  and permissible values

## Your task
1. Examine the source table columns and the GDC schema properties
2. For each source column, determine which GDC property it maps to (or "unmapped"
   if no mapping exists)
3. Write your mapping to `/workspace/mapping.json` as a JSON object:
   `{"source_column_name": "gdc_property_name", ...}`

## Guidelines
- Use the GDC property names exactly as they appear in the schema
- If a source column has no corresponding GDC property, map it to "unmapped"
- Consider both lexical similarity and semantic meaning
- BDI-Kit is installed (`pip install bdi-kit`) if you want to use it
```

**environment/Dockerfile:**
```dockerfile
FROM python:3.11-slim

RUN pip install pandas bdi-kit openpyxl

WORKDIR /workspace
COPY files/ /workspace/
COPY tests/ /tests/
```

**tests/test.sh:**
```bash
#!/bin/bash
cd /tests
python3 evaluate_mapping.py
```

**tests/evaluate_mapping.py:**
```python
import json
from pathlib import Path

# Load gold standard and prediction
gold = json.loads(Path("/workspace/gold_mapping.json").read_text())
pred_path = Path("/workspace/mapping.json")

if not pred_path.exists():
    Path("/logs/verifier/reward.json").write_text(
        json.dumps({"f1": 0.0, "precision": 0.0, "recall": 0.0, "error": "No mapping.json produced"})
    )
    exit(0)

pred = json.loads(pred_path.read_text())

# Exclude "unmapped" from evaluation
gold_mapped = {k: v for k, v in gold.items() if v != "unmapped"}
pred_mapped = {k: v for k, v in pred.items() if v != "unmapped"}

tp = sum(1 for k, v in gold_mapped.items() if pred_mapped.get(k) == v)
fp = sum(1 for k, v in pred_mapped.items() if gold_mapped.get(k, None) != v)
fn = sum(1 for k in gold_mapped if k not in pred_mapped or pred_mapped[k] != gold_mapped[k])

precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

Path("/logs/verifier/reward.json").write_text(json.dumps({
    "f1": round(f1, 4),
    "precision": round(precision, 4),
    "recall": round(recall, 4),
    "correct": tp,
    "total_gold": len(gold_mapped),
    "total_pred": len(pred_mapped),
}, indent=2))
```

### 4.3 Running Agents Against Tasks

**Run Claude Code on a single task:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...

harbor run -p tasks/geo-omnibench-L1-GSE12345 \
  -a claude-code \
  -m anthropic/claude-sonnet-4-6 \
  -o jobs \
  --job-name gse12345-claude-sonnet
```

**Run Codex on all tasks:**
```bash
export OPENAI_API_KEY=sk-...

harbor run -p tasks/ \
  -a codex \
  -m openai/o3 \
  -n 4 \
  -o jobs \
  --job-name omnibench-codex-o3
```

**Run OpenCode with a different model:**
```bash
harbor run -p tasks/ \
  -a opencode \
  -m anthropic/claude-sonnet-4-6 \
  -o jobs \
  --job-name omnibench-opencode
```

**Compare multiple agents via job config:**
```yaml
# job.yaml
tasks_path: tasks/
agents:
  - name: claude-code
    model: anthropic/claude-sonnet-4-6
    kwargs:
      max_turns: 30
      max_budget_usd: "5.00"
  - name: codex
    model: openai/o3
  - name: opencode
    model: anthropic/claude-sonnet-4-6
n_attempts: 3
n_concurrent: 4
output_dir: jobs
job_name: omnibench-agent-comparison
```

```bash
harbor run -c job.yaml
```

### 4.4 Analyzing Results

**Browse results in the viewer:**
```bash
harbor view jobs
# Opens http://127.0.0.1:8080 with interactive results browser
```

**Inspect specific trial results:**
```bash
# View trial result
cat jobs/omnibench-codex-o3/geo-omnibench-L1-GSE12345/result.json

# View agent trajectory
cat jobs/omnibench-codex-o3/geo-omnibench-L1-GSE12345/agent/trajectory.json

# View verifier output
cat jobs/omnibench-codex-o3/geo-omnibench-L1-GSE12345/verifier/reward.json
```

**Aggregate results across jobs:** Harbor's result.json at the job level aggregates trial-level scores. For statistical comparison across agents, extract the per-task scores and feed them into our `comparison.py` utilities (McNemar, Friedman, Cliff's δ).

### 4.5 Using AutoAgent for Meta-Optimization (Experiment S6b)

**Setup:**
1. Fork or clone AutoAgent
2. Create Gene Expression Omnibench tasks in Harbor format under `tasks/`
3. Write a harmonization-specific `program.md`:

```markdown
# autoagent — GEO Metadata Harmonization

You are a meta-agent improving an agent harness for GEO-to-GDC metadata
harmonization.

## Directive

Build an agent that takes GEO metadata tables and maps them to GDC schema
properties. The agent works inside a sandbox with pandas, bdi-kit, and standard
Python libraries.

The metric is F1 score on column mapping accuracy.

## Domain context

- Source: GEO metadata tables with free-text column names and values
- Target: GDC (Genomic Data Commons) schema with 736 properties
- Key challenges: ambiguous abbreviations, implicit context, ontology mapping
- BDI-Kit is available: `from bdi_kit import match_schema, rank_schema_matches`

## What to optimize

- System prompt: domain-specific instructions for GEO→GDC mapping
- Tools: consider adding tools for GDC schema lookup, ontology search,
  value validation against GDC permissible values
- Verification: add a self-check step before finishing
- Strategy: consider dual-pass (schema matching then value mapping)

Do NOT change the model from the configured default.
```

4. Run the meta-optimization loop:
```bash
# Set up
source .env
docker build -f Dockerfile.base -t autoagent-base .

# Run baseline
rm -rf jobs; mkdir -p jobs && \
  uv run harbor run -p tasks/ --agent-import-path agent:AutoAgent \
  -o jobs --job-name baseline > run.log 2>&1

# Start meta-agent (in Claude Code or Codex):
# "Read program.md and let's kick off a new experiment!"
```

5. The meta-agent will iterate: run benchmark → diagnose failures → edit agent.py → rerun → keep/discard. Each iteration is logged to `results.tsv`.

**Expected outcome:** After 10-20 iterations, the meta-agent will have discovered domain-specific tools and prompts that improve F1 over the baseline. The final `agent.py` represents an automatically engineered harness — compare its performance against the hand-crafted CLAUDE.md approach (S6 baseline) and the bespoke pipeline (S3/S7).

---

## 5. Mapping to the Roadmap

### 5.1 Where Harbor Fits Well

**Experiment S6 (frontier coding agent baseline) — HIGH FIT:**
Harbor was built for exactly this. Its Claude Code agent implementation (1092 lines) handles installation, model configuration, CLI flags, session management, skills/memory/MCP registration, Bedrock mode, and full ATIF trajectory extraction. This is far more mature than the `coding_agent.py` we planned. Using Harbor for S6 eliminates 2-3 days of wrapper development and gives us richer trajectory data.

Specifically, Harbor's Claude Code agent supports:
- `--max-turns`, `--max-budget-usd`, `--effort` flags via task config
- Skills directory mounting (for CLAUDE.md-like context)
- MCP server registration (for potential tool integration)
- Memory pre-seeding (for few-shot examples)
- Full JSONL → ATIF trajectory conversion with token counts and cost

**Experiment S6b (AutoAgent meta-optimization) — NOVEL ADDITION:**
AutoAgent provides a ready-made methodology for testing automated agent engineering on our benchmark. This is a genuinely novel experiment — no existing work has applied meta-agent optimization to structured biomedical data processing. The result (S6 hand-crafted vs. S6b auto-optimized) directly tests whether human context engineering or automated agent engineering produces better harmonization.

**Benchmark distribution — GOOD FIT:**
Harbor's task format is standardized and portable. Publishing Gene Expression Omnibench tasks in Harbor format makes them immediately runnable by anyone with Harbor installed, against any of the 17+ supported agents. This aligns with the goal of creating a reusable community benchmark. Tasks could be published to Harbor's registry alongside the HuggingFace release.

**Agent comparison at scale — GOOD FIT:**
Harbor's job system can run multiple agents (Claude Code, Codex, OpenCode, Aider) against all benchmark tasks with consistent evaluation, parallel execution, and structured results. This is exactly what S6 needs and would be tedious to build from scratch.

### 5.2 Where Harbor Does Not Fit

**Bespoke pipeline experiments (S3, S7) — POOR FIT:**
The ReAct+BDI-Kit agent, CodeAct agent, and Matchmaker reimplementation are custom Python code, not installed CLI tools. Wrapping them as Harbor agents is possible (implement `BaseAgent`, call the pipeline in `run()`) but adds abstraction overhead without clear benefit. These experiments are better served by the existing YAML-configured experiment runner.

**Local model inference (S4, S5) — DOES NOT APPLY:**
Harbor evaluates agents that call APIs or run CLI tools. It doesn't manage local model inference servers. vLLM on SLURM via Apptainer is a separate infrastructure concern.

**Statistical analysis and observability — DOES NOT APPLY:**
Harbor doesn't provide McNemar tests, Friedman comparisons, bootstrap CIs, Phoenix/OTel tracing, Langfuse prompt versioning, or the four-layer reproducibility strategy. These remain our infrastructure's responsibility.

**Ablation experiments (S8, S9) — POOR FIT:**
Context content ablation, temperature sweeps, and embedding model comparison are parameter variations within a single pipeline, not different agents on the same task. Harbor's model is "agent × task → score," not "parameter × configuration → metric."

### 5.3 The Apptainer Backend Question

**Image conversion is trivial:** `apptainer build task.sif docker://task-image:latest` works for any Harbor task Dockerfile. The project already does this for vLLM and Qdrant.

**Runtime integration requires a new `ApptainerEnvironment` class.** The mapping from Harbor's `BaseEnvironment` to Apptainer commands is clean (see Section 3.3 table). Estimated effort: 2-3 days for basic implementation, 1 week for production quality.

**Should we build it?** Yes, but as P2 infrastructure (Month 2-3), not P1. The immediate value is:
1. Run all coding agent experiments (S6, S6b) on SLURM compute nodes
2. Enable Harbor-formatted benchmark tasks to run on the same HPC infrastructure as all other experiments
3. Future-proof: if we publish Gene Expression Omnibench as a Harbor dataset, the Apptainer backend lets us validate it runs on HPC

**The Apptainer backend is a hard prerequisite**, not an optimization. Since the HPC has no Docker-capable nodes, all Harbor experiments (S6, S6b) require the `ApptainerEnvironment` implementation before they can run. Build this in Week 1 of Month 1 alongside benchmark construction.

**Implementation sketch for `ApptainerEnvironment`:**
```python
class ApptainerEnvironment(BaseEnvironment):
    """HPC-native environment using Apptainer instances."""

    async def start(self, force_build: bool):
        # Build .sif from Dockerfile
        if force_build or not self._sif_path.exists():
            await self._run_command([
                "apptainer", "build", "--fakeroot",
                str(self._sif_path),
                f"docker-daemon://{self._image_name}:latest"
            ])
        # Start instance with bind mounts
        await self._run_command([
            "apptainer", "instance", "start",
            "--nv" if self._gpus else "",
            "--bind", f"{self._logs_dir}:/logs",
            "--bind", f"{self._workspace_dir}:/workspace",
            str(self._sif_path),
            self._instance_name,
        ])

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        cmd = ["apptainer", "exec"]
        if env:
            for k, v in env.items():
                cmd.extend(["--env", f"{k}={v}"])
        cmd.extend([f"instance://{self._instance_name}", "bash", "-c", command])
        return await self._run_command(cmd, timeout_sec=timeout_sec)

    async def stop(self, delete: bool):
        await self._run_command(["apptainer", "instance", "stop", self._instance_name])
        if delete:
            self._sif_path.unlink(missing_ok=True)
```

### 5.4 AutoAgent as Experiment S6b

**Experiment definition:**

| Field | Value |
|-------|-------|
| ID | S6b |
| Name | AutoAgent meta-optimization for harmonization |
| Simplicity | 2 (requires AutoAgent setup + multi-iteration loop) |
| Yield | 4 (directly comparable to S6; tests automated agent engineering) |
| Risk | 3 (meta-agent may not converge; dependent on benchmark quality) |
| Novelty | 5 (no published work applies meta-agent optimization to structured biomedical data) |
| Score | (4 × 3 × 5) / (6 - 2) = 15.0 |
| Priority | **P2** |
| Dependencies | B1 (benchmark), S6 (baseline to compare against) |
| Timeline | Month 3 (after S6 baseline is established in Month 1) |
| Effort | ~1 week setup + 2-3 days of unattended meta-agent iteration |
| Cost | ~$20-50 per meta-optimization run (meta-agent API calls + benchmark runs) |

**What it tests:** Whether automated agent engineering (meta-agent iteratively improving system prompt, tools, and orchestration) outperforms manual context engineering (hand-crafted CLAUDE.md) on GEO→GDC harmonization. This is a direct test of the "context engineering matters more than tool architecture" thesis from the roadmap — if AutoAgent discovers a better context than the human-crafted one, it validates the thesis from a different angle.

**Success criteria:** If S6b score > S6 score on the same benchmark, the meta-agent discovered a better harness than the human. Log the final `agent.py` and `results.tsv` as artifacts.

**Failure analysis:** If S6b ≤ S6 after 20+ iterations, this is still a publishable negative result — automated agent engineering does not improve over manual context engineering for domain-specific tasks. The `results.tsv` trace shows what the meta-agent tried and why it didn't help.

---

## 6. Recommended Integration Strategy

**Phase 1 (Month 1, Week 1): Build ApptainerEnvironment backend + write Harbor tasks.**
- Implement `ApptainerEnvironment` class (2-3 days; see Section 5.3 for implementation sketch)
- Install Harbor CLI on the HPC
- Write Gene Expression Omnibench tasks in Harbor format (5-10 tasks from B1)
- Validate the backend on example tasks before running S6

**Phase 1b (Month 1, Weeks 3-4): Run S6 via Harbor on SLURM.**
- Run S6 baseline: `harbor run -p tasks/ -a claude-code -m anthropic/claude-sonnet-4-6 --env apptainer`
- Run S6 variants: codex, opencode
- Extract ATIF trajectories for failure analysis (feeds E2)

**Phase 2 (Month 2-3): Add AutoAgent meta-optimization (S6b).**
- Fork AutoAgent, populate `tasks/` with Harbor-formatted benchmark tasks
- Write harmonization-specific `program.md`
- Run baseline, then start meta-agent loop (runs on SLURM via ApptainerEnvironment)
- Compare S6b final score against S6 baseline

**Phase 3 (Month 4+, if Harbor proves valuable): Consider wrapping bespoke agents.**
- If the ApptainerEnvironment works well, consider wrapping the ReAct+BDI-Kit and Matchmaker pipelines as Harbor agents for unified evaluation
- This is a convenience, not a necessity — only worthwhile if Harbor's results viewer and comparison tools add enough value

**What to NOT do:**
- Do NOT replace the existing experiment infrastructure (sweep.py, comparison.py, YAML configs) with Harbor. Harbor evaluates agents; our infrastructure manages the broader experiment space.
- Do NOT block P1 experiments on Harbor integration. Harbor is additive to S6, not a prerequisite.
- Do NOT invest in the Apptainer backend before validating Harbor's value on Docker. If S6 results are uninteresting, the Apptainer backend is wasted effort.

---

## 7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Harbor Docker requirement blocks HPC usage | **Eliminated** — ApptainerEnvironment backend built as P1 prerequisite | N/A | Build and validate in Week 1 of Month 1 before any Harbor experiments |
| AutoAgent meta-optimization doesn't converge | Medium | Low (negative result is still publishable) | Limit to 20 iterations; analyze `results.tsv` for learning signal regardless |
| Harbor version incompatibility with AutoAgent | Low | Low | Pin versions; both are actively maintained |
| Harbor task format overhead vs. custom evaluation | Low | Low | Task format is simple (5 files); reusable for community benchmark distribution |
| Apptainer backend implementation takes >1 week | Medium | **High** (blocks all Harbor experiments) | Start in Week 1; keep scope minimal (start/exec/stop/upload); extend later |
| Harbor's trajectory format conflicts with Phoenix/OTel | Low | Low | They're complementary: ATIF for agent-level, Phoenix for LLM-call-level |
