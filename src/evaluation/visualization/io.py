from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RUN_ID_PATTERN = re.compile(r"_([0-9a-f]{8})$")


def discover_metrics_files(metrics_files: list[str] | None = None, metrics_globs: list[str] | None = None) -> list[Path]:
    paths: set[Path] = set()
    for item in metrics_files or []:
        p = Path(item).expanduser()
        if p.is_file() and p.name == "metrics.json":
            paths.add(p.resolve())
        elif p.is_dir():
            candidate = p / "metrics.json"
            if candidate.exists():
                paths.add(candidate.resolve())
    for pattern in metrics_globs or []:
        for p in Path().glob(pattern):
            if p.is_file() and p.name == "metrics.json":
                paths.add(p.resolve())
    return sorted(paths)


def extract_run_id(path: Path, data: dict[str, Any]) -> str:
    experiment_name = data.get("metadata", {}).get("experiment_name", "")
    m = RUN_ID_PATTERN.search(experiment_name)
    if m:
        return m.group(1)
    parent = path.parent.name
    m = RUN_ID_PATTERN.search(parent)
    return m.group(1) if m else parent


def load_metrics_bundle(paths: list[Path]) -> tuple[list[tuple[Path, dict[str, Any]]], list[dict[str, str]]]:
    loaded: list[tuple[Path, dict[str, Any]]] = []
    skipped: list[dict[str, str]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text())
            if "column_mapping" not in data or "column_values" not in data or "overall_summary" not in data:
                skipped.append({"file": str(path), "reason": "missing required keys"})
                continue
            loaded.append((path, data))
        except Exception as exc:
            skipped.append({"file": str(path), "reason": str(exc)})
    return loaded, skipped
