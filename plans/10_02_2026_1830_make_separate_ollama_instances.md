# Plan: Separate Ollama Instances Per SLURM Job

**Date:** 10-02-2026
**Goal:** Ensure every SLURM job starts its own isolated Ollama instance so experiments never share GPU memory, inference capacity, or lifecycle.

---

## Problem Summary

Currently, Ollama always runs on port **11434** (hardcoded). When multiple jobs land on the same GPU node, the second job detects the first job's Ollama and **reuses** it. This causes:

1. **Memory contention** -- both models compete for GPU VRAM
2. **Inference slowdown** -- concurrent requests on the same instance
3. **Lifecycle collision** -- the first job to finish kills the shared Ollama via the single `.ollama.pid` file, crashing the other job
4. **Unreliable benchmarks** -- shared resources make timings non-comparable

### What is already isolated (Beaker port)

The **Beaker** port is already randomized per job:

```bash
# sbatch_template.sh:45, sbatch_template_gpu.sh:47
PORT=$((8100 + (SLURM_JOB_ID % 100)))
```

Each job gets its own Beaker server. This part works fine.

### What is NOT isolated (Ollama -- the problem)

The Ollama port is hardcoded in three places and sharing is baked in at multiple layers:

| File | Line | What it does |
|------|------|-------------|
| `exec_apptainer_harmonia.sh` | 34 | `OLLAMA_PORT=11434` (hardcoded) |
| `ollama_config.yaml` | 12 | `host: 0.0.0.0:11434` |
| `start_ollama.sh` | 58 | `OLLAMA_HOST=${OLLAMA_HOST:-"0.0.0.0:11434"}` |
| `start_ollama.sh` | 68-73 | If PID file exists + process alive --> `exit 0` (share) |
| `start_ollama.sh` | 77-82 | If port 11434 in use --> `exit 0` (share) |
| `start_ollama.sh` | 156-161 | Race condition fallback --> `exit 0` (share) |
| `exec_apptainer_harmonia.sh` | 269-304 | `pgrep "ollama serve"` + API responds --> reuse |
| `stop_ollama.sh` | 4 | Single PID file: `.ollama.pid` |

---

## Call Hierarchy (Current)

```
SLURM job submitted (sbatch)
  |
  +-- sbatch_template_gpu.sh
  |     PORT = 8100 + (SLURM_JOB_ID % 100)          <-- Beaker port: UNIQUE per job
  |
  +-- exec_apptainer_harmonia.sh --port $PORT --config ...
        |
        +-- OLLAMA_PORT = 11434                       <-- Ollama port: SHARED (problem!)
        |
        +-- is_local_llm_provider() == true?
        |     |
        |     +-- start_ollama_server()
        |           |
        |           +-- pgrep "ollama serve" --> running?
        |           |     +-- curl localhost:11434 --> responds?
        |           |           +-- YES + model present --> REUSE (return 0)  <-- SHARING!
        |           |           +-- YES + model missing --> pkill, start fresh
        |           |
        |           +-- Not running --> call start_ollama.sh
        |                 |
        |                 +-- start_ollama.sh (in /ollama_run/analysis/dstoker/)
        |                       +-- Reads ollama_config.yaml --> host: 0.0.0.0:11434
        |                       +-- Checks .ollama.pid --> alive? --> exit 0 (SHARE!)
        |                       +-- Checks ss -tlnp :11434 --> in use? --> exit 0 (SHARE!)
        |                       +-- Starts "ollama serve" on port 11434
        |                       +-- Writes PID to .ollama.pid (single file!)
        |
        +-- Sets LLM_BASE_URL = http://$(hostname):11434
        +-- Sets OLLAMA_HOST = http://$(hostname):11434
        +-- Starts Beaker container on $PORT
        |     +-- Beaker connects to OLLAMA_HOST:11434 (shared!)
        |
        +-- On exit: stop_ollama_server()
              +-- Calls stop_ollama.sh
                    +-- Reads .ollama.pid --> kills that PID   <-- Kills shared instance!
                    +-- Removes .ollama.pid
```

---

## Proposed Solution

### Strategy: Dynamic Ollama Port + Per-Job PID Files

