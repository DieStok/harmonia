#!/usr/bin/env python3
"""
CLI tool for managing experiment configuration YAML files.

Provides subcommands for agents and humans to list, inspect, modify,
clone, regenerate, and validate experiment configs.

Usage:
    manage_configs.py list [--dir DIR] [--format table|json]
    manage_configs.py get --field DOTTED.PATH [--config FILE | --dir DIR] [--filter SUBSTR]
    manage_configs.py set --field DOTTED.PATH --value VALUE [--config FILE | --dir DIR] [--filter SUBSTR] [--dry-run]
    manage_configs.py clone --base BASE_CONFIG --output-dir DIR [--model MODEL] [--provider PROVIDER] [--context CONTEXT] [--name NAME]
    manage_configs.py regenerate --config FILE
    manage_configs.py validate [--dir DIR]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_DIR = Path(
    "experiments/experiment_1_harmonia_dou2020_gdc/configs/automated"
)

SCRIPT_DIR = Path(__file__).resolve().parent
REGISTRY_DIR = SCRIPT_DIR / "LLM_associated_metadata"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_dir(raw: str | None) -> Path:
    """Return an absolute Path for the config directory."""
    if raw is None:
        return SCRIPT_DIR / DEFAULT_CONFIG_DIR
    p = Path(raw)
    if not p.is_absolute():
        p = SCRIPT_DIR / p
    return p


def yaml_files_in(directory: Path) -> list[Path]:
    """Return sorted list of *.yaml files in *directory*."""
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.yaml"))


def load_yaml(path: Path) -> dict:
    """Load a YAML file and return a dict (empty dict on parse error)."""
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def get_nested(data: dict, dotted_path: str):
    """Traverse *data* using a dotted key path. Returns (value, True) or (None, False)."""
    keys = dotted_path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None, False
    return current, True


def set_nested(data: dict, dotted_path: str, value):
    """Set a value in *data* at the dotted key path, creating intermediate dicts.

    Returns (old_value, True) on success, (None, False) if the path is empty.
    """
    keys = dotted_path.split(".")
    if not keys:
        return None, False

    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current.get(key), dict):
            current[key] = {}
        current = current[key]

    old_value = current.get(keys[-1])
    current[keys[-1]] = value
    return old_value, True


def coerce_value(raw: str):
    """Best-effort coercion of a CLI string into a Python scalar.

    Tries: int, float, bool (true/false), null -> None, then falls back to str.
    """
    if raw.lower() == "null" or raw.lower() == "none":
        return None
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def write_yaml(path: Path, data: dict) -> None:
    """Write *data* back to *path* as YAML, preserving key order."""
    with open(path, "w") as fh:
        yaml.dump(data, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _infer_model_family_group(model_id: str) -> str | None:
    """Infer a human-friendly model family group from the model ID."""
    model_lower = model_id.lower()
    families = {
        "claude": "Claude",
        "gpt": "GPT",
        "gemini": "Gemini",
        "deepseek": "DeepSeek",
        "qwen": "Qwen",
        "llama": "Llama",
        "mistral": "Mistral",
        "devstral": "Mistral",
        "codestral": "Mistral",
        "command": "Cohere",
        "minimax": "MiniMax",
        "kimi": "Kimi",
        "phi": "Phi",
    }
    for token, group in families.items():
        if token in model_lower:
            return group
    return None


def _lookup_openrouter_model(model_id: str) -> dict | None:
    """Look up a model in the OpenRouter registry JSON. Returns model_metadata dict or None."""
    registry_file = REGISTRY_DIR / "openrouter_models.json"
    if not registry_file.exists():
        return None
    try:
        data = json.loads(registry_file.read_text())
    except Exception:
        return None

    for entry in data.get("data", []):
        if entry.get("id") == model_id:
            pricing = entry.get("pricing", {})
            arch = entry.get("architecture", {})
            input_mod = arch.get("input_modalities", [])
            output_mod = arch.get("output_modalities", [])
            modalities = sorted(set(input_mod + output_mod)) or None
            supported_params = entry.get("supported_parameters", [])

            prompt_price = pricing.get("prompt", "0")
            completion_price = pricing.get("completion", "0")
            # OpenRouter prices are per-token; convert to per-million-tokens
            try:
                prompt_per_m = float(prompt_price) * 1_000_000
            except (TypeError, ValueError):
                prompt_per_m = 0.0
            try:
                completion_per_m = float(completion_price) * 1_000_000
            except (TypeError, ValueError):
                completion_per_m = 0.0

            return {
                "pricing_prompt_per_million_tokens": round(prompt_per_m, 4),
                "pricing_completion_per_million_tokens": round(completion_per_m, 4),
                "context_length": entry.get("context_length"),
                "parameter_count_b": None,
                "model_family_group": _infer_model_family_group(model_id),
                "modalities": modalities,
                "supports_tools": "tools" in supported_params if supported_params else None,
                "supports_structured_output": "structured_outputs" in supported_params if supported_params else None,
                "source": "openrouter",
            }
    return None


def _lookup_ollama_model(model_id: str) -> dict | None:
    """Look up a model in the Ollama registry JSON. Returns model_metadata dict or None."""
    registry_file = REGISTRY_DIR / "ollama_models.json"
    if not registry_file.exists():
        return None
    try:
        data = json.loads(registry_file.read_text())
    except Exception:
        return None

    # model_id might be "model:tag" or just "model"
    if ":" in model_id:
        base_name = model_id.split(":")[0]
    else:
        base_name = model_id

    model_entry = data.get("models", {}).get(base_name)
    if not model_entry:
        return None

    # Try to find the exact tag, or use the first tag as default
    tags = model_entry.get("tags", [])
    tag_info = None
    for t in tags:
        if t.get("tag") == model_id:
            tag_info = t
            break
    if tag_info is None and tags:
        tag_info = tags[0]

    context_k = tag_info.get("context_k") if tag_info else None
    context_length = context_k * 1024 if context_k else None

    return {
        "pricing_prompt_per_million_tokens": 0.0,
        "pricing_completion_per_million_tokens": 0.0,
        "context_length": context_length,
        "parameter_count_b": tag_info.get("parameter_count_b") if tag_info else None,
        "model_family_group": _infer_model_family_group(model_id),
        "modalities": tag_info.get("modalities") if tag_info else None,
        "supports_tools": None,
        "supports_structured_output": None,
        "source": "ollama",
    }


def lookup_model_metadata(model_id: str, provider: str | None = None) -> dict | None:
    """Look up model metadata from the appropriate registry.

    Returns a dict suitable for the model_metadata YAML section, or None.
    """
    p = (provider or "").lower()
    if "ollama" in p:
        return _lookup_ollama_model(model_id)
    # Default: try OpenRouter first, then Ollama
    result = _lookup_openrouter_model(model_id)
    if result is None:
        result = _lookup_ollama_model(model_id)
    return result


def filter_configs(configs: list[Path], substr: str | None) -> list[Path]:
    """Return only those configs whose filename contains *substr*."""
    if substr is None:
        return configs
    return [c for c in configs if substr in c.name]


def configs_from_args(args) -> list[Path]:
    """Collect config file(s) from --config or --dir CLI args."""
    if getattr(args, "config", None):
        p = Path(args.config)
        if not p.is_absolute():
            p = SCRIPT_DIR / p
        if not p.exists():
            print(f"Error: config file not found: {p}", file=sys.stderr)
            sys.exit(2)
        return [p]
    directory = resolve_dir(getattr(args, "dir", None))
    configs = yaml_files_in(directory)
    if not configs:
        print(f"Error: no YAML files found in {directory}", file=sys.stderr)
        sys.exit(2)
    return filter_configs(configs, getattr(args, "filter", None))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_list(args) -> int:
    """List configs with key metadata."""
    directory = resolve_dir(getattr(args, "dir", None))
    configs = yaml_files_in(directory)
    if not configs:
        print(f"No YAML files found in {directory}", file=sys.stderr)
        return 2

    rows: list[dict] = []
    for cfg_path in configs:
        try:
            data = load_yaml(cfg_path)
        except Exception:
            rows.append({
                "file": cfg_path.name,
                "name": "PARSE_ERROR",
                "context": "",
                "provider": "",
                "model": "",
                "context_window_override": "",
            })
            continue

        exp = data.get("experiment", {})
        llm = data.get("llm", {})
        cm = data.get("context_management", {})
        arch = cm.get("archytas", {})

        rows.append({
            "file": cfg_path.name,
            "name": exp.get("name", ""),
            "context": exp.get("context", ""),
            "provider": llm.get("provider", ""),
            "model": llm.get("model", ""),
            "context_window_override": str(arch.get("context_window_override", "")),
        })

    fmt = getattr(args, "format", "table")
    if fmt == "json":
        print(json.dumps(rows, indent=2))
    else:
        # Table output with aligned columns
        headers = ["file", "name", "context", "provider", "model", "context_window_override"]
        col_widths = {h: len(h) for h in headers}
        for row in rows:
            for h in headers:
                col_widths[h] = max(col_widths[h], len(str(row.get(h, ""))))

        header_line = "  ".join(h.ljust(col_widths[h]) for h in headers)
        separator = "  ".join("-" * col_widths[h] for h in headers)
        print(header_line)
        print(separator)
        for row in rows:
            print("  ".join(str(row.get(h, "")).ljust(col_widths[h]) for h in headers))

    return 0


def cmd_get(args) -> int:
    """Get a field value from one or more configs."""
    configs = configs_from_args(args)
    field = args.field
    any_found = False

    for cfg_path in configs:
        try:
            data = load_yaml(cfg_path)
        except Exception:
            print(f"{cfg_path.name}: PARSE_ERROR", file=sys.stderr)
            continue

        value, found = get_nested(data, field)
        if found:
            any_found = True
            # Format the value for display
            if isinstance(value, (dict, list)):
                print(f"{cfg_path.name}: {json.dumps(value, indent=2)}")
            else:
                print(f"{cfg_path.name}: {value}")
        else:
            print(f"{cfg_path.name}: FIELD_NOT_FOUND")

    return 0 if any_found else 1


def cmd_set(args) -> int:
    """Set a field value in one or more configs."""
    configs = configs_from_args(args)
    field = args.field
    new_value = coerce_value(args.value)
    dry_run = getattr(args, "dry_run", False)
    failures = 0

    for cfg_path in configs:
        try:
            data = load_yaml(cfg_path)
        except Exception:
            print(f"{cfg_path.name}: PARSE_ERROR -- skipped", file=sys.stderr)
            failures += 1
            continue

        old_value, ok = get_nested(data, field)
        if not ok:
            # Field does not exist yet -- we'll create it
            old_value = "<absent>"

        set_nested(data, field, new_value)

        label = "[dry-run] " if dry_run else ""
        print(f"{label}{cfg_path.name}: {old_value} -> {new_value}")

        if not dry_run:
            try:
                write_yaml(cfg_path, data)
            except Exception as exc:
                print(f"{cfg_path.name}: WRITE_ERROR ({exc})", file=sys.stderr)
                failures += 1

    if failures == len(configs):
        return 2
    if failures > 0:
        return 1
    return 0


def cmd_clone(args) -> int:
    """Clone a config with field overrides."""
    base_path = Path(args.base)
    if not base_path.is_absolute():
        base_path = SCRIPT_DIR / base_path
    if not base_path.exists():
        print(f"Error: base config not found: {base_path}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = SCRIPT_DIR / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = load_yaml(base_path)
    except Exception as exc:
        print(f"Error: failed to parse base config: {exc}", file=sys.stderr)
        return 2

    # Apply overrides
    model = getattr(args, "model", None)
    provider = getattr(args, "provider", None)
    context = getattr(args, "context", None)

    if model:
        set_nested(data, "llm.model", model)
        # Also update all bdikit_models fields if present
        bdikit = data.get("bdikit_models", {})
        if bdikit:
            for key in bdikit:
                bdikit[key] = model

    if provider:
        set_nested(data, "llm.provider", provider)

    if context:
        set_nested(data, "experiment.context", context)

    # Enrich with model metadata from registry
    if model:
        metadata = lookup_model_metadata(model, provider)
        if metadata:
            data["model_metadata"] = metadata
            # Auto-set context_window_override from registry if not already set
            ctx_len = metadata.get("context_length")
            if ctx_len:
                cm = data.setdefault("context_management", {})
                arch = cm.setdefault("archytas", {})
                if not arch.get("context_window_override"):
                    arch["context_window_override"] = ctx_len
            print(f"Enriched with model metadata from {metadata.get('source', 'registry')}", file=sys.stderr)
        else:
            print(f"Warning: model '{model}' not found in registries. model_metadata will use defaults.", file=sys.stderr)
            registry_hint = REGISTRY_DIR / "openrouter_models.json"
            if not registry_hint.exists():
                print("  Hint: run .venv/bin/python LLM_associated_metadata/fetch_openrouter.py", file=sys.stderr)

    # Derive name
    name = getattr(args, "name", None)
    if name:
        slug = name
    else:
        base_stem = base_path.stem
        if model:
            model_slug = model.replace("/", "-").replace(".", "-")
            slug = f"{base_stem}_{model_slug}"
        else:
            slug = base_stem

    # Update experiment name in the data
    if "experiment" not in data:
        data["experiment"] = {}
    data["experiment"]["name"] = slug

    output_filename = f"dou_harmonization_{slug}.yaml"
    output_path = output_dir / output_filename

    try:
        write_yaml(output_path, data)
    except Exception as exc:
        print(f"Error: failed to write clone: {exc}", file=sys.stderr)
        return 2

    print(output_path)
    return 0


def cmd_regenerate(args) -> int:
    """Re-run generate_env.py for a config."""
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = SCRIPT_DIR / config_path
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        return 2

    generate_env_script = SCRIPT_DIR / "generate_env.py"
    if not generate_env_script.exists():
        print(f"Error: generate_env.py not found at {generate_env_script}", file=sys.stderr)
        return 2

    venv_python = SCRIPT_DIR / ".venv" / "bin" / "python"
    if not venv_python.exists():
        print(f"Warning: .venv python not found at {venv_python}, falling back to sys.executable", file=sys.stderr)
        venv_python = sys.executable

    result = subprocess.run(
        [str(venv_python), str(generate_env_script), "--config", str(config_path)],
        capture_output=True,
        text=True,
        cwd=str(SCRIPT_DIR),
    )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        print(f"generate_env.py exited with code {result.returncode}", file=sys.stderr)
        return 1

    return 0


def cmd_validate(args) -> int:
    """Validate all configs in a directory by loading them with load_config."""
    directory = resolve_dir(getattr(args, "dir", None))
    configs = yaml_files_in(directory)
    if not configs:
        print(f"No YAML files found in {directory}", file=sys.stderr)
        return 2

    # Import load_config from the project
    sys.path.insert(0, str(SCRIPT_DIR / "src"))
    try:
        from automation.config import load_config
    except ImportError as exc:
        print(f"Error: cannot import load_config: {exc}", file=sys.stderr)
        print("Falling back to basic YAML parse validation.", file=sys.stderr)
        load_config = None

    failures = 0
    for cfg_path in configs:
        # First: basic YAML parse
        try:
            data = load_yaml(cfg_path)
        except Exception as exc:
            print(f"PARSE_ERROR  {cfg_path.name}: {exc}")
            failures += 1
            continue

        if not isinstance(data, dict):
            print(f"PARSE_ERROR  {cfg_path.name}: top-level is not a mapping")
            failures += 1
            continue

        # Second: structural validation via load_config
        if load_config is not None:
            try:
                load_config(cfg_path)
            except FileNotFoundError:
                # load_config re-raises for missing file, but the file exists
                print(f"MISSING_FILE {cfg_path.name}: file vanished during validation")
                failures += 1
                continue
            except KeyError as exc:
                print(f"MISSING_FIELD {cfg_path.name}: {exc}")
                failures += 1
                continue
            except TypeError as exc:
                print(f"TYPE_ERROR   {cfg_path.name}: {exc}")
                failures += 1
                continue
            except Exception as exc:
                print(f"LOAD_ERROR   {cfg_path.name}: {exc}")
                failures += 1
                continue

        # Third: check for essential top-level keys
        missing = []
        if "experiment" not in data:
            missing.append("experiment")
        if "llm" not in data:
            missing.append("llm")
        if missing:
            print(f"MISSING_FIELD {cfg_path.name}: missing top-level keys: {', '.join(missing)}")
            failures += 1
            continue

        print(f"OK           {cfg_path.name}")

    total = len(configs)
    ok = total - failures
    print(f"\n{ok}/{total} configs valid")

    if failures == total:
        return 2
    if failures > 0:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage_configs.py",
        description="CLI tool for managing experiment configuration YAML files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- list --
    p_list = subparsers.add_parser("list", help="List configs with key metadata")
    p_list.add_argument("--dir", default=None, help="Directory containing YAML configs")
    p_list.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    # -- get --
    p_get = subparsers.add_parser("get", help="Read a field value from configs")
    p_get.add_argument("--field", required=True, help="Dotted path, e.g. llm.model")
    p_get_source = p_get.add_mutually_exclusive_group()
    p_get_source.add_argument("--config", default=None, help="Single config file")
    p_get_source.add_argument("--dir", default=None, help="Directory of configs")
    p_get.add_argument("--filter", default=None, help="Substring filter on filenames")

    # -- set --
    p_set = subparsers.add_parser("set", help="Update a field in configs")
    p_set.add_argument("--field", required=True, help="Dotted path, e.g. llm.model")
    p_set.add_argument("--value", required=True, help="New value (auto-coerced)")
    p_set_source = p_set.add_mutually_exclusive_group()
    p_set_source.add_argument("--config", default=None, help="Single config file")
    p_set_source.add_argument("--dir", default=None, help="Directory of configs")
    p_set.add_argument("--filter", default=None, help="Substring filter on filenames")
    p_set.add_argument("--dry-run", action="store_true", help="Show changes without writing")

    # -- clone --
    p_clone = subparsers.add_parser("clone", help="Create a new config from a base")
    p_clone.add_argument("--base", required=True, help="Path to the base config YAML")
    p_clone.add_argument("--output-dir", required=True, help="Directory to write clone")
    p_clone.add_argument("--model", default=None, help="Override llm.model and bdikit_models")
    p_clone.add_argument("--provider", default=None, help="Override llm.provider")
    p_clone.add_argument("--context", default=None, help="Override experiment.context")
    p_clone.add_argument("--name", default=None, help="Custom experiment name slug")

    # -- regenerate --
    p_regen = subparsers.add_parser("regenerate", help="Rebuild associated .env for a config")
    p_regen.add_argument("--config", required=True, help="Path to config YAML")

    # -- validate --
    p_validate = subparsers.add_parser("validate", help="Validate configs in a directory")
    p_validate.add_argument("--dir", default=None, help="Directory containing YAML configs")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "get": cmd_get,
        "set": cmd_set,
        "clone": cmd_clone,
        "regenerate": cmd_regenerate,
        "validate": cmd_validate,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 2

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
