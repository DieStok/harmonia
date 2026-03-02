"""
Runtime hardening for Archytas OpenRouter adapter behavior.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any


def _extract_openrouter_error_payload(text: str) -> dict[str, Any] | None:
    m = re.search(r"Error from OpenRouter:\s*(\{.*\})", text, re.DOTALL)
    if not m:
        return None
    try:
        parsed = ast.literal_eval(m.group(1))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _log_error_metadata(exc: Exception) -> None:
    payload = _extract_openrouter_error_payload(str(exc))
    if not payload:
        return
    error = payload.get("error", {})
    metadata = error.get("metadata")
    if metadata is None:
        return
    try:
        metadata_text = json.dumps(metadata, ensure_ascii=False)
    except Exception:
        metadata_text = str(metadata)
    print(f"[Harmonia] OpenRouter error.metadata: {metadata_text[:3000]}")

    if isinstance(metadata, dict) and "raw" in metadata:
        try:
            raw_text = json.dumps(metadata["raw"], ensure_ascii=False)
        except Exception:
            raw_text = str(metadata["raw"])
        print(f"[Harmonia] OpenRouter provider raw payload: {raw_text[:3000]}")


def apply_openrouter_hardening() -> None:
    """
    Monkey-patch OpenRouterModel.invoke to:
    1) log OpenRouter error metadata/raw payload when present
    2) coerce null-thought AIMessage validation failures to empty content
    """
    try:
        from archytas.models.openrouter import OpenRouterModel
        from langchain_core.messages import AIMessage
    except Exception:
        return

    if getattr(OpenRouterModel, "_harmonia_hardened", False):
        return

    original_invoke = OpenRouterModel.invoke

    def hardened_invoke(self, input, *args, **kwargs):
        try:
            return original_invoke(self, input, *args, **kwargs)
        except Exception as exc:
            _log_error_metadata(exc)
            text = str(exc)
            if "validation errors for AIMessage" in text and "input_value=None" in text:
                print("[Harmonia] OpenRouter returned null thought; coercing to empty AIMessage content.")
                return AIMessage(content="")
            raise

    OpenRouterModel.invoke = hardened_invoke
    OpenRouterModel._harmonia_hardened = True
