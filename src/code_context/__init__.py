"""
Minimal code-only context for Beaker.

This context provides a simple write_code tool and lets the LLM
execute Python code without domain-specific tooling.
"""

from .context import CodeContext

__all__ = ["CodeContext"]
