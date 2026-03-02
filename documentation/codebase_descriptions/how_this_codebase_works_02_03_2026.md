# Harmonia Metadata Agent Codebase Documentation

**Date:** 02-03-2026 (updated from 26-02-2026 baseline)
**Author:** Generated documentation for the Harmonia data harmonization experiment automation framework

---


## Update Summary (02-03-2026)

This update captures major reliability, observability, and analysis changes implemented today:

- **Run-isolated storage and runtime paths:**
  - SBATCH launch path now explicitly passes per-run `--results-dir` into `exec_apptainer_harmonia.sh`.
  - Runtime artifacts are redirected into run-local paths under `/workspace/results`:
    - `JUPYTER_RUNTIME_DIR`
    - `XDG_RUNTIME_DIR`
    - `BEAKER_RUN_PATH`
    - `IPYTHONDIR`
  - This fixes home-directory spillover (`~/.local/share/beaker`, `~/.ipython`) and reduces ENOSPC-related startup failures.

- **Prompt/path and automation correctness fixes:**
  - Automated config prompt text for input files was aligned with actual in-container paths (`/workspace/data/...`).
  - Turn logging in `src/automation/runner.py` was fixed to avoid duplicate/conflicting turn IDs when auto-decision messages are injected.
  - `run_experiment.py` output detection now handles nested output layout (`results/dou_harmonized.csv`) when metrics are computed.

- **Gemini/OpenRouter and bdi-kit compatibility hardening:**
  - `src/bdikit_context/agent.py` now normalizes model names to provider-qualified LiteLLM form (e.g., `openrouter/<model>`) where needed, reducing provider-resolution failures in internal bdi-kit LLM calls.
  - Frontier config variants were expanded and re-run across contexts.

- **Log/trace analyzer improvements:**
  - `read_and_analyze_logs_and_traces_cli.py` now supports `--diagnostics` for targeted RCA signals (duplicate turns, first-turn file failures, execution hints, output layout, mount visibility hints).
  - Analyzer remains taxonomy-driven via `types_of_log_and_trace_problems.yaml` and now better captures nested output/no-output edge cases.

- **Visualization tooling (new):**
  - Added reusable metrics-visualization package under `src/evaluation/visualization/`:
    - `io.py`, `enrich.py`, `normalize.py`, `aggregate.py`, `plots.py`, `report.py`
  - Added CLI: `src/evaluation/visualize_metrics_cli.py` with subcommands:
    - `summarize`, `bars`, `heatmap`, `confusion`, `errors`, `compare`
  - Supports both static and interactive plotting backends:
    - `--backend seaborn|plotly`
    - `--interactive` shortcut
    - output format includes `html`
  - Added error-analysis features:
    - top errors per column
    - per-column error summaries
    - `--error-columns-only` filtering for error-focused plotting.

- **Run metadata normalization for plotting:**
  - Visualization normalization now uses per-run `.experiment_id` metadata (when present) to enrich run tables with:
    - `run_id`, `slurm_job_id`, `config_path`, `timestamp_utc`, `llm_provider`, `llm_model`
    - bdi-kit internal model settings
    - hostname, beaker port, and log file paths
  - Prompt metadata and prompt-composition hashes are included when available, enabling future prompt-version comparisons.

- **Experiment expansion for benchmarking:**
  - New automated runs were launched for multiple models across contexts (`bdikit_context`, `code_context`, `codeact_context`) including:
    - `kimi-k2.5`, `minimax-m2.5`, `deepseek-v3.2`, `claude-sonnet-4.6`, `nemotron-3-nano`
    - plus requested `gemini-3-flash-preview` in `code_context`.

---

## IMPORTANT: Agent Onboarding Protocol

Before starting any work on this codebase, coding agents MUST:

1. **Check the datasets folder** for Harmonia experiments:
   ```
   harmonia_metadata_agent/raw/datasets_harmonia/
   ```
   This contains the three experiments from the Harmonia paper with all necessary data.

2. **Read the latest instructions** from:
   ```
   harmonia_metadata_agent/analysis/dstoker/harmonia/my_instructions/
   ```
   Always read the most recent file (by date) and ask the user if anything has changed.

---

## Project Goal

This project runs **metadata harmonization agents** using (local) LLMs and the beaker-dev framework to evaluate performance on specific data harmonization tasks.

**Core objective:** Use LLM agents with the BDI-Kit library to automatically harmonize biomedical metadata tables to standard vocabularies (primarily GDC - Genomic Data Commons), measuring and comparing agent performance across different LLMs.

**Current state:**
- Automated experiments work with multiple LLM backends
- Manual interactive experiments via port-forwarded Beaker notebook
- **Implemented:** Metrics evaluation pipeline (`src/evaluation/`) with schema v1.1 for comparing harmonized output to gold standard data
- **Implemented:** Configurable prompts per experiment via YAML config `prompts` section (system prompt, ReAct prelude, tool descriptions, code context prompt)
- **Implemented:** bdi-kit v0.9.0 with configurable LLM selection for schema/value matching via `bdikit_models` YAML section and `HARMONIA_LLM_*` env vars
- **Implemented:** Unified LLM stack using litellm (replaces any-llm-sdk) for both top-level agent and bdi-kit internal calls
- **Implemented:** True CodeAct context (`src/codeact_context/`) — bypasses Archytas ReAct entirely, LLM writes Python code in markdown fences, no tool schemas or structured tool calls
- **Implemented:** Context window management for CodeAct (summarize or truncate strategies)
- **Implemented:** Comprehensive context management for Archytas ReAct via `context_management:` YAML section — configurable summarization thresholds, context window override (critical for Ollama), max ReAct steps, tool output truncation, and optional separate summarization model. Changes span Archytas (`models/base.py`, `models/ollama.py`, `summarizers.py`), Beaker (`lib/config.py`, `lib/agent.py`), and Harmonia (`config.py`, `generate_env.py`, `exec_apptainer_harmonia.sh`, `.env.template`, experiment YAMLs).
- **Implemented:** VRAM estimation logging in `exec_apptainer_harmonia.sh` via `estimate_vram_usage()` — uses `nvidia-smi` after model pre-load to report actual GPU memory used, estimated KV cache at full context length, and warns if peak usage will exceed 80% or 100% of available VRAM.
- **Implemented:** Kernel state budget enforcement (`src/context_management/`) — prevents FETCH_STATE_CODE from sending ~1M-token GDC schema state to the LLM. Implements type blacklisting, variable whitelisting, per-variable size caps, total budget cap, and delta tracking (unchanged vars sent as compact summaries). Applied via Apptainer `.def` patch to `beaker_kernel/subkernels/python.py` at container build time; parameters controlled by `HARMONIA_STATE_*` env vars from experiment YAML. Failure mode 6A added to error taxonomy for observability.

---

## Overview

This codebase automates data harmonization experiments using the BDI-Kit library within Beaker kernel environments. It enables:
- Running scripted LLM conversations for data harmonization tasks
- Supporting 100+ LLM providers via the litellm unified interface
- Executing experiments on HPC clusters via SLURM
- Capturing conversation traces, notebooks, and harmonized output files
- Interactive manual experiments via port-forwarded Beaker notebooks

---

## Experiment Types

### 1. Automated Experiments
Scripted experiments where the exact same interaction script is given to each LLM in turn. The LLM completes the interaction autonomously and results are logged for comparison.

**Location:** `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/`

