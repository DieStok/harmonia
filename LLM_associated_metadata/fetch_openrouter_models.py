#!/usr/bin/env python3
"""
Fetch the OpenRouter model registry and save as JSON.

Usage:
    .venv/bin/python LLM_associated_metadata/fetch_openrouter_models.py
    .venv/bin/python LLM_associated_metadata/fetch_openrouter_models.py --force
    .venv/bin/python LLM_associated_metadata/fetch_openrouter_models.py --max-age 48
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
OUTPUT_FILE = Path(__file__).resolve().parent / "openrouter_models.json"


def _file_age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return (time.time() - mtime) / 3600


def fetch_models(api_key: str | None = None) -> dict:
    """Fetch models from the OpenRouter API."""
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(OPENROUTER_API_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _resolve_api_key() -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch OpenRouter model registry")
    parser.add_argument("--force", action="store_true", help="Overwrite regardless of file age")
    parser.add_argument("--max-age", type=float, default=24.0, help="Max file age in hours before re-fetching (default: 24)")
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE, help="Output JSON file path")
    args = parser.parse_args()

    output = args.output

    if not args.force:
        age = _file_age_hours(output)
        if age is not None and age < args.max_age:
            print(f"Registry file is {age:.1f}h old (< {args.max_age}h). Use --force to re-fetch.")
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

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2))

    n_models = len(data.get("data", []))
    size_kb = output.stat().st_size / 1024
    print(f"Saved {n_models} models to {output} ({size_kb:.0f} KB)")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
