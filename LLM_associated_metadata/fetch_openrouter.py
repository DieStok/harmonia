#!/usr/bin/env python3
"""
Fetch OpenRouter model registry and API parameter documentation.

Usage:
    # Fetch both models and parameters (default)
    .venv/bin/python LLM_associated_metadata/fetch_openrouter.py

    # Fetch only models
    .venv/bin/python LLM_associated_metadata/fetch_openrouter.py --models

    # Fetch only parameter meanings
    .venv/bin/python LLM_associated_metadata/fetch_openrouter.py --parameters

    # Force re-fetch regardless of file age
    .venv/bin/python LLM_associated_metadata/fetch_openrouter.py --force
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/models"
REGISTRY_DIR = Path(__file__).resolve().parent
MODELS_FILE = REGISTRY_DIR / "openrouter_models.json"
PARAMS_FILE = REGISTRY_DIR / "openrouter_models_parameter_meanings.json"


def _file_age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return (time.time() - mtime) / 3600


def _resolve_api_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    env_file = REGISTRY_DIR.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    return None


def fetch_models(api_key: str | None = None) -> dict:
    """Fetch models from the OpenRouter API."""
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(OPENROUTER_API_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_parameter_meanings() -> dict:
    """Update parameter meanings by cross-referencing existing definitions with registry.

    Reads the existing parameter meanings JSON for hand-curated descriptions,
    then cross-references with supported_parameters actually seen in the
    models registry to flag any undocumented ones.
    """
    # Load existing curated definitions
    if PARAMS_FILE.exists():
        existing = json.loads(PARAMS_FILE.read_text())
    else:
        existing = {"parameters": {}}

    known_params = existing.get("parameters", {})

    # Scan models registry for all unique supported_parameters
    seen_in_registry: set[str] = set()
    if MODELS_FILE.exists():
        models_data = json.loads(MODELS_FILE.read_text())
        for entry in models_data.get("data", []):
            for p in entry.get("supported_parameters", []):
                seen_in_registry.add(p)

    # Flag any parameters found in models but not documented
    undocumented = seen_in_registry - set(known_params.keys())
    if undocumented:
        for p in sorted(undocumented):
            known_params[p] = {
                "type": "unknown",
                "default": None,
                "range": None,
                "description": f"Parameter '{p}' found in model registry but not yet documented. Check OpenRouter docs.",
            }
        print(f"  Warning: {len(undocumented)} undocumented parameter(s) found: {', '.join(sorted(undocumented))}")

    result = {
        "_source": "https://openrouter.ai/docs/api/reference/parameters",
        "_additional_sources": existing.get("_additional_sources", [
            "https://openrouter.ai/docs/guides/best-practices/reasoning-tokens",
            "https://openrouter.ai/docs/guides/features/plugins/web-search",
        ]),
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "_note": "This file is auto-updated by fetch_openrouter.py --parameters. The _fetched_at field is set on fetch.",
        "parameters": known_params,
    }
    return result


def run_fetch_models(force: bool, max_age: float) -> int:
    """Fetch the models registry."""
    if not force:
        age = _file_age_hours(MODELS_FILE)
        if age is not None and age < max_age:
            print(f"Models registry is {age:.1f}h old (< {max_age}h). Use --force to re-fetch.")
            return 0

    api_key = _resolve_api_key()
    print(f"Fetching models from {OPENROUTER_API_URL} ({'authenticated' if api_key else 'unauthenticated'})...")

    try:
        data = fetch_models(api_key)
    except Exception as exc:
        if not api_key:
            print(f"Unauthenticated fetch failed ({exc}), trying with API key...")
            api_key = _resolve_api_key()
            if api_key:
                data = fetch_models(api_key)
            else:
                print("No API key available. Set OPENROUTER_API_KEY or add it to .env", file=sys.stderr)
                return 1
        else:
            raise

    MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODELS_FILE.write_text(json.dumps(data, indent=2))

    n_models = len(data.get("data", []))
    size_kb = MODELS_FILE.stat().st_size / 1024
    print(f"Saved {n_models} models to {MODELS_FILE.name} ({size_kb:.0f} KB)")
    return 0


def run_fetch_parameters(force: bool, max_age: float) -> int:
    """Update the parameter meanings file."""
    if not force:
        age = _file_age_hours(PARAMS_FILE)
        if age is not None and age < max_age:
            print(f"Parameter meanings file is {age:.1f}h old (< {max_age}h). Use --force to re-fetch.")
            return 0

    print("Updating parameter meanings...")
    data = fetch_parameter_meanings()
    PARAMS_FILE.write_text(json.dumps(data, indent=2))

    n_params = len(data.get("parameters", {}))
    print(f"Saved {n_params} parameter definitions to {PARAMS_FILE.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch OpenRouter model registry and parameter documentation"
    )
    parser.add_argument("--force", action="store_true", help="Overwrite regardless of file age")
    parser.add_argument("--max-age", type=float, default=24.0, help="Max file age in hours before re-fetching (default: 24)")
    parser.add_argument("--models", action="store_true", help="Fetch only the models registry")
    parser.add_argument("--parameters", action="store_true", help="Fetch only the parameter meanings")
    args = parser.parse_args()

    # If neither --models nor --parameters specified, fetch both
    fetch_both = not args.models and not args.parameters

    rc = 0
    if fetch_both or args.models:
        rc = run_fetch_models(args.force, args.max_age)
        if rc != 0:
            return rc

    if fetch_both or args.parameters:
        rc = run_fetch_parameters(args.force, args.max_age)

    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