Mirror the existing Beaker port randomization for Ollama. Each SLURM job gets:
- Its own Ollama port (derived from `SLURM_JOB_ID`)
- Its own PID file (so stop/cleanup only affects its own instance)
- Its own `OLLAMA_HOME` runtime directory (to avoid any data dir collision)

Interactive/manual use (no SLURM) falls back to the current default port 11434.

### Port Formula

```bash
if [ -n "$SLURM_JOB_ID" ]; then
    OLLAMA_PORT=$((11434 + 1 + (SLURM_JOB_ID % 200)))
else
    OLLAMA_PORT=11434
fi
```

- Range: **11435-11634** (when in SLURM), **11434** (manual/interactive)
- 200 slots -- wider than Beaker's 100 -- to reduce collision likelihood
- `+ 1` ensures SLURM jobs never use the default 11434, so interactive sessions are never disturbed

---

## Files to Modify

### 1. `exec_apptainer_harmonia.sh`

**Location:** `harmonia_metadata_agent/analysis/dstoker/harmonia/exec_apptainer_harmonia.sh`

#### Change A: Dynamic Ollama port (line 34)

**Current:**
```bash
OLLAMA_PORT=11434
```

**New:**
```bash
# Dynamic Ollama port per SLURM job for isolation
# Interactive/manual use (no SLURM_JOB_ID) keeps default 11434
if [ -n "$SLURM_JOB_ID" ]; then
    OLLAMA_PORT=$((11434 + 1 + (SLURM_JOB_ID % 200)))
else
    OLLAMA_PORT=11434
fi
```

#### Change B: Rewrite `start_ollama_server()` (lines 250-441)

The function currently has sharing logic (pgrep check, reuse if running). Replace with:

**When `SLURM_JOB_ID` is set (batch mode):**
- Skip the "is ollama already running" check entirely -- always start a fresh instance
- Export `OLLAMA_HOST=0.0.0.0:$OLLAMA_PORT` before calling `start_ollama.sh`
- Use a per-job PID file: `OLLAMA_PID_FILE="${OLLAMA_DIR}/.ollama_${SLURM_JOB_ID}.pid"`
- Export `OLLAMA_PID_FILE` so `start_ollama.sh` can use it
- Use a per-job data directory: `OLLAMA_HOME=$TMPDIR/ollama_${SLURM_JOB_ID}` (SLURM provides `$TMPDIR`)
- All `curl` calls already use `$OLLAMA_PORT` -- no change needed there
- Update the model pre-load call to use the correct port

