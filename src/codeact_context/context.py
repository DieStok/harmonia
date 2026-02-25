"""
True CodeAct Beaker context — bypasses Archytas ReAct.

The LLM writes Python code in markdown fences. Code is extracted and executed
in the Beaker subkernel. No tool schemas, no ReAct prelude, no Archytas.
"""

import os
from pathlib import Path

from beaker_kernel.lib.context import BeakerContext
from .agent import CodeActAgent, CodeActAgentLoop
from prompt_logging import print_prompt_composition, register_prompt_json_logger


class CodeActContext(BeakerContext):
    """
    CodeAct context: LLM writes code naturally, no tool-call framework.

    Key differences from CodeContext:
    - Uses CodeActAgent which overrides react_async() to bypass Archytas
    - Manages its own agent loop via CodeActAgentLoop
    - LLM is called directly via litellm (not through Archytas)
    - No tool schemas injected into the LLM prompt
    """

    SLUG = "codeact_context"
    enabled_subkernels = ["python3"]

    def __init__(self, beaker_kernel, config):
        # Pass CodeActAgent to super().__init__() — the subkernel initializes
        # correctly, but react_async() is overridden to use our CodeAct loop
        super().__init__(beaker_kernel, CodeActAgent, config)

        # Build litellm model string
        model = os.environ.get("LLM_SERVICE_MODEL", "gpt-4o")
        provider = os.environ.get("LLM_SERVICE_PROVIDER", "openai")

        provider_prefixes = {
            "openai": "",           # litellm handles OpenAI natively
            "ollama": "ollama/",
            "anthropic": "anthropic/",
            "openrouter": "openrouter/",
            "groq": "groq/",
            "gemini": "gemini/",
        }
        # Handle compound providers like "litellm:openrouter" or "anyllm:ollama"
        base_provider = provider.split(":")[-1] if ":" in provider else provider
        prefix = provider_prefixes.get(base_provider, f"{base_provider}/")
        litellm_model = f"{prefix}{model}" if prefix else model

        temperature = float(os.environ.get("LLM_TEMPERATURE", "0.0"))
        max_turns = int(os.environ.get("CODEACT_MAX_TURNS", "30"))
        context_strategy = os.environ.get("CODEACT_CONTEXT_STRATEGY", "summarize")

        # Load custom summary template if configured
        summary_template = None
        summary_template_path = os.environ.get("HARMONIA_CODEACT_SUMMARY_TEMPLATE")
        if summary_template_path and Path(summary_template_path).exists():
            summary_template = Path(summary_template_path).read_text()

        # Build the CodeAct agent loop and attach it to the agent
        self.codeact_loop = CodeActAgentLoop(
            model=litellm_model,
            system_prompt="",  # Set in auto_context()
            max_turns=max_turns,
            temperature=temperature,
            context_strategy=context_strategy,
            summary_template=summary_template,
        )
        self.agent.codeact_loop = self.codeact_loop

        # Prompt composition logging
        print_prompt_composition(self.agent, context_slug="codeact_context")
        register_prompt_json_logger(self.agent, context_slug="codeact_context")

    async def auto_context(self):
        """
        Provide the system prompt for the LLM.

        Supports custom prompts via HARMONIA_CODEACT_PROMPT env var.
        Falls back to HARMONIA_CODE_CONTEXT_PROMPT for compatibility.
        Falls back to a default CodeAct prompt.
        """
        custom_prompt_path = (
            os.environ.get("HARMONIA_CODEACT_PROMPT")
            or os.environ.get("HARMONIA_CODE_CONTEXT_PROMPT")
        )
        if custom_prompt_path and Path(custom_prompt_path).exists():
            prompt = Path(custom_prompt_path).read_text()
        else:
            prompt = (
                "You are a data scientist working in a Python environment with a "
                "persistent Jupyter kernel.\n\n"
                "You have access to pandas, numpy, and other data science libraries.\n\n"
                "When you need to do something, write Python code in a ```python code block.\n"
                "I will execute it and show you the output. You can then write more code "
                "based on the results.\n\n"
                "When you are done with the task and want to give a final answer, just "
                "respond with text (no code block).\n\n"
                "Important:\n"
                "- Variables persist between code blocks (this is a persistent kernel session)\n"
                "- Use print() to see output — bare expressions do not display\n"
                "- If you get an error, read the traceback and fix your code\n"
                "- Working directory: use os.getcwd() and os.listdir() to explore"
            )

        # Update the agent loop's system prompt
        self.codeact_loop.system_prompt = prompt

        if not hasattr(self, '_auto_context_logged'):
            print(f"\n{'=' * 80}")
            print(f"AUTO-CONTEXT (domain prompt) -- codeact_context [{len(prompt)} chars]:")
            if custom_prompt_path and Path(custom_prompt_path).exists():
                print(f"[from custom file: {custom_prompt_path}]")
            print(f"{'=' * 80}")
            print(prompt)
            print(f"{'=' * 80}\n")
            self._auto_context_logged = True

        return prompt
