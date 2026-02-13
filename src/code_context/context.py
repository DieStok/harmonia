"""
Minimal code-only Beaker context.

This context provides:
- A single write_code tool for executing Python code
- A simple system prompt for code assistance
- No domain-specific tooling (unlike bdikit_context)

Supports custom prompts via HARMONIA_CODE_CONTEXT_PROMPT env var.
"""

import os
from pathlib import Path

from beaker_kernel.lib.context import BeakerContext
from .agent import CodeAgent


class CodeContext(BeakerContext):
    """
    Minimal context that allows LLM to write and execute Python code.

    This demonstrates the minimum requirements for a working Beaker context:
    1. SLUG class variable (required for context discovery)
    2. auto_context() method (required for LLM system prompt)
    3. Passing an agent class to super().__init__()
    """

    SLUG = "code_context"
    enabled_subkernels = ["python3"]

    def __init__(self, beaker_kernel, config):
        """Initialize with the CodeAgent."""
        super().__init__(beaker_kernel, CodeAgent, config)

    async def auto_context(self):
        """
        Provide the system prompt for the LLM.

        This is THE critical method that makes a context work.
        Without this, the LLM has no instructions and communication fails.

        If HARMONIA_CODE_CONTEXT_PROMPT env var is set and points to a file,
        loads the prompt from that file instead of using the default.
        """
        custom_prompt_path = os.environ.get("HARMONIA_CODE_CONTEXT_PROMPT")
        if custom_prompt_path and Path(custom_prompt_path).exists():
            prompt = Path(custom_prompt_path).read_text()
            print(f"[Harmonia] Using custom code context prompt: {custom_prompt_path}")
            return prompt

        return f"""You are a Python code execution assistant running in a Jupyter-like environment.

## Your Capabilities
- You can write and execute Python code
- You have access to a {self.subkernel.DISPLAY_NAME} kernel
- Common data science libraries are available (pandas, numpy, etc.)

## Environment
- Working directory: Use `os.getcwd()` to check
- Available directories can be listed with `os.listdir()`

## Instructions
1. When asked to do something, write Python code to accomplish it
2. Execute the code to show results
3. Be concise in explanations
4. If you encounter errors, debug and fix them

## Code Execution
To execute code, use the code execution tool. The output will be shown to the user.
"""
