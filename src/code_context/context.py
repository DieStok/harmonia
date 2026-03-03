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
from typing import TYPE_CHECKING

from beaker_kernel.lib.context import BeakerContext
from openrouter_hardening import apply_openrouter_hardening
from prompt_logging import print_prompt_composition, register_prompt_json_logger

from .agent import CodeAgent

if TYPE_CHECKING:
    pass


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
        # NOTE: This patch only applies to native Archytas OpenRouterModel (provider: openrouter
        # without litellm: prefix). Has no effect on the litellm:openrouter code path.
        apply_openrouter_hardening()
        super().__init__(beaker_kernel, CodeAgent, config)

        # Wire ArchytasContextConfig -> Archytas agent (max_react_steps, max_errors)
        # BeakerContext creates the agent internally without forwarding kwargs, so we patch
        # the instance attributes directly after construction. These are plain int attributes
        # on ReActAgent (react.py lines 234-235) checked per-task in the react loop.
        _max_react_steps = os.environ.get("ARCHYTAS_MAX_REACT_STEPS")
        _max_errors = os.environ.get("ARCHYTAS_MAX_ERRORS")
        if _max_react_steps:
            self.agent.max_react_steps = int(_max_react_steps)
            print(f"  [HarmoniaConfig] max_react_steps = {self.agent.max_react_steps}")
        if _max_errors:
            self.agent.max_errors = int(_max_errors)
            print(f"  [HarmoniaConfig] max_errors = {self.agent.max_errors}")
        # NOTE: context_window_override, tool_output_summarization_threshold,
        # tool_output_snippet_size, summarization_model are not exposed in the
        # installed Archytas ReActAgent API and remain informational in the YAML config.

        # Prompt composition logging
        print_prompt_composition(self.agent, context_slug="code_context")
        register_prompt_json_logger(self.agent, context_slug="code_context")

    async def auto_context(self):
        """
        Provide the system prompt for the LLM.

        Priority:
        1. HARMONIA_CODE_CONTEXT_PROMPT env var (custom file path)
        2. Built-in v1 prompt file (src/code_context/prompts/v1/system.txt)
        3. Hardcoded fallback (should never be needed)
        """
        custom_prompt_path = os.environ.get("HARMONIA_CODE_CONTEXT_PROMPT")
        if custom_prompt_path and Path(custom_prompt_path).exists():
            prompt = Path(custom_prompt_path).read_text()
            source = f"custom file: {custom_prompt_path}"
        else:
            # Load from built-in v1 prompt file
            default_prompt_file = Path(__file__).parent / "prompts" / "v1" / "system.txt"
            if default_prompt_file.exists():
                prompt = default_prompt_file.read_text()
                source = f"built-in: {default_prompt_file}"
            else:
                # Hardcoded fallback (should never be reached)
                prompt = (
                    "You are a Python code execution assistant running in a "
                    "Jupyter-like environment.\n\n"
                    "You can write and execute Python code. Common data science "
                    "libraries are available (pandas, numpy, etc.).\n\n"
                    "When asked to do something, write Python code to accomplish it."
                )
                source = "hardcoded fallback"

        if not hasattr(self, '_auto_context_logged'):
            print(f"\n{'=' * 80}")
            print(f"AUTO-CONTEXT (domain prompt) -- code_context [{len(prompt)} chars]:")
            print(f"[source: {source}]")
            print(f"{'=' * 80}")
            print(prompt)
            print(f"{'=' * 80}\n")
            self._auto_context_logged = True

        return prompt
