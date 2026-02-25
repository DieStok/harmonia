"""
CodeAct agent loop — bypasses Archytas entirely.

Calls LLM directly via litellm, extracts code blocks from natural text responses,
executes them via BeakerContext.execute(), and feeds output back as observations.

Contains:
- CodeActAgentLoop: The core LLM conversation loop (no Archytas dependency)
- CodeActAgent: A BeakerAgent subclass that overrides react_async() to use the loop
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

import litellm

from beaker_kernel.lib.agent import BeakerAgent


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Code block extraction
# ---------------------------------------------------------------------------

CODE_BLOCK_PATTERN = re.compile(
    r"```(?:python|py)?\s*\n(.*?)```",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Context window management
# ---------------------------------------------------------------------------

DEFAULT_SUMMARY_TEMPLATE = """\
You have been working on a data harmonization task. Your conversation history
is getting long and needs to be summarized to continue.

Please provide a concise summary of:
1. What task you were given
2. What steps you have completed so far
3. What the current state of the work is (any errors, partial results, etc.)
4. A list of all Python variables currently in the environment and their purpose

Write ONLY the summary, no code blocks. Be specific about file names, column names,
and any mappings you have discovered or created.
"""


def _count_tokens(messages: list[dict], model: str) -> int:
    """Count tokens in a message list using litellm's token counter."""
    try:
        return litellm.token_counter(model=model, messages=messages)
    except Exception:
        # Fallback: rough estimate of 4 chars per token
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4


def _get_model_context_limit(model: str) -> int:
    """Get the context window size for a model via litellm, with fallback."""
    try:
        info = litellm.get_model_info(model=model)
        if info and "max_input_tokens" in info:
            return info["max_input_tokens"]
        if info and "max_tokens" in info:
            return info["max_tokens"]
    except Exception:
        pass
    # Conservative fallback
    return 16_000


def _truncate_middle(history: list[dict], keep_fraction: float = 0.2) -> list[dict]:
    """Keep first and last keep_fraction of messages, drop the middle.

    With keep_fraction=0.2, keeps first 20% and last 20%, dropping middle 60%.
    """
    n = len(history)
    if n <= 4:
        return history

    keep_count = max(2, int(n * keep_fraction))
    head = history[:keep_count]
    tail = history[-keep_count:]
    dropped = n - 2 * keep_count

    separator = {
        "role": "user",
        "content": (
            f"[Context window management: {dropped} messages from the middle of the "
            f"conversation were removed to fit within the context window. The first "
            f"{keep_count} and last {keep_count} messages are preserved.]"
        ),
    }
    return head + [separator] + tail


# ---------------------------------------------------------------------------
# CodeActAgentLoop
# ---------------------------------------------------------------------------

