# WP-D: manage_configs.py CLI Tool -- Implementation Progress

**Date:** 2026-03-03
**Work Package:** D -- manage_configs.py CLI Tool
**Status:** Complete

## What was done

Created `manage_configs.py` in the repository root -- a standalone CLI tool (~350 lines) for managing experiment configuration YAML files. The tool uses only stdlib + PyYAML (no ruamel.yaml).

### Subcommands implemented

1. **`list`** -- Globs `*.yaml` in a directory (default: `experiments/experiment_1_harmonia_dou2020_gdc/configs/automated/`), loads each with `yaml.safe_load`, and displays: file, name, context, provider, model, context_window_override. Supports `--format table` (aligned columns, default) and `--format json`.

2. **`get`** -- Reads a field via dotted path (e.g. `llm.model`, `context_management.archytas.max_react_steps`) from one or more configs. Prints `filename: value` per file. Supports `--config FILE` for a single file, `--dir DIR` for a directory, and `--filter SUBSTR` to limit by filename substring.

3. **`set`** -- Updates a field via dotted path in one or more configs. Auto-coerces the CLI value string to int, float, bool, None, or str. Supports `--dry-run` (prints what would change without writing), `--filter` for selective updates. Prints `filename: OLD -> NEW` for each changed file. Writes back with `yaml.dump(..., allow_unicode=True, sort_keys=False)`.

4. **`clone`** -- Reads a base config, applies overrides: `--model` sets `llm.model` and all `bdikit_models.*` fields; `--provider` sets `llm.provider`; `--context` sets `experiment.context`. Derives experiment name from `--name` or constructs `{base_stem}_{model_slug}`. Writes to `output_dir/dou_harmonization_{slug}.yaml`. Prints the output path.

5. **`regenerate`** -- Calls `generate_env.py --config <path>` via `subprocess.run` using the project `.venv/bin/python`. Prints stdout/stderr and reports exit code.

6. **`validate`** -- Attempts `load_config(path)` (from `src/automation/config.py`) for each YAML in the directory. Reports OK, PARSE_ERROR, MISSING_FIELD, TYPE_ERROR, or LOAD_ERROR per file. Prints summary `N/M configs valid`. Falls back to basic YAML parse if `load_config` cannot be imported.

### Exit code convention

- 0: full success
- 1: partial failure (some files failed)
- 2: complete failure (all files failed, or critical error like missing directory)

### Design decisions

- **Path resolution:** All relative paths are resolved against `SCRIPT_DIR` (the directory containing manage_configs.py), making the tool work correctly regardless of the user's working directory.
- **Value coercion in `set`:** The `coerce_value` function tries int, float, bool (true/false), null/none -> None, falling back to string. This is deliberate to support common YAML scalar types from the command line.
- **`clone` bdikit_models update:** When `--model` is given, all existing keys in `bdikit_models` are updated to the new model value, matching the convention in existing configs where all bdikit models use the same LLM as the main agent.
- **`validate` import fallback:** If `from automation.config import load_config` fails (e.g. missing dependency), the tool falls back to basic YAML parse + top-level key checks rather than failing entirely.
- **No `ruamel.yaml`:** As specified, only stdlib + PyYAML are used. This means YAML comments are lost when using `set` or `clone` (PyYAML limitation), but structural correctness is preserved with `sort_keys=False`.

## Testing performed

All six subcommands were tested against the real config directories:

- `list` -- displayed all 30 automated configs in table format; JSON format also verified
- `get --field llm.model --filter claude` -- correctly returned 3 Claude configs
- `get --field context_management.archytas.max_react_steps --filter nemotron` -- deep path traversal worked
- `get --field nonexistent.field` -- correctly exited with code 1, printed FIELD_NOT_FOUND
- `set --field llm.temperature --value 0.5 --filter glm --dry-run` -- correctly showed 2 files would change, no files modified
- `clone --base ... --model google/gemini-2.0-flash --provider openrouter` -- created clone with all fields overridden
- `validate` -- all 30 automated configs and 13 manual configs reported OK
- `--help` -- standard argparse help displayed correctly

## Issues encountered

- None. All subcommands worked as specified on the first implementation.

## Files changed

- **Created:** `manage_configs.py` (repo root)