**When no `SLURM_JOB_ID` (manual/interactive mode):**
- Keep the current sharing logic (it's fine for single interactive sessions)

#### Change C: Rewrite `stop_ollama_server()` (lines 444-464)

**Current:** calls `stop_ollama.sh` unconditionally (uses shared PID file).

**New:**
- When `SLURM_JOB_ID` is set: kill the Ollama process directly using the per-job PID file, then clean up
- When no `SLURM_JOB_ID`: keep current behavior (call `stop_ollama.sh`)

```bash
stop_ollama_server() {
    # Kill the tail process if running
    if [ -n "$OLLAMA_TAIL_PID" ]; then
        kill $OLLAMA_TAIL_PID 2>/dev/null || true
    fi

    if [ "$OLLAMA_STARTED_BY_US" = true ]; then
        echo ""
        echo "Stopping Ollama server (port ${OLLAMA_PORT})..."

        if [ -n "$SLURM_JOB_ID" ] && [ -n "$OLLAMA_PID_FILE" ] && [ -f "$OLLAMA_PID_FILE" ]; then
            # Per-job cleanup: kill our specific process
            local pid=$(cat "$OLLAMA_PID_FILE")
            kill $pid 2>/dev/null || true
            sleep 2
            kill -9 $pid 2>/dev/null || true
            rm -f "$OLLAMA_PID_FILE"
            # Clean up per-job monitor PID file too
            rm -f "${OLLAMA_PID_FILE%.pid}_monitor.pid"
        else
            # Interactive mode: use shared stop script
            if [ -f "${OLLAMA_DIR}/stop_ollama.sh" ]; then
                "${OLLAMA_DIR}/stop_ollama.sh" 2>/dev/null || true
            fi
        fi

        echo "   Done."
    fi
}
```

#### Change D: Display Ollama port in startup info

Add Ollama port to the existing status output (after line 48 area, and in the status block around line 488):

```bash
echo "   Ollama Port:              ${OLLAMA_PORT}"
```

---

### 2. `start_ollama.sh`

**Location:** `/hpc/compgen/projects/ollama/ollama_run/analysis/dstoker/start_ollama.sh`

#### Change A: Respect `OLLAMA_HOST` environment variable for port override

**Current** (line 52-58): Reads from config, then defaults:
```bash
OLLAMA_HOST=$(parse_yaml "$CONFIG_FILE" "host")
...
OLLAMA_HOST=${OLLAMA_HOST:-"0.0.0.0:11434"}
```

The `OLLAMA_HOST` env var override already works because of how bash variable precedence works -- if `exec_apptainer_harmonia.sh` exports `OLLAMA_HOST=0.0.0.0:$OLLAMA_PORT` before calling `start_ollama.sh`, the `parse_yaml` result gets overwritten. **However**, we need to check precedence.

**New:** Add explicit check before the config file load:

```bash
# Allow caller to override via environment variable (for per-job isolation)
OLLAMA_HOST_OVERRIDE="$OLLAMA_HOST"

# Load config
if [ -f "$CONFIG_FILE" ]; then
    MODEL_DIR=$(parse_yaml "$CONFIG_FILE" "model_dir")
    DATA_DIR=$(parse_yaml "$CONFIG_FILE" "data_dir")
    [ -z "$OLLAMA_HOST_OVERRIDE" ] && OLLAMA_HOST=$(parse_yaml "$CONFIG_FILE" "host")
    IDLE_TIMEOUT=$(parse_yaml "$CONFIG_FILE" "idle_timeout_minutes")
fi

# Apply override if provided, then defaults
OLLAMA_HOST=${OLLAMA_HOST_OVERRIDE:-${OLLAMA_HOST:-"0.0.0.0:11434"}}
```

#### Change B: Per-job PID file support

**Current** (line 6): `PID_FILE="$SCRIPT_DIR/.ollama.pid"`

**New:**
```bash
# Per-job PID file (passed from exec_apptainer_harmonia.sh) or default
PID_FILE="${OLLAMA_PID_FILE:-$SCRIPT_DIR/.ollama.pid}"
MONITOR_PID_FILE="${PID_FILE%.pid}_monitor.pid"
```

#### Change C: Skip sharing logic when SLURM_JOB_ID is set

**Current** (lines 68-82): If PID file exists or port in use --> exit 0 (share).

**New:**
```bash
# When running as a SLURM job, always start a fresh instance (no sharing)
if [ -z "$SLURM_JOB_ID" ]; then
    # Interactive mode: share if already running (original behavior)
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if kill -0 $OLD_PID 2>/dev/null; then
            echo "Ollama server already running (PID: $OLD_PID)"
            exit 0
        fi
    fi

    OLLAMA_PORT=$(echo "$OLLAMA_HOST" | cut -d':' -f2)
    if ss -tlnp 2>/dev/null | grep -q ":${OLLAMA_PORT} "; then
        echo "Ollama server already running on this node (port $OLLAMA_PORT in use)"
        exit 0
    fi
fi
```

#### Change D: Race condition handler (line 154-161)

Same logic: only share on race condition if **not** in a SLURM job.

**Current:**
```bash
if ! kill -0 $OLLAMA_PID 2>/dev/null; then
    if ss -tlnp 2>/dev/null | grep -q ":${OLLAMA_PORT} "; then
        echo "Sharing the server instead of starting a new one"
        rm -f "$PID_FILE"
        exit 0
    fi
    ...
fi
```

**New:**
```bash
if ! kill -0 $OLLAMA_PID 2>/dev/null; then
    if [ -z "$SLURM_JOB_ID" ] && ss -tlnp 2>/dev/null | grep -q ":${OLLAMA_PORT} "; then
        echo "Sharing the server instead of starting a new one"
        rm -f "$PID_FILE"
        exit 0
    fi
    echo "ERROR: Failed to start server. Check ollama_serve.log"
    rm -f "$PID_FILE"
    exit 1
fi
```

---

### 3. `stop_ollama.sh`

**Location:** `/hpc/compgen/projects/ollama/ollama_run/analysis/dstoker/stop_ollama.sh`

#### Change: Accept PID file as argument or environment variable

**Current:**
```bash
PID_FILE="$SCRIPT_DIR/.ollama.pid"
```

**New:**
```bash
# Accept PID file path as argument, env var, or use default
if [ -n "$1" ]; then
    PID_FILE="$1"
elif [ -n "$OLLAMA_PID_FILE" ]; then
    PID_FILE="$OLLAMA_PID_FILE"
else
    PID_FILE="$SCRIPT_DIR/.ollama.pid"
fi

MONITOR_PID_FILE="${PID_FILE%.pid}_monitor.pid"
```

The rest of the script stays the same -- it reads the PID from file and kills it.

---

### 4. `sbatch_template_gpu.sh` (optional, minor)

**Location:** `harmonia_metadata_agent/analysis/dstoker/harmonia/sbatch_template_gpu.sh`

No changes strictly required -- `exec_apptainer_harmonia.sh` computes `OLLAMA_PORT` from `$SLURM_JOB_ID` which is automatically available in the SLURM environment.

**Optional improvement:** Add a display line for clarity:

```bash
PORT=$((8100 + (SLURM_JOB_ID % 100)))
OLLAMA_PORT=$((11434 + 1 + (SLURM_JOB_ID % 200)))
echo "Using Beaker port: $PORT, Ollama port: $OLLAMA_PORT"
```

This is purely for logging -- the actual computation happens in `exec_apptainer_harmonia.sh`.

---

### 5. `sbatch_template.sh` (no change)

CPU template. Ollama is only started for local LLM providers, which should use the GPU template. No changes needed, but the dynamic port logic in `exec_apptainer_harmonia.sh` will work here too if someone accidentally submits an ollama job on CPU.

---

### 6. No changes needed

These files require **no modifications**:

| File | Reason |
|------|--------|
| `ollama_config.yaml` | Only used as fallback when no env var override; interactive mode keeps 11434 |
| `generate_jobs.py` | Templates contain the logic, not the generator |
| `run_experiment.py` | Connects to Beaker, not Ollama directly |
| `run_manual_experiment.py` | Connects to Beaker, not Ollama directly |
| YAML experiment configs | Specify `provider: ollama`, not port numbers |
| `.env` / `.env.template` | `LLM_BASE_URL` and `OLLAMA_HOST` set dynamically by exec script |
| Python src/ code | Reads `OLLAMA_HOST` from environment at runtime |

---

## Call Hierarchy (After Changes)

```
SLURM job submitted (sbatch)
  |
  +-- sbatch_template_gpu.sh
  |     PORT = 8100 + (SLURM_JOB_ID % 100)              <-- Beaker: UNIQUE
  |
  +-- exec_apptainer_harmonia.sh --port $PORT --config ...
        |
        +-- OLLAMA_PORT = 11434 + 1 + (SLURM_JOB_ID % 200)  <-- Ollama: UNIQUE
        +-- OLLAMA_PID_FILE = .ollama_${SLURM_JOB_ID}.pid    <-- PID file: UNIQUE
        |
        +-- is_local_llm_provider() == true?
        |     |
        |     +-- start_ollama_server()
        |           |
        |           +-- SLURM_JOB_ID is set --> skip sharing checks entirely
        |           +-- Export OLLAMA_HOST=0.0.0.0:${OLLAMA_PORT}
        |           +-- Export OLLAMA_PID_FILE
        |           +-- Export OLLAMA_HOME=$TMPDIR/ollama_${SLURM_JOB_ID}
        |           +-- Call start_ollama.sh
        |                 |
        |                 +-- Respects OLLAMA_HOST override (dynamic port)
        |                 +-- Uses per-job PID file
        |                 +-- SLURM_JOB_ID set --> no sharing, always start fresh
        |                 +-- Starts "ollama serve" on UNIQUE port
        |                 +-- Writes PID to per-job PID file
        |
        +-- Sets LLM_BASE_URL = http://$(hostname):${OLLAMA_PORT}
        +-- Sets OLLAMA_HOST = http://$(hostname):${OLLAMA_PORT}
        +-- Starts Beaker container on $PORT
        |     +-- Beaker connects to OLLAMA_HOST:${OLLAMA_PORT} (ISOLATED!)
        |
        +-- On exit: stop_ollama_server()
              +-- Reads per-job PID file --> kills only OUR Ollama
              +-- Removes per-job PID file
              +-- Other jobs' Ollama instances are UNAFFECTED
```

---

## Edge Cases & Considerations

### GPU VRAM with multiple jobs on same node

Each Ollama instance loads its own model into GPU memory. If SLURM schedules two jobs on the same GPU node, both will try to use the GPU.

**Mitigation:** Use `--gpus-per-node=1` (already in the GPU template) which should give exclusive GPU access. If the HPC allows multiple jobs to share a node with separate GPUs, this is fine -- each job gets its own GPU. If there's only one GPU per node, SLURM should not schedule two GPU jobs on the same node.

Verify with: `scontrol show partition gpu` to check `OverSubscribe` setting.

### Model storage directory (shared, read-only)

All Ollama instances share `ollama_models/` for **reading** model weights. This is safe -- Ollama model files are immutable once downloaded. No lock contention.

### OLLAMA_HOME (runtime data)

Ollama writes runtime data to `OLLAMA_HOME`. With shared `OLLAMA_HOME`, two instances might conflict on lock files or temporary state.

**Solution:** Set per-job `OLLAMA_HOME`:
```bash
export OLLAMA_HOME="$TMPDIR/ollama_${SLURM_JOB_ID}"
mkdir -p "$OLLAMA_HOME"
```

`$TMPDIR` is provided by SLURM and cleaned up automatically when the job ends.

### Interactive/manual use (no SLURM)

Falls back to default port 11434 with original sharing behavior. Only one manual session at a time -- this is acceptable and expected.

### Port collisions

The formula `11434 + 1 + (SLURM_JOB_ID % 200)` gives 200 slots. Port collision requires two jobs with `JOB_ID` values differing by exactly 200 to be scheduled on the same node. This is extremely unlikely given HPC scheduling but not impossible.

**If needed later:** switch to `SLURM_JOB_ID % 1000` for 1000 slots (range 11435-12434), or use a truly random port with retry.

### Ollama serve log

Currently all instances log to the same `ollama_serve.log` in the ollama directory. With per-job instances:

**Solution:** Use per-job log: `ollama_serve_${SLURM_JOB_ID}.log`. The exec script already creates per-job `${JOB_NAME}_ollama.log` in the harmonia logs dir, but the inner `start_ollama.sh` also writes to `ollama_serve.log`. Redirect that:
```bash
nohup "$OLLAMA_BIN" serve > "$SCRIPT_DIR/ollama_serve_${SLURM_JOB_ID:-default}.log" 2>&1 &
```

---

## Testing Plan

1. **Single job test:** Submit one GPU job, verify it starts Ollama on a non-default port and Beaker connects correctly
2. **Two concurrent jobs test:** Submit two GPU jobs simultaneously to the same node (if possible), verify each gets its own Ollama instance and port
3. **Cleanup test:** Let one job finish while the other is still running; verify the remaining job's Ollama is unaffected
4. **Interactive test:** Run `exec_apptainer_harmonia.sh` without SLURM (on submit node), verify it still uses port 11434 with original behavior
5. **Model loading test:** Verify model pre-loading works with the dynamic port

---

## Summary of Changes

| # | File | What changes |
|---|------|-------------|
| 1 | `exec_apptainer_harmonia.sh` | Dynamic `OLLAMA_PORT` from `SLURM_JOB_ID`; per-job PID file; skip sharing in SLURM mode; per-job `OLLAMA_HOME`; update `stop_ollama_server()` |
| 2 | `start_ollama.sh` | Respect `OLLAMA_HOST` env override; per-job PID file via `OLLAMA_PID_FILE` env; skip sharing when `SLURM_JOB_ID` set |
| 3 | `stop_ollama.sh` | Accept PID file path as argument or env var |
| 4 | `sbatch_template_gpu.sh` | Optional: display Ollama port in log output |
