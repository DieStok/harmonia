# Next Steps: LLM-Based Dou Harmonization Experiments

**Date**: 2026-01-13
**Status**: Ready to run experiments

---

## What Was Implemented

In previous sessions, we built a complete automated experiment framework for Harmonia/Beaker:

### Automation Module (`src/automation/`)

- `client.py` - WebSocket client for Beaker/Jupyter interaction
- `runner.py` - Experiment execution orchestrator
- `config.py` - YAML config loading and validation
- `logger.py` - Trace logging (JSON + Markdown)

### CLI Entry Point (`run_experiment.py`)

- Connects to running Beaker server via Jupyter protocol
- Sends messages sequentially per config
- Captures responses and saves traces to `results/` directory

### Experiment Configs

- `experiments/configs/dou_harmonization.yaml` - Main experiment config
- `experiments/conversations/dou_basic.yaml` - Reusable conversation script

### HPC Support

- `sbatch_template.sh` - SLURM job template with dynamic port allocation
- `generate_jobs.py` - Batch job script generator

---

## Issues Fixed

### Issue 1: Connection Error (Different Nodes)

**Problem**: Running Beaker server on one node and `run_experiment.py` on another fails because `localhost:8100` doesn't cross nodes.

**Solution**: Run both in the same `srun` session.

### Issue 2: OpenRouter Provider Not Working

**Problem**: OpenRouter API key was being sent to OpenAI endpoint because:

1. Beaker-kernel's default providers don't include `openrouter`
2. Harmonia's config used `setdefault()` which didn't override empty strings

**Fix Applied**: Changed `src/bdikit_context/llm/__init__.py` to use direct assignment:

```python
os.environ["LLM_PROVIDER_IMPORT_PATH"] = import_path  # was setdefault
os.environ["LLM_SERVICE_MODEL"] = llm.model           # was setdefault
os.environ["LLM_SERVICE_TOKEN"] = llm.api_key         # was setdefault
```

### Issue 3: API Path Mismatch (404 on /api/contexts)

**Problem**: `run_experiment.py` failed with `Failed to get contexts: 404` because the BeakerClient used wrong API path.

**Root Cause**: The client called `/api/contexts` but Beaker registers the handler at `/contexts` (no `/api` prefix).

**API Path Audit Results**:

| Endpoint | Client Used | Beaker Has | Status |
|----------|-------------|------------|--------|
| Sessions list | `/api/sessions` | Standard Jupyter | ✅ OK |
| Contexts list | `/api/contexts` | `/contexts` | ❌ **Fixed** |
| Create session | `/api/sessions/create-with-context` | `/api/sessions/create-with-context` | ✅ OK |
| WebSocket | `/api/kernels/{id}/channels` | Standard Jupyter | ✅ OK |

**Fix Applied**: Changed `src/automation/client.py` line 93:

```python
# Before:
async with self.session.get(f"{self.server_url}/api/contexts") as resp:

# After:
async with self.session.get(f"{self.server_url}/contexts") as resp:
```

---

## How to Run Experiments

### Single Experiment (Interactive)

```bash
# 1. Get an interactive session on a compute node
srun --pty --time=2:00:00 --mem=16G bash

# 2. Navigate to harmonia directory
cd /hpc/compgen/projects/llm_GEO_project/harmonia_metadata_agent/analysis/dstoker/harmonia

# 3. Start Beaker server in background
./exec_apptainer_harmonia.sh &

# 4. Wait for server to start (watch for "Server is running" message)
sleep 30

# 5. Run experiment
python run_experiment.py --config experiments/configs/dou_harmonization.yaml \
                         --token 89f73481102c46c0bc13b2998f9a4fce
```

### Batch Experiments (sbatch)

```bash
# 1. Generate job script
python generate_jobs.py --config experiments/configs/dou_harmonization.yaml

# 2. Submit to queue
sbatch jobs/dou_harmonization.sh

# 3. Monitor
watch squeue -u dstoker

# 4. Check logs
tail -f logs/dou_harmonization_*.out
```

### Multiple Experiments in Parallel

Each job gets a unique port via `PORT=$((8100 + (SLURM_JOB_ID % 100)))`, so multiple jobs can run on the same node.

```bash
# Generate and submit multiple experiments
python generate_jobs.py --config experiments/configs/experiment1.yaml
python generate_jobs.py --config experiments/configs/experiment2.yaml
python generate_jobs.py --config experiments/configs/experiment3.yaml

# Submit all
for job in jobs/*.sh; do sbatch "$job"; done
```

---

## Current Configuration

From `.env`:

```
LLM_SERVICE_PROVIDER=openrouter
LLM_SERVICE_MODEL=xiaomi/mimo-v2-flash:free
OPENROUTER_API_KEY=sk-or-v1-...
```

---

## Output Directory Structure

Results are saved to:

```
results/
  dou_harmonization_20260113_120000/
    trace.json           # Full execution trace
    conversation.md      # Simplified conversation log
    metadata.json        # LLM info, timing, etc.
    artifacts/           # Output files (CSVs, etc.)
```

---

## Verification Checklist

1. [ ] Start Beaker server - check printed environment variables show OpenRouter config
2. [ ] Run `run_experiment.py` from same node
3. [ ] Verify experiment uses OpenRouter (check trace.json for provider info)
4. [ ] Check `results/` directory for output files

---

## Troubleshooting

### "Cannot connect to host localhost:8100"

You're running the client on a different node than the server. Either:

- Run both in the same `srun` session
- Pass `--server http://<node-hostname>:8100` to `run_experiment.py`

### "Error code: 401 - Incorrect API key"

The provider is likely falling back to OpenAI. Check:

1. `.env` has correct `LLM_SERVICE_PROVIDER=openrouter`
2. The code fix in `src/bdikit_context/llm/__init__.py` was applied
3. Restart the Beaker server after changes

### Server Not Starting

Check `.env` file exists and has valid configuration.

### "Failed to get contexts: 404"

The BeakerClient was using wrong API path. This is now fixed in `src/automation/client.py`.
If you see this error, ensure you have the latest version of `client.py`.
