"""
True CodeAct context for Beaker — bypasses Archytas ReAct entirely.

The LLM writes Python code in markdown fences. Code is extracted and executed
in the Beaker subkernel. No tool schemas, no ReAct prelude, no Archytas agent loop.
"""

from .context import CodeActContext

__all__ = ["CodeActContext"]
