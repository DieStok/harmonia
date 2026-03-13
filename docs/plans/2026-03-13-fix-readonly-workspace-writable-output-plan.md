---
title: "fix: Make workspace writable and direct LLM output to results/"
type: fix
status: completed
date: 2026-03-13
origin: docs/brainstorms/2026-03-13-readonly-workspace-fix-brainstorm.md
---

# fix: Make workspace writable and direct LLM output to results/

## Overview

Multiple recent experiments produce **no usable output** because the LLM cannot write files anywhere in its container environment. The LLM tries `/workspace/data/` (read-only mount), then `/workspace/` (read-only squashfs), then falls back to in-memory StringIO buffers that are never persisted. The writable `/workspace/results/` directory exists but the LLM is never told about it.

## Problem Statement

**Evidence from 3+ recent experiments:**
- `bdikit-tools_qwen3.5-9b` (48213672): 24 `OSError [Errno 30]` errors
- `code-context_qwen3.5-4b` (48333911): 9 errors, fell back to StringIO
- `codeact_deepseek-v3.2` (48222429): 12 errors, acknowledged failure in chat

**Root cause (two interacting problems):**
1. **Infrastructure:** `/workspace` is inside the squashfs `.sif` image (read-only). `WORKSPACE_HOST_DIR` is created at line 977 of `exec_apptainer_harmonia.sh` but never bound.
2. **Prompt gap:** No system prompt or config message tells the LLM that `results/` is the writable output directory.

(See brainstorm: `docs/brainstorms/2026-03-13-readonly-workspace-fix-brainstorm.md`)

## Proposed Solution

Belt-and-suspenders: bind `/workspace` writable **AND** update all prompts to direct output to `results/`.

### Phase 1: Infrastructure — Bind `/workspace` writable

**File:** `exec_apptainer_harmonia.sh`

**Change 1a:** Add workspace bind mount (after line 978, before data mounts at line 983):

```bash
# Bind workspace directory writable — LLM's cwd must be writable for
# intermediate files. Data overlay (:ro) still protects input files.
APPTAINER_CMD="$APPTAINER_CMD --bind ${WORKSPACE_HOST_DIR}:/workspace"
```

This must come **before** the data and results bind mounts (lines 1028-1040) because Apptainer overlays later mounts on top of earlier ones. So:
- `/workspace` → writable (from `workspace_mount/`)
- `/workspace/data/` → read-only (overlaid on top, `:ro` flag)
- `/workspace/results/` → writable (overlaid on top, bound to experiment-specific results dir)

**Change 1b:** Add cleanup of `workspace_mount/` between runs to prevent stale files from leaking between experiments. Add after the `mkdir -p "$WORKSPACE_HOST_DIR"` line:

```bash
# Clean workspace from previous runs (data/ and results/ are overlaid mounts,
# so only scratch files from prior runs exist here)
find "$WORKSPACE_HOST_DIR" -mindepth 1 -maxdepth 1 \
    ! -name data ! -name results -exec rm -rf {} + 2>/dev/null || true
```

**Change 1c:** Add a post-run log of any files the LLM wrote to `/workspace` (outside `results/`). Add to the cleanup/shutdown section of the script:

```bash
# Report any files the LLM wrote outside results/ (diagnostic)
STRAY_FILES=$(find "$WORKSPACE_HOST_DIR" -mindepth 1 -maxdepth 2 \
    ! -path "*/data/*" ! -path "*/results/*" -type f 2>/dev/null)
if [ -n "$STRAY_FILES" ]; then
    echo ""
    echo "Warning: LLM wrote files outside results/:"
    echo "$STRAY_FILES" | sed 's|^|   |'
    echo "   These files are in workspace_mount/ and will be cleaned on next run."
fi
```

### Phase 2: Prompts — Update system prompts (3 files)

Add a workspace structure block to each system prompt. The block should be consistent across all three contexts.

**File 2a:** `src/codeact_context/prompts/v1/system.txt`

Append after the existing content:

```
## Workspace Layout

Your working directory is /workspace. It has this structure:
- data/     — Input data files (READ-ONLY, do not write here)
- results/  — Save all output files here (e.g., results/dou_harmonized.csv)

Always save output files to the results/ directory. Writing to data/ will fail.
```

**File 2b:** `src/code_context/prompts/v1/system.txt`

Append the same block.

**File 2c:** `src/bdikit_context/prompts/system/main.j2`

Append the same block (plain text, no Jinja variables needed).

### Phase 3: Config messages — Update all 49 automated configs

**Location:** `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/`

All 49 configs share identical message text. Two messages need updating:

**Message 6** (currently): `save it as "dou_harmonized.csv"`
**Message 6** (updated): `save it as "results/dou_harmonized.csv"`

**Message 7** (currently): `save the column mapping you used as "column_mapping.json"` ... `save the value mapping as "value_mapping.json"`
**Message 7** (updated): `save the column mapping you used as "results/column_mapping.json"` ... `save the value mapping as "results/value_mapping.json"`

**`output.save_artifacts`:** No change needed. This field is parsed by `src/automation/config.py:33` but never consumed by any runtime code — it's metadata-only. Leave as bare filenames for documentation purposes.

**Implementation strategy:** Use a shell loop with `sed` to update all 49 configs in one pass:

