#!/usr/bin/env python3
"""
Fetch the Ollama model registry by scraping ollama.com and save as JSON.

Usage:
    .venv/bin/python LLM_associated_metadata/fetch_ollama_models.py
    .venv/bin/python LLM_associated_metadata/fetch_ollama_models.py --force
    .venv/bin/python LLM_associated_metadata/fetch_ollama_models.py --models qwen3.5,deepseek-v3.1
    .venv/bin/python LLM_associated_metadata/fetch_ollama_models.py --skip-tags
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OLLAMA_LIBRARY_URL = "https://ollama.com/library"
OUTPUT_FILE = Path(__file__).resolve().parent / "ollama_models.json"
FETCH_DELAY = 0.5  # seconds between per-model page fetches


def _file_age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return (time.time() - mtime) / 3600


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Harmonia-ModelFetcher/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def get_model_names() -> list[str]:
    """Scrape the Ollama library page for all model names."""
    html = _fetch_html(OLLAMA_LIBRARY_URL)
    return re.findall(r'href="/library/([^"]+)"', html)


def _parse_size_gb(raw: str) -> float | None:
    raw = raw.strip()
    if raw == "-" or not raw:
        return None
    m = re.match(r"([\d.]+)\s*(GB|MB)", raw, re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    if m.group(2).upper() == "MB":
        val /= 1024
    return round(val, 2)


def _parse_context_k(raw: str) -> int | None:
    m = re.match(r"(\d+)K", raw.strip(), re.IGNORECASE)
    return int(m.group(1)) if m else None


def _parse_param_count(tag: str) -> float | None:
    """Extract parameter count in billions from a tag name like 'qwen3.5:24b'."""
    m = re.search(r"(\d+(?:\.\d+)?)b", tag.split(":")[-1] if ":" in tag else tag, re.IGNORECASE)
    return float(m.group(1)) if m else None


def _parse_quantization(tag: str) -> str | None:
    """Extract quantization suffix like 'q4_K_M' from a tag."""
    parts = tag.split(":")
    if len(parts) < 2:
        return None
    variant = parts[-1]
    m = re.search(r"(q\d+[_a-zA-Z0-9]*)", variant, re.IGNORECASE)
    return m.group(1) if m else None


def scrape_model_page(model_name: str) -> list[dict]:
    """Scrape a single model page for tag metadata."""
    url = f"{OLLAMA_LIBRARY_URL}/{model_name}"
    try:
        html = _fetch_html(url)
    except Exception as exc:
        print(f"  Warning: failed to fetch {url}: {exc}", file=sys.stderr)
        return []

    tags = []
    # Match the mobile-view tag lines: tag link followed by metadata span
    # Pattern: href="/library/model:tag" ... then size · context · modalities
    tag_pattern = re.compile(
        r'href="/library/' + re.escape(model_name) + r':([^"]+)"[^>]*class="[^"]*sm:hidden[^"]*"',
    )
    # Metadata pattern: size · context window · modalities
    meta_pattern = re.compile(
        r'([\d.]+\s*(?:GB|MB)|-)\s*·\s*(\d+K)\s*context\s*window\s*·\s*([^·<]+?)·',
        re.IGNORECASE,
    )

    # Split HTML into chunks per tag block
    tag_matches = list(tag_pattern.finditer(html))
    for i, tm in enumerate(tag_matches):
        tag_name = f"{model_name}:{tm.group(1)}"
        # Search for metadata after this tag, before the next tag
        end = tag_matches[i + 1].start() if i + 1 < len(tag_matches) else len(html)
        chunk = html[tm.end():end]
        mm = meta_pattern.search(chunk)
        if mm:
            modalities_raw = mm.group(3).strip()
            modalities = [m.strip() for m in modalities_raw.split("&") if m.strip()]
            if not modalities:
                modalities = [modalities_raw] if modalities_raw else ["Text"]
            tags.append({
                "tag": tag_name,
                "size_gb": _parse_size_gb(mm.group(1)),
                "context_k": _parse_context_k(mm.group(2)),
                "modalities": modalities,
                "parameter_count_b": _parse_param_count(tag_name),
                "quantization": _parse_quantization(tag_name),
            })
        else:
            # Minimal entry if metadata parsing fails
            tags.append({
                "tag": tag_name,
                "size_gb": None,
                "context_k": None,
                "modalities": ["Text"],
                "parameter_count_b": _parse_param_count(tag_name),
                "quantization": _parse_quantization(tag_name),
            })

    return tags


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Ollama model registry")
    parser.add_argument("--force", action="store_true", help="Overwrite regardless of file age")
    parser.add_argument("--max-age", type=float, default=24.0, help="Max file age in hours before re-fetching (default: 24)")
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE, help="Output JSON file path")
    parser.add_argument("--models", help="Comma-separated list of specific model names to fetch")
    parser.add_argument("--skip-tags", action="store_true", help="Only get model names, skip per-model page scraping")
    args = parser.parse_args()

    output = args.output

    if not args.force:
        age = _file_age_hours(output)
        if age is not None and age < args.max_age:
            print(f"Registry file is {age:.1f}h old (< {args.max_age}h). Use --force to re-fetch.")
            return 0

    print("Fetching model list from ollama.com/library ...")
    all_names = get_model_names()
    # Deduplicate while preserving order
    seen = set()
    unique_names = []
    for n in all_names:
        if n not in seen:
            seen.add(n)
            unique_names.append(n)
    all_names = unique_names

    print(f"Found {len(all_names)} models on ollama.com")

    if args.models:
        requested = {m.strip() for m in args.models.split(",")}
        all_names = [n for n in all_names if n in requested]
        missing = requested - set(all_names)
        if missing:
            print(f"Warning: models not found on ollama.com: {', '.join(sorted(missing))}", file=sys.stderr)
        print(f"Filtering to {len(all_names)} requested model(s)")

    models = {}
    if args.skip_tags:
        for name in all_names:
            models[name] = {"tags": []}
    else:
        for i, name in enumerate(all_names):
            print(f"  [{i+1}/{len(all_names)}] Scraping {name} ...", end="", flush=True)
            tags = scrape_model_page(name)
            models[name] = {"tags": tags}
            print(f" {len(tags)} tag(s)")
            if i < len(all_names) - 1:
                time.sleep(FETCH_DELAY)

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))

    total_tags = sum(len(m["tags"]) for m in models.values())
    size_kb = output.stat().st_size / 1024
    print(f"\nSaved {len(models)} models ({total_tags} tags) to {output} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
