from __future__ import annotations

import json
from pathlib import Path


def write_manifest(out_dir: Path, payload: dict):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(payload, indent=2))