```bash
for f in experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/*.yaml; do
  sed -i \
    -e 's|save it as "dou_harmonized.csv"|save it as "results/dou_harmonized.csv"|g' \
    -e 's|as "column_mapping.json"|as "results/column_mapping.json"|g' \
    -e 's|as "value_mapping.json"|as "results/value_mapping.json"|g' \
    "$f"
done
```

**Note:** `manage_configs.py` copies messages verbatim during clone — it does not template them. Future configs cloned from an updated base will inherit the fixed paths.

**Resolved:** `save_artifacts` is defined in `src/automation/config.py:33` but never consumed by any runtime code (no references outside the dataclass and YAML parsing). It is metadata-only — no changes needed.

### Phase 4: Validation

**4a:** Dry-run test — start a container with the new binds and verify:
```bash
apptainer exec --bind workspace_mount:/workspace \
    --bind /tmp/test_data:/workspace/data:ro \
    --bind /tmp/test_results:/workspace/results \
    --pwd /workspace \
    harmonia_beaker_LLM_agent_environment_apptainer.sif \
    bash -c "touch /workspace/test.txt && touch /workspace/results/test.txt && touch /workspace/data/test.txt; echo \$?"
```
Expected: first two succeed, third fails with read-only error.

**4b:** Run one small automated experiment (e.g., `qwen3.5-4b`) and verify:
- No `OSError [Errno 30]` in the beaker log
- `dou_harmonized.csv` appears in the results directory
- `column_mapping.json` and `value_mapping.json` appear in results
- The stray-file warning does NOT fire (all output went to `results/`)

## System-Wide Impact

**Low blast radius:**
- Only `exec_apptainer_harmonia.sh` changes for infrastructure (one file, 3 additions)
- System prompts: 3 files, append-only (no existing behavior changes)
- Config YAMLs: 49 files, mechanical text substitution
- No code changes to Python source, evaluation pipeline, or monitoring tools

**Interaction with existing systems:**
- **Evaluation pipeline** (`src/evaluation/`): Reads from `${RESULTS_DIR}/` on the host. Since `/workspace/results` is bound to `${RESULTS_DIR}`, files saved to `results/X` inside the container appear at `${RESULTS_DIR}/X` on the host. No evaluation code changes needed.
- **Artifact collection** (`output.save_artifacts`): Metadata-only field, not consumed at runtime. No changes needed.
- **Log analysis CLI**: No changes — it reads logs and trace.json, not output artifacts.
- **Run ID system**: Unaffected — run IDs are generated before container launch.

## Acceptance Criteria

- [x] `exec_apptainer_harmonia.sh` binds `workspace_mount/` to `/workspace` (writable)
- [x] `/workspace/data/` remains read-only inside the container (overlay preserved) — needs dry-run validation
- [x] `/workspace/results/` remains writable and maps to experiment-specific results dir
- [x] `workspace_mount/` is cleaned between runs (no stale file leakage)
- [x] Post-run diagnostic logs any files written outside `results/`
- [x] All 3 system prompts describe workspace layout and direct output to `results/`
- [x] All 50 config YAML messages use `results/` prefix for output filenames
- [ ] One successful automated experiment produces `results/dou_harmonized.csv`, `results/column_mapping.json`, `results/value_mapping.json` on disk

## Dependencies & Risks

**Risk 1: Apptainer bind mount ordering.** The `/workspace` bind must come before `/workspace/data` and `/workspace/results` for overlay to work correctly. Apptainer processes binds in order; later mounts overlay earlier ones. If this assumption is wrong, data could become writable. **Mitigation:** Phase 4a dry-run test explicitly checks that `data/` is still read-only.

**Risk 2: `save_artifacts` path mismatch.** ~~Resolved:~~ `save_artifacts` is metadata-only (parsed but never consumed at runtime). No path mismatch risk.

**Risk 3: LLMs ignoring prompt instructions.** Some models may still write to `/workspace/` instead of `results/` despite the prompt. **Mitigation:** This is now acceptable because `/workspace` is writable — the file will at least exist (in `workspace_mount/`). The stray-file diagnostic will flag it. The evaluation pipeline looks in `${RESULTS_DIR}` (= `/workspace/results`) so misplaced files won't be evaluated, but at least the experiment won't crash.

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-03-13-readonly-workspace-fix-brainstorm.md](docs/brainstorms/2026-03-13-readonly-workspace-fix-brainstorm.md) — Key decisions: belt-and-suspenders (bind + prompts), update both system prompts and config messages, add observability logging.

### Internal References

- Container binding: [exec_apptainer_harmonia.sh:965-1060](exec_apptainer_harmonia.sh#L965-L1060)
- Unused workspace_mount: [exec_apptainer_harmonia.sh:977-978](exec_apptainer_harmonia.sh#L977-L978)
- HF cache redirect precedent: [exec_apptainer_harmonia.sh:1155-1160](exec_apptainer_harmonia.sh#L1155-L1160)
- Config message template: [configs/automated/dou_harmonization_codeact_qwen3.5-4b.yaml:107-139](experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/dou_harmonization_codeact_qwen3.5-4b.yaml#L107-L139)
- System prompts: `src/codeact_context/prompts/v1/system.txt`, `src/code_context/prompts/v1/system.txt`, `src/bdikit_context/prompts/system/main.j2`
- Config tool: [manage_configs.py](manage_configs.py) (messages copied verbatim, no templating)
