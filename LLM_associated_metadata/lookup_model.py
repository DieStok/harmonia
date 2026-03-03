#!/usr/bin/env python3
"""
Standalone model lookup tool for querying OpenRouter and Ollama registries.

Usage:
    .venv/bin/python LLM_associated_metadata/lookup_model.py search "claude sonnet"
    .venv/bin/python LLM_associated_metadata/lookup_model.py details openrouter:anthropic/claude-sonnet-4.6
    .venv/bin/python LLM_associated_metadata/lookup_model.py list --source openrouter
    .venv/bin/python LLM_associated_metadata/lookup_model.py config-snippet openrouter:anthropic/claude-sonnet-4.6
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

REGISTRY_DIR = Path(__file__).resolve().parent


def _load_openrouter_registry() -> list[dict]:
    path = REGISTRY_DIR / "openrouter_models.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data.get("data", [])
    except Exception:
        return []


def _load_ollama_registry() -> dict:
    path = REGISTRY_DIR / "ollama_models.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data.get("models", {})
    except Exception:
        return {}


def _infer_model_family_group(model_id: str) -> str | None:
    model_lower = model_id.lower()
    families = {
        "claude": "Claude", "gpt": "GPT", "gemini": "Gemini",
        "deepseek": "DeepSeek", "qwen": "Qwen", "llama": "Llama",
        "mistral": "Mistral", "devstral": "Mistral", "codestral": "Mistral",
        "command": "Cohere", "minimax": "MiniMax", "kimi": "Kimi", "phi": "Phi",
    }
    for token, group in families.items():
        if token in model_lower:
            return group
    return None


def _openrouter_to_metadata(entry: dict) -> dict:
    """Convert an OpenRouter API entry to our model_metadata format."""
    pricing = entry.get("pricing", {})
    arch = entry.get("architecture", {})
    input_mod = arch.get("input_modalities", [])
    output_mod = arch.get("output_modalities", [])
    modalities = sorted(set(input_mod + output_mod)) or None
    supported_params = entry.get("supported_parameters", [])

    try:
        prompt_per_m = float(pricing.get("prompt", "0")) * 1_000_000
    except (TypeError, ValueError):
        prompt_per_m = 0.0
    try:
        completion_per_m = float(pricing.get("completion", "0")) * 1_000_000
    except (TypeError, ValueError):
        completion_per_m = 0.0

    return {
        "pricing_prompt_per_million_tokens": round(prompt_per_m, 4),
        "pricing_completion_per_million_tokens": round(completion_per_m, 4),
        "context_length": entry.get("context_length"),
        "parameter_count_b": None,
        "model_family_group": _infer_model_family_group(entry.get("id", "")),
        "modalities": modalities,
        "supports_tools": "tools" in supported_params if supported_params else None,
        "supports_structured_output": "structured_outputs" in supported_params if supported_params else None,
        "source": "openrouter",
    }


def _ollama_tag_to_metadata(model_name: str, tag_info: dict | None) -> dict:
    """Convert an Ollama tag entry to our model_metadata format."""
    context_k = tag_info.get("context_k") if tag_info else None
    context_length = context_k * 1024 if context_k else None
    return {
        "pricing_prompt_per_million_tokens": 0.0,
        "pricing_completion_per_million_tokens": 0.0,
        "context_length": context_length,
        "parameter_count_b": tag_info.get("parameter_count_b") if tag_info else None,
        "model_family_group": _infer_model_family_group(model_name),
        "modalities": tag_info.get("modalities") if tag_info else None,
        "supports_tools": None,
        "supports_structured_output": None,
        "source": "ollama",
    }


def cmd_search(args) -> int:
    query = args.query.lower()
    results = []

    for entry in _load_openrouter_registry():
        model_id = entry.get("id", "")
        name = entry.get("name", "")
        if query in model_id.lower() or query in name.lower():
            md = _openrouter_to_metadata(entry)
            results.append({
                "source": "openrouter",
                "id": model_id,
                "name": name,
                "context_length": md["context_length"],
                "pricing_prompt": md["pricing_prompt_per_million_tokens"],
                "pricing_completion": md["pricing_completion_per_million_tokens"],
                "family": md["model_family_group"],
            })

    ollama_models = _load_ollama_registry()
    for model_name, data in ollama_models.items():
        if query in model_name.lower():
            tags = data.get("tags", [])
            first_tag = tags[0] if tags else None
            md = _ollama_tag_to_metadata(model_name, first_tag)
            results.append({
                "source": "ollama",
                "id": model_name,
                "name": model_name,
                "context_length": md["context_length"],
                "pricing_prompt": 0.0,
                "pricing_completion": 0.0,
                "family": md["model_family_group"],
                "n_tags": len(tags),
            })

    if not results:
        print(f"No models found matching '{args.query}'")
        return 1

    print(f"Found {len(results)} model(s) matching '{args.query}':\n")
    for r in results:
        pricing_str = f"${r['pricing_prompt']:.2f}/${r['pricing_completion']:.2f} per M tokens" if r['pricing_prompt'] > 0 else "free"
        ctx_str = f"{r['context_length']:,}" if r['context_length'] else "?"
        print(f"  [{r['source']}] {r['id']}")
        print(f"    Context: {ctx_str} | Pricing: {pricing_str} | Family: {r.get('family', '?')}")
        if "n_tags" in r:
            print(f"    Tags: {r['n_tags']}")
        print()
    return 0


def cmd_details(args) -> int:
    ref = args.model_ref
    if ":" in ref and not ref.startswith("ollama:") and not ref.startswith("openrouter:"):
        # Could be an Ollama tag like "qwen3.5:9b"
        source = "ollama"
        model_id = ref
    elif ref.startswith("openrouter:"):
        source = "openrouter"
        model_id = ref[len("openrouter:"):]
    elif ref.startswith("ollama:"):
        source = "ollama"
        model_id = ref[len("ollama:"):]
    else:
        source = "auto"
        model_id = ref

    if source in ("openrouter", "auto"):
        for entry in _load_openrouter_registry():
            if entry.get("id") == model_id:
                print(json.dumps(entry, indent=2))
                return 0

    if source in ("ollama", "auto"):
        ollama_models = _load_ollama_registry()
        base = model_id.split(":")[0] if ":" in model_id else model_id
        if base in ollama_models:
            print(json.dumps({base: ollama_models[base]}, indent=2))
            return 0

    print(f"Model '{ref}' not found in registries.", file=sys.stderr)
    return 1


def cmd_list(args) -> int:
    entries = []

    if args.source in ("openrouter", None):
        for entry in _load_openrouter_registry():
            model_id = entry.get("id", "")
            md = _openrouter_to_metadata(entry)
            if args.filter_text_only and md.get("modalities") and "text" not in [m.lower() for m in md["modalities"]]:
                continue
            entries.append(f"openrouter:{model_id}")

    if args.source in ("ollama", None):
        ollama_models = _load_ollama_registry()
        for model_name in sorted(ollama_models):
            entries.append(f"ollama:{model_name}")

    for e in entries:
        print(e)
    print(f"\nTotal: {len(entries)}")
    return 0


def cmd_config_snippet(args) -> int:
    ref = args.model_ref
    if ref.startswith("openrouter:"):
        source = "openrouter"
        model_id = ref[len("openrouter:"):]
    elif ref.startswith("ollama:"):
        source = "ollama"
        model_id = ref[len("ollama:"):]
    else:
        source = "auto"
        model_id = ref

    metadata = None
    provider = None

    if source in ("openrouter", "auto"):
        for entry in _load_openrouter_registry():
            if entry.get("id") == model_id:
                metadata = _openrouter_to_metadata(entry)
                provider = "openrouter"
                break

    if metadata is None and source in ("ollama", "auto"):
        ollama_models = _load_ollama_registry()
        base = model_id.split(":")[0] if ":" in model_id else model_id
        if base in ollama_models:
            tags = ollama_models[base].get("tags", [])
            tag_info = None
            for t in tags:
                if t.get("tag") == model_id:
                    tag_info = t
                    break
            if tag_info is None and tags:
                tag_info = tags[0]
            metadata = _ollama_tag_to_metadata(model_id, tag_info)
            provider = "ollama"

    if metadata is None:
        print(f"Model '{ref}' not found in registries.", file=sys.stderr)
        return 1

    snippet = {
        "llm": {
            "provider": provider,
            "model": model_id,
            "temperature": 0.0,
        },
        "model_metadata": metadata,
    }
    if metadata.get("context_length"):
        snippet["context_management"] = {
            "archytas": {
                "context_window_override": metadata["context_length"],
            }
        }

    print(yaml.dump(snippet, sort_keys=False, default_flow_style=False).rstrip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Look up model information from registries")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Search models by name (fuzzy)")
    p_search.add_argument("query", help="Search query")

    p_details = sub.add_parser("details", help="Show full details for a model")
    p_details.add_argument("model_ref", help="Model reference, e.g. openrouter:anthropic/claude-sonnet-4.6")

    p_list = sub.add_parser("list", help="List all models from a source")
    p_list.add_argument("--source", choices=["openrouter", "ollama"], help="Filter by source")
    p_list.add_argument("--filter-text-only", action="store_true", help="Only text-capable models")

    p_snippet = sub.add_parser("config-snippet", help="Output config-ready YAML snippet")
    p_snippet.add_argument("model_ref", help="Model reference, e.g. openrouter:anthropic/claude-sonnet-4.6")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "search": cmd_search,
        "details": cmd_details,
        "list": cmd_list,
        "config-snippet": cmd_config_snippet,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