**How it works:**
1. `exec_apptainer_harmonia.sh` starts Beaker server inside Apptainer container
2. `run_experiment.py` connects via WebSocket, sends scripted messages, captures responses
3. Both processes run outside the container (Python scripts connect to Beaker's WebSocket API)

**Shorthand command (single terminal):**
```bash
cd /path/to/data/directory
./exec_apptainer_harmonia.sh &
sleep 10
python run_experiment.py --config configs/automated/dou_harmonization_anyllm_devstral.yaml
```

**Full srun command for HPC:**
```bash
srun -J harmonia_automated --account=compgen --time=02:00:00 --mem=20G bash -c '
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/data
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/exec_apptainer_harmonia.sh &
BEAKER_PID=$!
sleep 10
python /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/run_experiment.py \
    --config /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml
kill $BEAKER_PID
'
```

### 2. Manual (Interactive) Experiments
Start the beaker-dev server with the correct LLM backend and interactively run analysis in a Beaker notebook via SSH port forwarding to the HPC.

**Location:** `experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/`

**How it works:**
1. `exec_apptainer_harmonia.sh` starts Beaker server inside Apptainer container
2. User interacts via web UI (not a script)
3. `run_manual_experiment.py` passively monitors WebSocket traffic and logs interactions

#### Option A: Single command with logging (recommended)

**Shorthand command:**
```bash
cd /path/to/data/directory
./exec_apptainer_harmonia.sh --config configs/manual/dou_harmonization_manual_devstral.yaml --monitor
```

**Full srun command for HPC:**
```bash
srun -J harmonia_manual --account=compgen --time=04:00:00 --mem=20G bash -c '
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia/one_metadata_table_gdc_schema/data
/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/exec_apptainer_harmonia.sh \
    --config /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/experiments/experiment_1_harmonia_dou2020_gdc/configs/manual/dou_harmonization_manual_devstral.yaml \
    --monitor
'
```

This `--monitor` flag:
1. Starts Beaker server in background
2. Waits for server to be ready
3. Starts the logging monitor in foreground
4. Cleans up Beaker when you press Ctrl+C

#### Option B: Two terminals (for debugging)

**Terminal 1 - Start Beaker server:**
```bash
cd /path/to/data/directory
./exec_apptainer_harmonia.sh --config configs/manual/dou_harmonization_manual_devstral.yaml
```

**Terminal 2 - Start monitor:**
```bash
python run_manual_experiment.py --config configs/manual/dou_harmonization_manual_devstral.yaml
```

#### Option C: Without logging

```bash
# Just start the Beaker server
./exec_apptainer_harmonia.sh --config configs/manual/dou_harmonization_manual_devstral.yaml

# Or use a pre-generated .env file
./exec_apptainer_harmonia.sh --env configs/manual/my_config_associated.env

# Or use default .env (original method)
./exec_apptainer_harmonia.sh --port 8100
```

#### SSH Access

After starting the server (any option above), set up SSH tunnel from your local machine:
```bash
ssh -L 8100:localhost:8100 hpc_login_node
# Then access http://localhost:8100 in browser
```

Manual configs define LLM settings but no automated messages. Use the template at `configs/manual/dou_harmonization_manual_config.template` to create new manual experiment configs.

**Logging for manual experiments:** The `run_manual_experiment.py` script (or `--monitor` flag) connects to the running Beaker server via WebSocket and passively monitors all interactions, creating `trace.json` and `conversation.md` just like automated experiments.

---

## Harmonia Experiments (Datasets)

All experiment data is in: `harmonia_metadata_agent/raw/datasets_harmonia/`

### Experiment 1: One Metadata Table to GDC Schema
**Location:** `one_metadata_table_gdc_schema/`

Proof-of-principle harmonization of a single dataset to GDC standard.
- **Source:** Dou et al. 2020 - Endometrial Carcinoma Proteogenomics
- **Data file:** `data/dou.csv` (17 columns, 190 rows)
- **Task:** Map columns to GDC schema using schema matching and value mapping

### Experiment 2: Two Metadata Tables Harmonization
**Location:** `two_metadata_tables_harmonize/`

Harmonize metadata from two related endometrial cancer studies.
- **Sources:** Dou et al. 2020 + Dou et al. 2023
- **Task:** Combine 153 + 190 samples with different column schemas

### Experiment 3: Ten Metadata Tables Pan-Cancer
**Location:** `ten_metadata_tables_harmonize/`

Large-scale benchmark with ground truth from Li et al. 2023.
- **Sources:** 10 CPTAC cancer studies (PDAC, ccRCC, UCEC, LUAD, HNSCC, BRCA, HGSC, LSCC, COAD, GBM)
- **Ground truth:** `data/ground_truth/li_2023_harmonized_metadata_metadata_table.csv`
- **Task:** Evaluate against manually harmonized reference

Each experiment folder contains:
- `experiment_metadata.yaml` - Configuration with paper citations, DOIs, file specifications
- `readme.md` - Overview and context
- `data/` - CSV/XLSX data files
- `papers/` - Source publication PDFs

---

## Directory Structure

```
harmonia/
├── src/
│   ├── automation/           # Experiment automation framework
│   │   ├── __init__.py       # Exports: load_config, ExperimentConfig, BeakerClient, ExperimentRunner, TraceLogger, ConversationLogger
│   │   ├── client.py         # WebSocket client for Beaker kernel communication
│   │   ├── runner.py         # Experiment execution orchestration
│   │   ├── config.py         # Configuration dataclasses for experiments
│   │   └── logger.py         # Trace and conversation logging
│   │
│   ├── evaluation/            # Metrics evaluation pipeline
│   │   ├── __init__.py
│   │   ├── schemas.py         # Pydantic schemas for metrics.json (v1.1)
│   │   └── metrics.py         # Core metrics calculation functions
│   │
│   ├── prompt_logging.py      # Prompt composition logging (stdout + JSON)
│   │
│   ├── bdikit_context/       # BDI-Kit Beaker context package (ReAct + domain tools)
│   │   ├── __init__.py       # Package init (configures LLM environment)
│   │   ├── __about__.py      # Version info
│   │   ├── context.py        # BeakerContext implementation
│   │   ├── agent.py          # BDIKitAgent with tool definitions
│   │   ├── config/           # Configuration management
│   │   │   └── __init__.py   # LLMConfig, HarmoniaConfig, get_config(), reset_config()
│   │   ├── llm/              # LLM provider system
│   │   │   ├── __init__.py   # configure_llm_environment(), get_provider_info()
│   │   │   ├── litellm_model.py  # ChatLiteLLM, LiteLLMModel (100+ providers via litellm)
│   │   │   └── litellm_direct.py # DirectLiteLLMRunner for non-Beaker use
│   │   ├── prompts/          # Prompt template system
│   │   │   ├── __init__.py   # PromptLoader, get_prompt_loader()
│   │   │   └── *.j2          # Jinja2 templates
│   │   └── procedures/       # Code templates for BDI-Kit functions
│   │       └── python3/
│   │           ├── match_schema.py
│   │           ├── match_values.py
│   │           ├── rank_schema_matches.py
│   │           ├── materialize_mapping.py
│   │           └── get_gdc_acceptable_values.py
│   │
│   ├── code_context/          # Code-only Beaker context (ReAct + run_code tool)
│   │   ├── __init__.py
│   │   ├── context.py         # CodeContext (minimal BeakerContext)
│   │   ├── agent.py           # CodeAgent (minimal BeakerAgent)
│   │   └── prompts/
│   │       └── v1/
│   │           └── system.txt # Default system prompt (versioned)
│   │
│   └── codeact_context/       # True CodeAct context (bypasses Archytas entirely)
│       ├── __init__.py
│       ├── context.py         # CodeActContext (builds litellm model, manages loop)
│       ├── agent.py           # CodeActAgent (overrides react_async) + CodeActAgentLoop
│       └── prompts/
│           └── v1/
│               ├── system.txt          # Default system prompt (versioned)
│               └── summary_template.txt # Default context window summary template
│
├── experiments/
│   ├── experiment_1_harmonia_dou2020_gdc/
│   │   └── configs/
│   │       ├── automated/    # YAML configs for scripted experiments
│   │       │   ├── experiment_config.template
│   │       │   └── dou_harmonization_*.yaml
│   │       ├── manual/       # YAML configs for interactive experiments
│   │       │   ├── dou_harmonization_manual_config.template
│   │       │   └── dou_harmonization_manual_*.yaml
│   │       └── prompts/      # Configurable prompt variants per experiment
│   │           ├── system_prompt/
│   │           │   ├── v1_default/system/main.j2
│   │           │   └── v2_autonomous/system/main.j2
│   │           ├── react_agent_prompts/
│   │           │   ├── v1_default/prelude.txt
│   │           │   └── v2_tool_focused/prelude.txt
│   │           ├── code_context_prompts/
│   │           │   └── v1_default/prompt.txt
│   │           └── codeact_prompts/
│   │               └── v1_harmonization/prompt.txt
│   ├── experiment_2_harmonia_2_metadata_tables_dou2020_dou2023/  # (placeholder)
│   └── experiment_3_harmonia_10_metadata_tables/                  # (placeholder)
│
├── code_development_tools_agents/  # Developer tooling (outside Apptainer)
│   └── monitoring_and_evaluation/
│       ├── read_and_analyze_logs_and_traces_cli.py  # CLI log/trace analyzer
│       └── types_of_log_and_trace_problems.yaml     # Error taxonomy (16 classes)
│
├── plans/                    # Implementation plans (dated .md files)
│   └── 05_02_2026_1200.md   # Plan for any-llm-sdk integration
│
├── my_instructions/          # Latest instructions for agents
│   └── 27_01_2026_1330.md   # Most recent (read this!)
│
├── documentation/
│   ├── codebase_descriptions/
│   │   └── how_this_codebase_works_*.md
│   └── processes/
│       └── 11_02_2026_interpreting_logs_and_traces.md  # Failure mode reference
│
├── jobs/                     # Generated SLURM job scripts
├── results/                  # Experiment output directories
├── logs/                     # SLURM stdout/stderr logs
│
├── run_experiment.py         # CLI entry point for automated experiments
├── run_manual_experiment.py  # CLI entry point for manual experiment logging
├── calculate_metrics.py      # CLI entry point for standalone metrics calculation
├── generate_jobs.py          # Script to generate SLURM job scripts
├── generate_env.py           # Generate .env files from experiment configs
│
├── # Container files (NEW and LEGACY)
├── harmonia_beaker_LLM_agent_environment_apptainer.def  # NEW: Apptainer definition with litellm
├── harmonia_beaker_LLM_agent_environment_apptainer.sif  # NEW: Built image with litellm support
├── build_harmonia_apptainer.sh                          # NEW: Build script for new image
├── jupyter.def               # LEGACY: Original Apptainer definition
├── jupyter.sif               # LEGACY: Original built image (fallback)
├── build_apptainer.sh        # LEGACY: Original build script
│
├── exec_apptainer_harmonia.sh # Run script for Beaker server (auto-detects image, per-job Ollama isolation)
├── sbatch_template.sh        # SLURM job template (CPU)
├── sbatch_template_gpu.sh    # SLURM job template (GPU, with Ollama port display)
├── .env                      # API keys and configuration (base file)
└── .env.template             # Template for creating .env files
```

---

## Apptainer Images

### NEW: `harmonia_beaker_LLM_agent_environment_apptainer.sif` (Recommended)

**Base:** Python 3.11

This is the current Apptainer image with litellm and bdi-kit v0.9.0 support. It includes:

- **litellm** - Unified access to 100+ LLM providers (replaces any-llm-sdk)
- **bdi-kit v0.9.0** - Updated data harmonization library with LLM-based matching methods
- **bdikit_context.llm.litellm_model module** - LiteLLMModel and ChatLiteLLM classes
- **langchain-core** - Message type compatibility
- **beaker-kernel >= 1.14.0** - Latest Beaker functionality

**Note:** The container is built from local development forks of beaker-kernel and archytas (`/hpc/compgen/projects/llm_GEO_project/beaker-kernel` and `/hpc/compgen/projects/llm_GEO_project/archytas`) rather than PyPI, so local changes to those repos (e.g. context management patches to `models/base.py`, `models/ollama.py`, `summarizers.py`) take effect when the container is rebuilt.

**Build command:**
```bash
srun -J apptainer_build_claude-code --time=02:30:00 --mem=50G --gres=tmpspace:100G bash
./build_harmonia_apptainer.sh
```

**Verification:**
```bash
apptainer exec harmonia_beaker_LLM_agent_environment_apptainer.sif \
    python3 -c "from bdikit_context.llm.litellm_model import LiteLLMModel; print('OK')"
```

### LEGACY: `jupyter.sif`

The original Apptainer image. Still works but does **NOT** include:
- litellm
- bdikit_context.llm.litellm_model module
- bdi-kit v0.9.0

Use this as a fallback if the new image has issues, but note that `litellm:*` and `anyllm:*` providers won't work.

### Image Auto-Detection

`exec_apptainer_harmonia.sh` automatically detects which image to use:

1. **Priority 1:** `--image` argument (if specified)
2. **Priority 2:** `harmonia_beaker_LLM_agent_environment_apptainer.sif` (new image)
3. **Priority 3:** `jupyter.sif` (legacy fallback)

---

## Key Components

### 1. Automation Framework (`src/automation/`)

#### `client.py` - BeakerClient
Handles WebSocket communication with the Beaker Jupyter server.

**Class: `AgentResponse`**
```python
@dataclass
class AgentResponse:
    content: str
    response_type: str  # "llm_response", "code_cell", "stream", "error", "timeout"
    raw_messages: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    tool_calls: list[dict] = field(default_factory=list)
```

**Class: `BeakerClient`**
```python
class BeakerClient:
    def __init__(self, server_url: str, token: str, timeout: float = 300.0) -> None

    @property
    def is_connected(self) -> bool

    async def connect(self, context_name: str = None) -> None  # context_name from config
    async def disconnect(self) -> None

    # Message handling
    async def send_message(self, message: str, timeout: Optional[float] = None) -> AgentResponse
    async def send_message_stream(self, message: str, timeout: Optional[float] = None) -> AsyncIterator[dict]

    # Code execution
    async def execute_code(self, code: str, timeout: float = 60.0) -> dict

    # Notebook management
    async def save_notebook(self, cells: list[dict], name: str = "experiment") -> dict
    async def get_notebook(self, session_id: str = None) -> Optional[dict]

    # Context manager support
    async def __aenter__(self) -> "BeakerClient"
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None
```

**Connection Flow:**
```python
async with BeakerClient(server_url, token) as client:
    response = await client.send_message("Load dou.csv...")
    print(response.content)
```

#### `runner.py` - ExperimentRunner
Orchestrates the full experiment lifecycle.

**Class: `ExperimentRunner`**
```python
class ExperimentRunner:
    def __init__(
        self,
        client: BeakerClient,
        config: ExperimentConfig,
        output_dir: Optional[Path] = None,
        on_turn_complete: Optional[Callable[[int, str, AgentResponse], None]] = None,
    ) -> None

    async def run(self, interactive: bool = False) -> Path
    def stop(self) -> None
```

The output directory name includes `RUN_ID` from the environment if available:
`<config.name>_<timestamp>_<run_id>` (or just `<config.name>_<timestamp>` without it).

**Standalone Function:**
```python
async def run_single_message(
    client: BeakerClient,
    message: str,
    timeout: float = 60.0,
) -> AgentResponse
```

**Output Directory Structure:**
```
results/<experiment_name>_<timestamp>[_<run_id>]/
├── .experiment_id      # JSON metadata linking run_id, logs, config
├── trace.json          # Full message trace with raw WebSocket data
├── conversation.md     # Human-readable conversation log
├── dou.csv            # Input data (copied)
└── harmonized_table.csv # Output (if successful)
```

The `run_id` suffix is an 8-character hex string (e.g., `a1b2c3d4`) that uniquely links
logs to results folders. See "Uniform Experiment Tracking" section below.

#### `manual_runner.py` - ManualExperimentRunner
Monitors manual/interactive Beaker sessions and logs all interactions.

**Class: `ManualExperimentRunner`**
```python
class ManualExperimentRunner:
    def __init__(
        self,
        server_url: str,
        token: str,
        config: ExperimentConfig,
        output_dir: Optional[Path] = None,
    ) -> None

    async def start(self) -> None  # Start monitoring (blocks until stop)
    def stop(self) -> None         # Stop monitoring and save logs
```

**Standalone Function:**
```python
async def run_manual_experiment(
    config_path: Path,
    server_url: str = "http://localhost:8100",
    token: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> Path
```

**How it works:**
1. Connects to an existing Beaker kernel via WebSocket
2. Passively monitors all `llm_request` and `llm_response` messages
3. Logs each user-agent interaction as a turn
4. Auto-saves after each turn (crash-safe)
5. On Ctrl+C, finalizes and saves `trace.json` and `conversation.md`

**Usage:**
```bash
# Option 1: Single command with --monitor flag (recommended)
./exec_apptainer_harmonia.sh --config configs/manual/my_config.yaml --monitor

# Option 2: Two terminals (for debugging)
# Terminal 1: Start Beaker
./exec_apptainer_harmonia.sh --config configs/manual/my_config.yaml
# Terminal 2: Start monitor
python run_manual_experiment.py --config configs/manual/my_config.yaml
```

#### `config.py` - Configuration Dataclasses
Defines the structure of experiment configuration.

```python
@dataclass
class LLMConfig:
    provider: str
    model: str
    temperature: float = 0.0
    context_length: Optional[int] = None  # Ollama context window (e.g. 64000)

@dataclass
class MessageConfig:
    content: str
    wait_seconds: int = 30
    decision_mode: Optional[str] = None  # "auto_accept", "predefined", "llm_decides"

@dataclass
class OutputConfig:
    base_dir: str = "./results"
    save_artifacts: list[str] = field(default_factory=list)

@dataclass
class DecisionConfig:
    default_mode: str = "auto_accept"
    predefined_responses: dict[str, str] = field(default_factory=dict)

@dataclass
class PromptsConfig:
    prompts_base_dir: Optional[str] = None
    system_prompt_dir: Optional[str] = None
    react_prelude: Optional[str] = None
    code_context_prompt: Optional[str] = None
    codeact_prompt: Optional[str] = None       # Custom CodeAct system prompt
    tool_prompts_dir: Optional[str] = None

@dataclass
class PythonKernelContextConfig:
    """Configuration for kernel state budget enforcement (FETCH_STATE_CODE patch)."""
    max_variable_size: int = 20_000
    state_budget_pct: int = 25
    type_blacklist: list[str]   # default: SchemaGraph, SimilarityFloodingMatcher, ...
    var_whitelist: list[str]    # default: df, df_harmonized, result, ...

@dataclass
class ArchytasContextConfig:
    """Configuration for Archytas agent/model context management."""
    summarization_threshold_pct: int = 50
    context_window_override: Optional[int] = None  # Force context window size (critical for Ollama)
    max_tokens: Optional[int] = None
    tool_output_summarization_threshold: int = 1000
    tool_output_snippet_size: int = 1000
    max_react_steps: Optional[int] = 30
    max_errors: int = 3
    summarization_model: Optional[str] = None       # Separate model for summarization
    summarization_model_provider: Optional[str] = None

@dataclass
class ContextManagementConfig:
    python_kernel: PythonKernelContextConfig
    archytas: ArchytasContextConfig

@dataclass
class ExperimentConfig:
    name: str
    description: str
    llm: LLMConfig
    messages: list[MessageConfig]
    output: OutputConfig = field(default_factory=OutputConfig)
    decision_handling: DecisionConfig = field(default_factory=DecisionConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    context_management: ContextManagementConfig = field(default_factory=ContextManagementConfig)
    # Manual mode: if True, this config is for manual experiments (no automated messages)
    manual_mode: bool = False
    # Optional reference to dataset metadata YAML
    dataset_metadata: Optional[str] = None
    # Beaker context to use: "bdikit_context", "code_context", or "codeact_context"
    context: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig"

def load_config(config_path: str | Path) -> ExperimentConfig
def load_conversation(conversation_path: str | Path) -> list[MessageConfig]
```

#### `logger.py` - Logging Classes

**Dataclasses:**
```python
@dataclass
class TurnRecord:
    turn: int
    user_message: str
    agent_response: str
    response_type: str
    tool_calls: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    raw_messages: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class ExperimentTrace:
    experiment_name: str
    description: str
    llm_provider: str
    llm_model: str
    start_time: str
    end_time: Optional[str] = None
    turns: list[TurnRecord] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    status: str = "running"  # running, completed, failed, timeout, cancelled
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]
```

**Class: `TraceLogger`** - Full JSON traces
```python
class TraceLogger:
    def __init__(self, output_dir: Path) -> None
    def start_experiment(self, experiment_name: str, description: str, llm_provider: str, llm_model: str) -> None
    def log_turn(self, turn: int, user_message: str, agent_response: str, response_type: str,
                 tool_calls: list[dict] = None, duration_seconds: float = 0.0, raw_messages: list[dict] = None) -> None
    def end_experiment(self, status: str = "completed", error_message: Optional[str] = None) -> None
    def save(self, filename: str = "trace.json") -> Path
    def build_notebook_cells(self) -> list[dict]
```

**Class: `ConversationLogger`** - Markdown conversation logs
```python
class ConversationLogger:
    def __init__(self, output_dir: Path) -> None
    def start_experiment(self, experiment_name: str, description: str, llm_provider: str, llm_model: str) -> None
    def log_turn(self, turn: int, user_message: str, agent_response: str, response_type: str = "llm_response") -> None
    def log_error(self, error_message: str) -> None
    def log_summary(self, total_turns: int, total_duration: float, status: str) -> None
    def save(self, filename: str = "conversation.md") -> Path
    def get_content(self) -> str
```

---

### 2. BDI-Kit Context (`src/bdikit_context/`)

#### `context.py` - BDIKitContext
Beaker context that provides BDI-Kit tools to the LLM agent. Supports per-experiment prompt overrides via env vars.

```python
class BDIKitContext(BeakerContext):
    enabled_subkernels = ["python3"]
    SLUG = "bdikit_context"

    def __init__(self, beaker_kernel: "BeakerKernel", config: Dict[str, Any]) -> None
        # Reads HARMONIA_PROMPTS_DIR env var → creates per-instance PromptLoader
        # Reads HARMONIA_REACT_PRELUDE env var → overrides agent.custom_prelude
        # Calls _override_tool_descriptions() → mutates StructuredTool.description
        # Calls print_prompt_composition() → Output A (stdout layers)
        # Calls register_prompt_json_logger() → Output B (one-shot JSON on first execute)
    def _override_tool_descriptions(self) -> None  # Replaces tool descs from .j2 templates
    async def setup(self, context_info=None, parent_header=None) -> None
    async def auto_context(self) -> str  # Returns system prompt (prints domain prompt on first call)
```

#### `agent.py` - BDIKitAgent
Defines tools available to the LLM for data harmonization.

**Constants:**
```python
VALID_SCHEMA_METHODS = [
    "similarity_flooding", "coma", "cupid", "distribution_based", "jaccard_distance",
    "two_phase", "max_val_sim", "magneto_zs_bp", "magneto_ft_bp", "magneto_zs_llm",
    "magneto_ft_llm", "llm"
]
DEFAULT_SCHEMA_METHOD = "magneto_ft_bp"

VALID_VALUE_METHODS = ["edit_distance", "llm", "llm_numeric", "tfidf", "embedding"]
DEFAULT_VALUE_METHOD = "tfidf"

VALID_TARGETS = ["gdc"]
DEFAULT_TARGET = "gdc"

DEFAULT_OUTPUT_FILE = "harmonized_table.csv"
```

**Available Tools:**

| Tool | Signature | Description |
|------|-----------|-------------|
| `match_schema` | `(dataset: str, agent: AgentRef, target: Optional[str] = None, method: Optional[str] = None) -> str` | Maps source columns to target schema |
| `rank_schema_matches` | `(dataset: str, attribute: str, agent: AgentRef, target: Optional[str] = None, top_k: Optional[int] = None) -> str` | Shows top-k alternative column mappings for an attribute |
| `match_values` | `(dataset: str, column_mapping: str, agent: AgentRef, target: Optional[str] = None, method: Optional[str] = None) -> str` | Maps values between source and target columns |
| `materialize_mapping` | `(dataset: str, mapping_spec: str, agent: AgentRef, output_file: Optional[str] = None) -> str` | Creates the final harmonized table |
| `get_gdc_acceptable_values` | `(attribute: str, agent: AgentRef) -> str` | Lists valid values for GDC attributes |

Note: All Optional parameters have defaults applied internally (target="gdc", method="magneto_ft_bp"/"tfidf").

#### `config/__init__.py` - Configuration Management

**Class: `LLMConfig`** (for bdikit_context)
```python
@dataclass
class LLMConfig:
    provider: str = "openai"  # Can be "litellm:openai", "litellm:ollama", "anyllm:ollama" (backwards compat), etc.
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 4096
    extra: Dict[str, Any] = field(default_factory=dict)
    use_anyllm: bool = False

    def get_effective_provider(self) -> str
```

**Class: `HarmoniaConfig`**
```python
@dataclass
class HarmoniaConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    prompts_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "prompts")
    debug: bool = True

    @classmethod
    def from_env(cls) -> "HarmoniaConfig"

    @classmethod
    def from_yaml(cls, path: Path) -> "HarmoniaConfig"

def get_config() -> HarmoniaConfig
def reset_config() -> None
```

#### `llm/__init__.py` - LLM Provider Configuration

```python
PROVIDER_IMPORT_MAP = {
    # Native Archytas providers
    "openai": "archytas.models.openai.OpenAIModel",
    "ollama": "archytas.models.ollama.OllamaModel",
    "openrouter": "archytas.models.openrouter.OpenRouterModel",
    "anthropic": "archytas.models.anthropic.AnthropicModel",
    ...
    # litellm unified providers (100+ supported, preferred)
    "litellm": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:openai": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:ollama": "bdikit_context.llm.litellm_model.LiteLLMModel",
    ...
    # Backwards compatibility: anyllm: prefix maps to litellm
    "anyllm": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:ollama": "bdikit_context.llm.litellm_model.LiteLLMModel",
    ...
}

def configure_llm_environment() -> None
def get_provider_info() -> dict
```

#### `llm/litellm_model.py` - Unified LLM Provider (via litellm)

**IMPORTANT:** This module requires the new `harmonia_beaker_LLM_agent_environment_apptainer.sif` image. The legacy `jupyter.sif` does not include litellm.

Replaces the previous `anyllm.py` module. Uses litellm's stateless `acompletion()` API instead of any-llm's client-based approach.

```python
class ChatLiteLLM:
    def __init__(self, *, provider: str, model: str, api_key: Optional[str] = None,
                 api_base: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 4096) -> None
    def _build_model_string(self) -> str  # Maps provider+model to litellm format (e.g. "ollama_chat/model")
    def bind_tools(self, tools: Sequence[Any]) -> "ChatLiteLLM"
    def invoke(self, input: list[BaseMessage], *args, **kwargs) -> AIMessage
    async def ainvoke(self, input: list[BaseMessage], *args, **kwargs) -> AIMessage
    def get_num_tokens_from_messages(self, *, messages: list[BaseMessage], tools: Optional[Sequence[Any]] = None) -> int

class LiteLLMModel(BaseArchytasModel):
    DEFAULT_MODEL = "gpt-4o"
    DEFAULT_PROVIDER = "openai"

    def auth(self, **kwargs) -> None          # Handles litellm: and anyllm: prefix stripping
    def initialize_model(self, **kwargs) -> ChatLiteLLM
    async def get_num_tokens_from_messages(self, messages: list[BaseMessage], tools: Optional[Sequence] = None) -> int
    def contextsize(self, model_name: Optional[str] = None) -> int | None  # Uses litellm.get_max_tokens()
```

**litellm model string mapping:**

| Harmonia Provider | litellm Model String | Notes |
|---|---|---|
| `ollama` | `ollama_chat/model` | Use `ollama_chat/` for chat completions |
| `openai` | `model` | No prefix needed for OpenAI |
| `openrouter` | `openrouter/model` | Full path including org |
| `anthropic` | `anthropic/model` | Anthropic prefix required |
| `groq` | `groq/model` | Groq prefix required |

#### `llm/litellm_direct.py` - Direct LLM Runner (No Beaker)

Replaces the previous `direct.py` module.

```python
@dataclass
class DirectLLMConfig:
    provider: str
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 4096
    system_prompt: Optional[str] = None

@dataclass
class DirectLLMResult:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_seconds: float = 0.0
    raw_response: Optional[Any] = None

class DirectLiteLLMRunner:
    def __init__(self, provider: str, model: str, api_key: Optional[str] = None,
                 api_base: Optional[str] = None, temperature: float = 0.0,
                 max_tokens: int = 4096, system_prompt: Optional[str] = None) -> None
    async def complete(self, prompt: str, conversation_history: Optional[list[dict]] = None, **kwargs) -> DirectLLMResult
    async def complete_stream(self, prompt: str, conversation_history: Optional[list[dict]] = None, **kwargs) -> AsyncIterator[str]
    def complete_sync(self, prompt: str, conversation_history: Optional[list[dict]] = None, **kwargs) -> DirectLLMResult
    async def multi_turn_conversation(self, prompts: list[str], **kwargs) -> list[DirectLLMResult]

async def quick_complete(prompt: str, provider: str = "openai", model: str = "gpt-4o", **kwargs) -> str
def quick_complete_sync(prompt: str, provider: str = "openai", model: str = "gpt-4o", **kwargs) -> str
```

#### `prompts/__init__.py` - Prompt Template System

```python
class PromptLoader:
    def __init__(self, prompts_dir: Optional[Path] = None) -> None
    def render(self, template_name: str, **kwargs) -> str
    def get_system_prompt(self, **kwargs) -> str
    def get_tool_description(self, tool_name: str, **kwargs) -> str
    def list_tools(self) -> List[str]

def get_prompt_loader(prompts_dir: Optional[Path] = None) -> PromptLoader
```

---

### 2b. CodeAct Context (`src/codeact_context/`) — True CodeAct

A third Beaker context that **bypasses Archytas entirely**. The LLM writes Python code directly in markdown fences (`\`\`\`python ... \`\`\``). Code is extracted via regex and executed in the Beaker subkernel. No tool schemas, no ReAct prelude, no structured tool calls.

**Paradigm comparison:**

| Paradigm | Context | Agent loop | LLM action format |
|----------|---------|------------|-------------------|
| ReAct + domain tools | `bdikit_context` | Archytas `ReActAgent.react_async()` | Structured JSON tool calls |
| ReAct + run_code only | `code_context` | Archytas `ReActAgent.react_async()` | Structured JSON tool calls |
| True CodeAct | `codeact_context` | Custom `CodeActAgentLoop` | Python code in markdown fences |

#### `context.py` - CodeActContext

```python
class CodeActContext(BeakerContext):
    SLUG = "codeact_context"
    enabled_subkernels = ["python3"]

    def __init__(self, beaker_kernel, config) -> None
        # Passes CodeActAgent to super().__init__() (subkernel works normally)
        # Builds litellm model string from LLM_SERVICE_PROVIDER + LLM_SERVICE_MODEL env vars
        # Creates CodeActAgentLoop and attaches it to self.agent.codeact_loop
        # Reads CODEACT_MAX_TURNS, CODEACT_CONTEXT_STRATEGY, HARMONIA_CODEACT_SUMMARY_TEMPLATE env vars

    async def auto_context(self) -> str
        # Priority: HARMONIA_CODEACT_PROMPT env var → HARMONIA_CODE_CONTEXT_PROMPT → built-in v1 prompt file → hardcoded fallback
        # Returns CodeAct system prompt (no tool schemas, no ReAct prelude)
```

#### `agent.py` - CodeActAgent + CodeActAgentLoop

**CodeActAgent** subclasses `BeakerAgent` and overrides `react_async()`:

```python
class CodeActAgent(BeakerAgent):
    codeact_loop: Optional[CodeActAgentLoop] = None

    async def react_async(self, query: str, react_context: dict = None) -> str
        # Overrides Archytas react_async to run CodeActAgentLoop.run() instead
        # Gets parent_header from react_context["message"].header
        # Creates execute_fn wrapper around self.context.execute()
```

**CodeActAgentLoop** is the core LLM conversation loop (no Archytas dependency):

```python
class CodeActAgentLoop:
    def __init__(
        self,
        model: str,              # litellm model string
        system_prompt: str,
        max_turns: int = 30,
        temperature: float = 0.0,
        context_strategy: str = "summarize",  # "summarize", "truncate", or "none"
        summary_template: Optional[str] = None,
        context_budget_fraction: float = 0.80,
    ) -> None

    def reset(self) -> None              # Clear conversation history
    async def run(                       # Run the CodeAct loop for one user message
        self,
        user_message: str,
        execute_fn,                      # async callable(code) -> dict
        parent_header: dict,
    ) -> str                             # Returns final LLM text (no code)
```

**Loop logic:**
1. Append user message to history
2. Call LLM via `litellm.acompletion()` with system prompt + history
3. Extract code blocks via `CODE_BLOCK_PATTERN` regex
4. If no code: return assistant text as final answer
5. If code found: execute via `execute_fn(code)` → collect stdout/stderr/error from result dict
6. Append execution output as `[Execution output]` user message
7. Repeat from step 2 until max_turns

**Context window management** (triggered when token count exceeds `context_budget_fraction * model_limit`):

| Strategy | Env var value | Behavior |
|----------|---------------|----------|
| Summarize | `CODEACT_CONTEXT_STRATEGY=summarize` | Ask LLM to summarize history + kernel variables, replace history with summary |
| Truncate | `CODEACT_CONTEXT_STRATEGY=truncate` | Keep first 20% and last 20% of messages, drop middle 60% |
| None | `CODEACT_CONTEXT_STRATEGY=none` | No management, litellm will error on overflow |

The summarize strategy uses `HARMONIA_CODEACT_SUMMARY_TEMPLATE` env var for a custom template, or falls back to a built-in default. It also introspects current kernel variables via a `globals()` listing before summarizing.

#### Environment variables

| Env Variable | Default | Purpose |
|---|---|---|
| `CODEACT_MAX_TURNS` | `30` | Maximum code-execute cycles per user message |
| `CODEACT_CONTEXT_STRATEGY` | `summarize` | Context window management: "summarize", "truncate", or "none" |
| `HARMONIA_CODEACT_PROMPT` | (none) | Path to custom CodeAct system prompt file |
| `HARMONIA_CODEACT_SUMMARY_TEMPLATE` | (none) | Path to custom context window summarization template |

---

### 3. Experiment Configuration

Experiments are defined in YAML files in `experiments/experiment_*/configs/`.

#### Automated Experiments (`configs/automated/`)

Scripted experiments with predefined messages:

```yaml
experiment:
  name: "dou_harmonization_devstral"
  description: "Harmonize dou.csv using Devstral"

llm:
  provider: anyllm:ollama    # or "litellm:ollama", "ollama", "openrouter", etc.
  model: devstral:latest
  base_url: http://localhost:11434
  temperature: 0.0
  context_length: 64000      # Ollama context window (optional, sets OLLAMA_CONTEXT_LENGTH)

# bdi-kit internal LLM configuration (optional — defaults to top-level llm.model)
bdikit_models:
  instance_matching_llm: devstral:latest
  numeric_instance_matching_llm: devstral:latest
  schema_matching_llm: devstral:latest
  magneto_zero_shot_schema_matching_llm: devstral:latest
  magneto_fine_tuned_schema_matching_llm: devstral:latest

context_management:
  python_kernel:
    max_variable_size: 20000     # Max chars per variable in kernel state
    state_budget_pct: 25         # Total state budget as % of context window
  archytas:
    summarization_threshold_pct: 50   # When to trigger history summarization (% of context)
    context_window_override: 64000    # Force context window size (critical for Ollama)
    max_react_steps: 30               # Max ReAct loop iterations per query

messages:
  - content: |
      Load the file dou.csv as a dataframe...
    wait_seconds: 180
    decision_mode: auto_accept

output:
  base_dir: "./results"
  save_artifacts:
    - "harmonized_table.csv"

decision_handling:
  default_mode: auto_accept
  predefined_responses:
    "choose.*method": "Use the similarity method"

# Optional: configurable prompts (all fields optional)
prompts:
  prompts_base_dir: "../prompts"                              # Relative to config file
  system_prompt_dir: "system_prompt/v2_autonomous"            # Custom system prompt template dir
  react_prelude: "react_agent_prompts/v2_tool_focused/prelude.txt"  # Custom ReAct prelude
  code_context_prompt: "code_context_prompts/v1_default/prompt.txt"  # Custom code context prompt
  codeact_prompt: "codeact_prompts/v1_harmonization/prompt.txt"    # Custom CodeAct prompt
  tool_prompts_dir: "bdikit_prompts/v2_detailed"              # Custom tool description templates
```

**CodeAct experiments** use `context: codeact_context` in the `experiment:` section:

```yaml
experiment:
  name: dou_harmonization_codeact_devstral
  description: "Harmonize using true CodeAct (no tools, no Archytas)"
  context: codeact_context          # Selects the CodeAct context

llm:
  provider: openrouter
  model: mistralai/devstral-small-2505
  temperature: 0.0

prompts:
  prompts_base_dir: "../../prompts"
  codeact_prompt: "codeact_prompts/v1_harmonization/prompt.txt"

messages:
  - content: |
      You have dou.csv in the current directory. Harmonize it to GDC schema...
    wait_seconds: 600
    decision_mode: auto_accept
```

#### Configurable Prompts

Experiments can override prompts via the `prompts:` section in the YAML config. All fields are optional — when omitted, defaults are used. The flow is:

```
YAML prompts section → generate_env.py → HARMONIA_* env vars in .env → exec_apptainer_harmonia.sh binds dirs → BDIKitContext/CodeContext reads env vars
```

| Env Variable | Config Field | Used By | Purpose |
|---|---|---|---|
| `HARMONIA_PROMPTS_DIR` | `system_prompt_dir` | `BDIKitContext.__init__()` | Custom `system/main.j2` template directory |
| `HARMONIA_REACT_PRELUDE` | `react_prelude` | `BDIKitContext.__init__()` | Custom ReAct agent prelude text file |
| `HARMONIA_TOOL_PROMPTS_DIR` | `tool_prompts_dir` | `BDIKitContext._override_tool_descriptions()` | Custom tool `.j2` template directory |
| `HARMONIA_CODE_CONTEXT_PROMPT` | `code_context_prompt` | `CodeContext.auto_context()` | Custom code context prompt text file (overrides built-in `prompts/v1/system.txt`) |
| `HARMONIA_CODEACT_PROMPT` | `codeact_prompt` | `CodeActContext.auto_context()` | Custom CodeAct system prompt text file (overrides built-in `prompts/v1/system.txt`) |
| `HARMONIA_CODEACT_SUMMARY_TEMPLATE` | `codeact_summary_template` | `CodeActContext.__init__()` | Custom context window summarization template (overrides built-in `prompts/v1/summary_template.txt`) |

#### Manual Experiments (`configs/manual/`)

Interactive experiments with no automated messages:

```yaml
experiment:
  name: "dou_gdc_manual_anyllm-ollama_devstral"
  description: "Manual harmonization of dou.csv to GDC schema"
  manual_mode: true
  dataset_metadata: "/path/to/experiment_metadata.yaml"

llm:
  provider: anyllm:ollama
  model: devstral:latest
  temperature: 0.0

output:
  base_dir: "/path/to/harmonia/results"

# Optional: environment settings for generate_env.py
env_settings:
  LLM_SERVICE_PROVIDER: "anyllm:ollama"
  LLM_SERVICE_MODEL: "devstral:latest"

# Optional: data location documentation
data:
  working_directory: "/path/to/data"
  source_file: "dou.csv"
  target_schema: "gdc"

# No messages section - user interacts via Beaker UI
```

**Template:** `configs/manual/dou_harmonization_manual_config.template`

---

### 4. Environment Generation (`generate_env.py`)

Script to generate experiment-specific `.env` files from YAML configs.

```python
def load_base_env(base_env_path: Path) -> str
def load_experiment_config(config_path: Path) -> dict
def update_env_value(env_content: str, key: str, value: str) -> str
def get_provider_import_path(provider: str) -> str
def get_api_key_for_provider(provider: str, env_content: str) -> str
def generate_env_from_config(config_path: Path, base_env_path: Path, output_dir: Path = None) -> Path
```

**Usage:**
```bash
# Generate .env from single config
python generate_env.py --config path/to/config.yaml

# Generate .env for all configs in directory
python generate_env.py --config-dir path/to/configs/

# Specify custom base .env and output directory
python generate_env.py --config config.yaml --base-env /path/to/.env --output-dir ./output/
```

**Output:** Creates `[config_name]_associated.env` files (ignored by `.gitignore`).

**Prompt env vars:** When a `prompts` section exists in the YAML config, `generate_env.py` resolves paths (relative to config file via `prompts_base_dir`) and writes `HARMONIA_PROMPTS_DIR`, `HARMONIA_REACT_PRELUDE`, `HARMONIA_CODE_CONTEXT_PROMPT`, `HARMONIA_TOOL_PROMPTS_DIR` to the `.env` file.

For Ollama providers, also writes `OLLAMA_CONTEXT_LENGTH` if `context_length` is set in the YAML config.

**Context management env vars:** When a `context_management` section exists in the YAML config, `generate_env.py` emits:

| Env Variable | YAML Path | Read by |
|---|---|---|
| `ARCHYTAS_SUMMARIZATION_THRESHOLD_PCT` | `context_management.archytas.summarization_threshold_pct` | Beaker `config.py` → ModelConfig; Archytas `base.py` (fallback) |
| `ARCHYTAS_CONTEXT_WINDOW_OVERRIDE` | `context_management.archytas.context_window_override` | Beaker `config.py` → ModelConfig; Archytas `base.py` + `ollama.py` |
| `ARCHYTAS_TOOL_SUMMARIZATION_THRESHOLD` | `context_management.archytas.tool_output_summarization_threshold` | Archytas `summarizers.py` |
| `ARCHYTAS_TOOL_SNIPPET_SIZE` | `context_management.archytas.tool_output_snippet_size` | Archytas `summarizers.py` |
| `ARCHYTAS_MAX_REACT_STEPS` | `context_management.archytas.max_react_steps` | Beaker `agent.py` → ReActAgent kwargs |
| `ARCHYTAS_MAX_ERRORS` | `context_management.archytas.max_errors` | Beaker `agent.py` → ReActAgent kwargs |
| `ARCHYTAS_SUMMARIZATION_MODEL_CONFIG` | Built from `summarization_model` + `summarization_model_provider` | Archytas `summarizers.py` (lazy model creation) |
| `HARMONIA_STATE_MAX_VAR_SIZE` | `context_management.python_kernel.max_variable_size` | FETCH_STATE_CODE patch |
| `HARMONIA_STATE_BUDGET_PCT` | `context_management.python_kernel.state_budget_pct` | `exec_apptainer_harmonia.sh` (budget calc) |
| `HARMONIA_STATE_TOTAL_BUDGET` | Calculated by exec script from PCT × context_length | FETCH_STATE_CODE patch |
| `HARMONIA_STATE_TYPE_BLACKLIST` | `context_management.python_kernel.type_blacklist` (comma-separated) | FETCH_STATE_CODE patch |
| `HARMONIA_STATE_VAR_WHITELIST` | `context_management.python_kernel.var_whitelist` (comma-separated) | FETCH_STATE_CODE patch |

The `exec_apptainer_harmonia.sh` script also exports `OLLAMA_NUM_CTX` alongside `OLLAMA_CONTEXT_LENGTH` (Ollama uses both depending on version), calculates `HARMONIA_STATE_TOTAL_BUDGET` from percentage × context_length, and pre-pulls Ollama summarization models if configured.

---

### 5. Container Environment

The Apptainer containers provide:
- Jupyter server with Beaker kernel
- BDI-Kit library for data harmonization
- Pre-installed bdikit_context package
- LLM provider libraries

**New image additionally provides:**
- litellm for unified provider support (100+ providers)
- bdi-kit v0.9.0 with LLM-based matching methods
- `bdikit_context.llm.litellm_model` module (ChatLiteLLM, LiteLLMModel)

**Build (new image):**
```bash
srun -J apptainer_build_claude-code --time=02:30:00 --mem=50G --gres=tmpspace:100G bash
./build_harmonia_apptainer.sh
```

**Run:**
```bash
# Using default .env (auto-detects new or legacy image)
./exec_apptainer_harmonia.sh [--port 8100]

# Using custom .env file
./exec_apptainer_harmonia.sh --env path/to/custom.env

# Auto-generate .env from experiment config (recommended for manual experiments)
./exec_apptainer_harmonia.sh --config path/to/experiment_config.yaml

# With logging monitor (single command for manual experiments with logging)
./exec_apptainer_harmonia.sh --config path/to/experiment_config.yaml --monitor

# Explicitly specify image
./exec_apptainer_harmonia.sh --image path/to/custom.sif

# Show help
./exec_apptainer_harmonia.sh --help
```

**Options:**
| Flag | Description |
|------|-------------|
| `--port, -p PORT` | Port to run Beaker on (default: 8100) |
| `--env, -e FILE` | Path to custom .env file |
| `--config, -c FILE` | Path to experiment config YAML (auto-generates .env) |
| `--monitor, -m` | Enable logging monitor (requires --config) |
| `--image, -i FILE` | Path to Apptainer image (default: auto-detect) |
| `--run-id, -R ID` | Unique 8-char hex run ID (auto-generated if not provided) |
| `--job-name NAME` | Job name for logging (default: derived from config) |
| `--help, -h` | Show help message |

**Bind Mounts (automatic):**
The execution script automatically binds:
- Current directory → `/jupyter` (source code access)
- Data directory → same path (read-only): `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/raw/datasets_harmonia`
- Results directory → same path (read-write): `/hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia/results`
- SSL certificate (if available)

**Context Registration:**
The bdikit_context is registered via Python entry points:
```toml
[project.entry-points."beaker.contexts"]
bdikit_context = "bdikit_context.context:BDIKitContext"
```

---

## LLM Provider Configuration

### Supported Providers (100+)

**Native Archytas Providers:**
- openai, ollama, openrouter, anthropic, azure, bedrock, gemini, groq

**litellm Unified Providers (requires new image, preferred):**
Use `litellm:` prefix for unified interface:
- litellm:openai, litellm:ollama, litellm:anthropic, litellm:openrouter
- litellm:mistral, litellm:groq, litellm:together, litellm:perplexity
- litellm:bedrock, litellm:azure, litellm:cohere, litellm:deepseek, litellm:fireworks, litellm:gemini

**Backwards-compatible `anyllm:` prefix:**
All `anyllm:*` provider strings still work and map to litellm under the hood.

### Environment Variables

```bash
# Provider and model
LLM_SERVICE_PROVIDER=anyllm:ollama       # or litellm:ollama (preferred for new configs)
LLM_SERVICE_MODEL=devstral:latest
LLM_PROVIDER_IMPORT_PATH=bdikit_context.llm.litellm_model.LiteLLMModel

# API keys (provider-specific)
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_HOST=http://localhost:11434

# Optional
LLM_TEMPERATURE=0.0
LLM_MAX_TOKENS=4096
LLM_BASE_URL=http://localhost:11434

# bdi-kit internal LLM selection (optional — defaults to LLM_SERVICE_MODEL)
HARMONIA_LLM_FOR_INSTANCE_MATCHING=devstral:latest
HARMONIA_LLM_FOR_NUMERIC_INSTANCE_MATCHING=devstral:latest
HARMONIA_EMBEDDING_MODEL_FOR_INSTANCE_MATCHING=bert-base-multilingual-cased
HARMONIA_LLM_FOR_SCHEMA_MATCHING=devstral:latest
HARMONIA_LLM_FOR_MAGNETO_ZERO_SHOT_SCHEMA_MATCHING=devstral:latest
HARMONIA_LLM_FOR_MAGNETO_FINE_TUNED_SCHEMA_MATCHING=devstral:latest

# Run metadata (passed into container by exec_apptainer_harmonia.sh)
HARMONIA_RUN_ID=a1b2c3d4         # 8-char hex run ID
HARMONIA_EXPERIMENT_NAME=dou_harmonization_devstral  # From YAML config
RESULTS_DIR=/workspace/results    # Container-internal results mount point
```

### Ollama (Local Models)
- Requires GPU partition on HPC for larger models
- Models must be pre-downloaded or pulled at runtime
- No API key needed
- **Context length:** Configurable per-model via `context_length` in YAML config (e.g., `context_length: 64000`). This sets `OLLAMA_CONTEXT_LENGTH` env var for `ollama serve` and passes `num_ctx` in the model pre-warm API call. Default Ollama context is only 4096 tokens, which is too small for harmonization tasks.
- **Model verification:** After model pre-warming, `ollama ps` is run automatically to verify GPU offload percentage. Warnings are logged if the model is not fully loaded on GPU.
- **Per-job isolation:** When running under SLURM, each job gets its own Ollama instance with:
  - Unique port: `11434 + 1 + (SLURM_JOB_ID % 200)` (range 11435-11634)
  - Per-job PID file: `.ollama_${SLURM_JOB_ID}.pid`
  - Per-job runtime directory: `$TMPDIR/ollama_${SLURM_JOB_ID}`
  - Per-job serve log: `ollama_serve_${SLURM_JOB_ID}.log`
- Interactive/manual use (no SLURM) keeps default port 11434 with original sharing behavior

### WebSocket Configuration

- Beaker's WebSocket max message size is set to 20MB (default was 4MB in older tornado versions)
- Configured via `--ServerApp.tornado_settings={"websocket_max_message_size":20971520}` in the Beaker launch command
- This prevents connection drops for models that produce large responses (e.g., qwen3-coder)

### OpenRouter (Cloud Models)
- Access to many model providers through single API
- Requires `OPENROUTER_API_KEY`

---

## Sample Workflows

### Running an Experiment Locally

```bash
# Set environment variables (or use .env file)
export LLM_SERVICE_PROVIDER="anyllm:ollama"
export LLM_SERVICE_MODEL="devstral:latest"

# Start the Beaker server in container
./exec_apptainer_harmonia.sh

# Run experiment (in another terminal)
python run_experiment.py experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_anyllm_devstral.yaml
```

### Running Experiments on HPC (SLURM)

```bash
# Generate SLURM job scripts for all experiments
python generate_jobs.py --config-dir experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/

# Submit a single job
sbatch jobs/dou_harmonization_devstral.sh

# Check job status
squeue -u $USER
```

### Launching Interactive Beaker Server

```bash
# On HPC
./exec_apptainer_harmonia.sh --port 8100

# On local machine (SSH tunnel)
ssh -L 8100:localhost:8100 hpc_user@hpc_login

# Access in browser: http://localhost:8100
# Token is printed in console output
```

---

## Tool Calling Requirements

**Important:** The Beaker kernel uses Archytas ReAct agent which requires LLMs to support function/tool calling. Models without tool support will fail.

**Models with Tool Support (Ollama):**
- devstral:latest
- devstral-small:latest
- qwen3-coder:30b
- olmo3:latest (newer versions)

**Models WITHOUT Tool Support:**
- Some older Ollama models
- Some free-tier OpenRouter models

---

## Evaluation Pipeline (`src/evaluation/`)

### Schema v1.1 (`schemas.py`)

Pydantic models that define the structure of `metrics.json` output:

- **`ExperimentMetadata`** - experiment name, timestamp, LLM provider/model, timing
- **`ColumnMappingMetrics`** - schema mapping quality with dual precision (`precision_excl_null`, `precision_incl_null`), recall, accuracy
- **`ColumnMappingDetail`** - per-column mapping details (correct, wrong, missing, explicitly null)
- **`ColumnValueMetrics`** - per-column value harmonization quality (accuracy, macro-averaged precision/recall/F1 both incl/excl empty)
- **`ErrorCategorization`** - breakdown of errors (whitespace_only, case_only, whitespace_and_case, genuine)
- **`Misclassification`** - individual error details with row index
- **`OverallSummary`** - aggregate statistics across all columns
- **`MetricsResult`** - top-level result with nested `metadata: ExperimentMetadata`, all metrics, diagnostics

### Core Metrics (`metrics.py`)

Key functions:
- `calculate_column_mapping_metrics()` - evaluates how well the LLM mapped source columns to target schema
- `calculate_column_value_metrics()` - evaluates value harmonization quality per column with optional `numeric_tolerance`
- `calculate_all_metrics()` - orchestrates full evaluation with index-based row alignment (inner join when `index_column` provided)

Features:
- **Numeric tolerance** - float columns compared within tolerance (e.g., "23.5" vs "23.50")
- **Index-based row alignment** - joins on index column instead of sort+truncate
- **Dual precision** for column mapping (with and without null mappings)
- **Confusion matrix** per column: `{expected_value: {predicted_value: count}}`
- **Error categorization** - classifies mismatches as whitespace, case, or genuine errors

### Standalone CLI (`calculate_metrics.py`)

```bash
python calculate_metrics.py \
  --results-dir results/<experiment_dir> \
  --gold-standard /path/to/gold_standard.csv \
  --gold-column-mapping /path/to/gold_column_mapping.json \
  --verbose
```

Metrics are also automatically calculated at the end of `run_experiment.py` and `run_manual_experiment.py` if evaluation config is present.

---

## Missing Functionality

The following features are **not yet implemented** and need development:

1. **Experiment 2 and 3 Automation Configs**
   - Currently only Experiment 1 has automated configs
   - Need configs for two-table and ten-table harmonization

2. **Result Aggregation**
   - Scripts to aggregate results across multiple LLM runs
   - Statistical comparison between models

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'bdikit_context.llm.litellm_model'"

**Root Cause:** Using the legacy `jupyter.sif` image which doesn't include litellm.

**Fix:** Build and use the new image:
```bash
srun -J apptainer_build_claude-code --time=02:30:00 --mem=50G --gres=tmpspace:100G bash
./build_harmonia_apptainer.sh
```

The `exec_apptainer_harmonia.sh` script will auto-detect the new image if present.

### "Agent says it doesn't have tools"
**Root Cause:** The `bdikit_context` package entry point is not registered.

**Fix:** Ensure `pyproject.toml` has:
```toml
[project.entry-points."beaker.contexts"]
bdikit_context = "bdikit_context.context:BDIKitContext"
```
Then rebuild the Apptainer image.

### "Context has no workflows: disabling tools"
This message appears in Beaker logs but doesn't affect BDI-Kit tools. The tools are registered via the agent, not workflows.

### "Model does not support tools"
Ensure the model supports function calling. For Ollama, test with:
```bash
curl http://localhost:11434/api/chat -d '{
  "model": "devstral:latest",
  "messages": [{"role": "user", "content": "Hello"}],
  "tools": [{"type": "function", "function": {"name": "test", "parameters": {}}}]
}'
```

### Connection Errors
- Verify Beaker server is running on expected port
- Check token is being passed correctly
- Ensure WebSocket upgrade is supported

### Missing Columns in dou.csv
The experiment prompts reference specific columns. Verify the CSV has:
`Country, Histologic_Grade_FIGO, Histologic_type, FIGO_stage, BMI, Age, Race, Ethnicity, Gender, Tumor_Focality, Tumor_Size_cm`

---

## File Outputs

After a successful experiment run:

- `results/<name>_<timestamp>_<run_id>/trace.json` - Full execution trace
- `results/<name>_<timestamp>_<run_id>/conversation.md` - Readable conversation log
- `results/<name>_<timestamp>_<run_id>/.experiment_id` - JSON metadata linking run_id, logs, config
- `results/<name>_<timestamp>_<run_id>/harmonized_table.csv` - Harmonized output
- `results/<name>_<timestamp>_<run_id>/metrics.json` - Evaluation metrics (if gold standard configured)
- `results/<name>_<timestamp>_<run_id>/metrics_calculation.log` - Metrics calculation log (if run via calculate_metrics.py)
- `results/<name>_<timestamp>_<run_id>/full_prompt_composition.json` - Structured prompt layers with content hashes (written on first LLM call)
- `logs/<DD-MM-YYYY_HHMM>_<name>_<jobid>_<run_id>.out/.err` - SLURM job logs (automated, with run_id)
- `logs/beaker_<YYYYMMDD_HHMMSS>.log` - Beaker server logs (manual mode)
- `logs/ollama_<YYYYMMDD_HHMMSS>.log` - Ollama server logs (local LLM mode)

---

## Uniform Experiment Tracking (Run ID System)

Every experiment run (automated or manual) is assigned a unique **run ID** — an 8-character
lowercase hex string (e.g., `a1b2c3d4`) generated via `secrets.token_hex(4)`.

### How it works

**Automated mode (SBATCH):**

1. The SBATCH template generates `RUN_ID` before log file redirection
2. `RUN_ID` appears in log filenames: `logs/<timestamp>_<name>_<jobid>_<run_id>.out`
3. `RUN_ID` is passed to `exec_apptainer_harmonia.sh` via `--run-id "$RUN_ID"`
4. `exec_apptainer_harmonia.sh` creates results dir: `results/<name>_<timestamp>_<run_id>/`
5. `run_experiment.py` reads `RUN_ID` from environment and includes it in its output directory

**Manual mode (interactive):**

1. `exec_apptainer_harmonia.sh` generates `RUN_ID` itself (no SBATCH template)
2. Results dir includes run_id: `results/<name>_<timestamp>_<run_id>/`
3. No SLURM logs exist; Beaker and Ollama logs are referenced in `.experiment_id`

### `.experiment_id` file

Created in every results directory, this JSON file links all artifacts:

```json
{
  "run_id": "a1b2c3d4",
  "experiment_name": "dou_harmonization_devstral",
  "experiment_mode": "automated",
  "config_file": "path/to/config.yaml",
  "llm_provider": "litellm:ollama",
  "llm_model": "devstral:latest",
  "timestamp": "20260211_143000",
  "slurm_job_id": "46662631",
  "log_files": {
    "stdout": "logs/11-02-2026_1430_dou_harmonization_devstral_46662631_a1b2c3d4.out",
    "stderr": "logs/11-02-2026_1430_dou_harmonization_devstral_46662631_a1b2c3d4.err"
  }
}
```

---

## Prompt Composition Logging (`src/prompt_logging.py`)

Captures the full composed prompt that the LLM sees, for diagnostics and cross-experiment comparison.

### Two Outputs

**Output A — Stdout (SLURM log inspection):**
- `print_prompt_composition()` fires at context `__init__()` time, printing Layer 1 (system message / ReAct prelude), model-specific instructions, custom prelude, and prompt config env vars.
- The auto-context (domain prompt) is printed separately on the first `auto_context()` call, since it's not rendered until then.

**Output B — Structured JSON (`full_prompt_composition.json`):**
- `register_prompt_json_logger()` monkey-patches `agent.execute()` with a one-shot wrapper.
- On the first LLM call, it captures all messages from `ChatHistory.records()`, decomposes them into layers, computes SHA-256 content hashes, and writes `full_prompt_composition.json` to the results directory.
- The wrapper self-removes after firing — no ongoing overhead.

### JSON Structure

```json
{
  "metadata": { "run_id": "a1b2c3d4", "experiment_name": "...", "model_class": "LiteLLMModel", "prompt_config": {} },
  "layers": {
    "system_message": { "content": "...", "content_hash": "...", "char_count": 1179, "custom_prelude_used": false },
    "auto_context_message": { "content": "...", "content_hash": "...", "char_count": 3581 },
    "model_prompt_instructions": { "content": "...", "is_empty": true }
  },
  "messages_sent_to_llm": [ { "type": "SystemMessage", "content": "...", "index": 0, "content_hash": "..." }, ... ],
  "summary": { "total_messages": 2, "total_char_count": 4760, "uses_custom_prompts": false }
}
```

### Environment Variables Required

| Env Var | Set by | Read by | Purpose |
|---------|--------|---------|---------|
| `RESULTS_DIR` | `exec_apptainer_harmonia.sh` | `register_prompt_json_logger()` | Where to write `full_prompt_composition.json` |
| `HARMONIA_RUN_ID` | `exec_apptainer_harmonia.sh` | `register_prompt_json_logger()` | Run ID for JSON metadata |
| `HARMONIA_EXPERIMENT_NAME` | `exec_apptainer_harmonia.sh` | `register_prompt_json_logger()` | Experiment name for JSON metadata |

### Cross-Experiment Comparison

```bash
# Compare system messages by hash
jq '.layers.system_message.content_hash' results/*/full_prompt_composition.json

# Diff domain prompts between two runs
diff <(jq -r '.layers.auto_context_message.content' results/run_A/full_prompt_composition.json) \
     <(jq -r '.layers.auto_context_message.content' results/run_B/full_prompt_composition.json)
```

---

## Log and Trace Analysis Tool

### CLI Tool (`code_development_tools_agents/monitoring_and_evaluation/read_and_analyze_logs_and_traces_cli.py`)

Analyzes experiment logs and traces to detect problems from a 16-class failure taxonomy.

**Usage:**
```bash
# Analyze all experiments in default directories
python read_and_analyze_logs_and_traces_cli.py

# Analyze specific experiment by run_id
python read_and_analyze_logs_and_traces_cli.py --run-id a1b2c3d4

# Analyze specific experiment by name
python read_and_analyze_logs_and_traces_cli.py --experiment dou_harmonization_devstral

# Verbose per-turn analysis
python read_and_analyze_logs_and_traces_cli.py --verbose

# JSON output (Pydantic schema)
python read_and_analyze_logs_and_traces_cli.py --json

# Custom directories
python read_and_analyze_logs_and_traces_cli.py --log-dir ./logs --results-dir ./results
```

**Detection methods:**

- **Keyword matching:** Simple string/regex patterns in log files and trace.json
- **Compound detection:** Multi-condition Python logic for complex failure modes (e.g., "all turns timed out" vs "some turns timed out with successful raw messages")

### Error Taxonomy (`code_development_tools_agents/monitoring_and_evaluation/types_of_log_and_trace_problems.yaml`)

Machine-readable taxonomy with 16 problem classes across 5 categories:

| Category | Problems |
| -------- | -------- |
| 1. Infrastructure | 1A: Beaker Server Hung, 1B: 405 Notebook Save, 1C: ZMQ ReadTimeout |
| 2. Model Config | 2A: Ollama Model Not Found, 2B: Tool Calling Not Supported, 2C: Ollama Runner Crash, 2D: OpenRouter Model Unavailable, 2E: OpenRouter Rate Limit |
| 3. LLM Behavioral | 3A: LLM-Side Timeout, 3B: Not Using Tools, 3C: Hallucinated Output, 3D: WebSocket Size Exceeded, 3E: Context Window Exhaustion, 3F: Response Stream Truncated, 3G: Silent Empty Response |
| 4. Data/Config | 4A: FileNotFoundError — Incorrect Data Path |
| 5. Output | 5A: No Output Produced |

Each class specifies detection keywords, regex patterns, severity, examples, and remediation steps.