class CodeActAgentLoop:
    """
    A CodeAct agent loop that:
    1. Sends system prompt + conversation history to LLM via litellm
    2. Parses LLM response for ```python ... ``` code blocks
    3. If code found: executes via context.execute(), captures output
    4. Appends output as observation, calls LLM again
    5. If no code found: returns LLM text as final answer
    6. Stops after max_turns iterations

    This is NOT an Archytas agent. It does not use ReActAgent, BeakerAgent,
    tool schemas, or structured tool calls.
    """

    def __init__(
        self,
        model: str,
        system_prompt: str,
        max_turns: int = 30,
        temperature: float = 0.0,
        context_strategy: str = "summarize",
        summary_template: Optional[str] = None,
        context_budget_fraction: float = 0.80,
    ):
        """
        Args:
            model: litellm model string (e.g. "openrouter/mistralai/devstral-small-2505")
            system_prompt: System prompt for the LLM
            max_turns: Maximum number of code-execute cycles before stopping
            temperature: LLM temperature
            context_strategy: "summarize", "truncate", or "none"
            summary_template: Jinja2 or plain text template for summarization prompt
            context_budget_fraction: Use at most this fraction of the context window
                before triggering context management (default 0.80)
        """
        self.model = model
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.temperature = temperature
        self.context_strategy = context_strategy
        self.summary_template = summary_template or DEFAULT_SUMMARY_TEMPLATE
        self.context_budget_fraction = context_budget_fraction
        self.history: list[dict] = []  # OpenAI-format messages

    def reset(self):
        """Clear conversation history for a new task."""
        self.history = []

    def _build_messages(self) -> list[dict]:
        """Build the full message list: system prompt + conversation history."""
        return [
            {"role": "system", "content": self.system_prompt},
            *self.history,
        ]

    async def _manage_context_window(self, execute_fn) -> None:
        """Check if history is approaching context limit and manage it.

        Args:
            execute_fn: async callable(code) -> dict, for running introspection
                code in the kernel when using the summarize strategy.
        """
        if self.context_strategy == "none":
            return

        messages = self._build_messages()
        current_tokens = _count_tokens(messages, self.model)
        limit = _get_model_context_limit(self.model)
        budget = int(limit * self.context_budget_fraction)

        if current_tokens < budget:
            return

        logger.info(
            "Context window management triggered: %d tokens >= %d budget "
            "(limit=%d, strategy=%s)",
            current_tokens, budget, limit, self.context_strategy,
        )

        if self.context_strategy == "truncate":
            self.history = _truncate_middle(self.history)
            return

        if self.context_strategy == "summarize":
            await self._summarize_history(execute_fn)
            return

    async def _summarize_history(self, execute_fn) -> None:
        """Replace conversation history with an LLM-generated summary."""
        # First, get current kernel variable state
        var_listing = ""
        try:
            result = await execute_fn(
                "import sys as _sys\n"
                "_user_vars = {k: type(v).__name__ for k, v in globals().items() "
                "if not k.startswith('_') and k not in _sys.modules}\n"
                "for _k, _t in sorted(_user_vars.items()):\n"
                "    print(f'{_k}: {_t}')\n"
                "del _user_vars, _k, _t"
            )
            var_listing = "".join(result.get("stdout_list", []))
        except Exception:
            var_listing = "[Could not retrieve variable listing]"

        # Build summarization request
        summary_prompt = self.summary_template
        if var_listing.strip():
            summary_prompt += (
                f"\n\nCurrent kernel variables:\n```\n{var_listing.strip()}\n```"
            )

        # Ask LLM to summarize
        summary_messages = [
            {"role": "system", "content": self.system_prompt},
            *self.history,
            {"role": "user", "content": summary_prompt},
        ]

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=summary_messages,
                temperature=0.0,  # Deterministic summary
            )
            summary_text = response.choices[0].message.content or ""
        except Exception as e:
            logger.warning("Summarization LLM call failed: %s. Falling back to truncation.", e)
            self.history = _truncate_middle(self.history)
            return

        # Replace history with summary
        self.history = [
            {
                "role": "user",
                "content": (
                    "[Context window management: The conversation history has been "
                    "summarized to fit within the context window. Below is the summary "
                    "of all previous work.]\n\n" + summary_text
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Understood. I have the summary of our previous work. "
                    "I'll continue from where we left off."
                ),
            },
        ]

    async def run(self, user_message: str, execute_fn, parent_header: dict) -> str:
        """
        Run the CodeAct loop for one user message.

        Args:
            user_message: The user's request.
            execute_fn: async callable(code: str) -> dict
                        (wraps BeakerContext.execute, returns result dict)
            parent_header: Jupyter message parent header for response routing.

        Returns:
            The LLM's final text response (the turn where it produced no code).
        """
        self.history.append({"role": "user", "content": user_message})

        for turn in range(self.max_turns):
            # Manage context window before each LLM call
            await self._manage_context_window(execute_fn)

            # 1. Call LLM
            messages = self._build_messages()
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
            )
            assistant_text = response.choices[0].message.content or ""
            self.history.append({"role": "assistant", "content": assistant_text})

            # 2. Extract code blocks
            code_blocks = CODE_BLOCK_PATTERN.findall(assistant_text)

            if not code_blocks:
                # No code -> LLM is giving final answer
                return assistant_text

            # 3. Execute each code block, collect output
            all_output = []
            for code in code_blocks:
                code = code.strip()
                if not code:
                    continue

                # Execute in subkernel
                result = await execute_fn(code)

                # Collect stdout, stderr, errors
                output_parts = []

                stdout_text = "".join(result.get("stdout_list", []))
                if stdout_text.strip():
                    output_parts.append(stdout_text.strip())

                stderr_text = "".join(result.get("stderr_list", []))
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text.strip()}")

                error_info = result.get("error")
                if error_info:
                    ename = error_info.get("ename", "Error")
                    evalue = error_info.get("evalue", "")
                    tb_lines = error_info.get("traceback", [])
                    tb_text = "\n".join(tb_lines) if tb_lines else f"{ename}: {evalue}"
                    output_parts.append(f"ERROR:\n{tb_text}")

                return_val = result.get("return")
                if return_val is not None:
                    output_parts.append(f"Return value: {return_val}")

                if output_parts:
                    all_output.append("\n".join(output_parts))
                else:
                    all_output.append("[Code executed successfully with no output]")

            # 4. Append observation to history
            observation = "\n---\n".join(all_output)
            self.history.append({
                "role": "user",
                "content": f"[Execution output]\n{observation}",
            })

        # Max turns reached
        return (
            f"[CodeAct agent reached maximum of {self.max_turns} turns "
            f"without completing the task]"
        )


# ---------------------------------------------------------------------------
# CodeActAgent (BeakerAgent subclass)
# ---------------------------------------------------------------------------

class CodeActAgent(BeakerAgent):
    """
    BeakerAgent subclass that overrides react_async() to run the CodeAct loop
    instead of Archytas' ReAct loop.

    The Beaker kernel dispatches LLM requests via:
        self.context.agent.react_async(request, react_context={"message": message})

    By overriding react_async(), we intercept this dispatch and route it through
    CodeActAgentLoop instead of Archytas.
    """

    # Will be set by CodeActContext after construction
    codeact_loop: Optional[CodeActAgentLoop] = None

    async def react_async(self, query: str, react_context: dict = None) -> str:
        """
        Override Archytas react_async to run the CodeAct loop.

        Args:
            query: The user's message text.
            react_context: Dict with "message" key containing the JupyterMessage.

        Returns:
            The LLM's final text response.
        """
        if self.codeact_loop is None:
            raise RuntimeError(
                "CodeActAgent.codeact_loop is not set. "
                "CodeActContext must assign it after construction."
            )

        # Extract parent header for message routing
        parent_header = {}
        if react_context and "message" in react_context:
            parent_header = react_context["message"].header

        # Create execute_fn that wraps context.execute() and awaits the task
        async def execute_fn(code: str) -> dict:
            task = self.context.execute(code, parent_header=parent_header)
            return await task

        result = await self.codeact_loop.run(
            user_message=query,
            execute_fn=execute_fn,
            parent_header=parent_header,
        )

        return result
