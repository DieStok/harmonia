import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from beaker_kernel.lib.context import BeakerContext
from openrouter_hardening import apply_openrouter_hardening
from prompt_logging import print_prompt_composition, register_prompt_json_logger

from .agent import BDIKitAgent
from .prompts import PromptLoader

if TYPE_CHECKING:
    from beaker_kernel.kernel import BeakerKernel


class BDIKitContext(BeakerContext):
    """
    Beaker context for BDIKit data harmonization.

    Provides system prompts and manages the data harmonization workflow.
    Supports per-experiment prompt overrides via environment variables:
      - HARMONIA_PROMPTS_DIR: custom directory for system prompt templates
      - HARMONIA_REACT_PRELUDE: path to custom ReAct agent prelude text file
      - HARMONIA_TOOL_PROMPTS_DIR: custom directory for tool description templates
    """

    enabled_subkernels = ["python3"]

    SLUG = "bdikit_context"

    def __init__(self, beaker_kernel: "BeakerKernel", config: Dict[str, Any]):
        # NOTE: This patch only applies to native Archytas OpenRouterModel (provider: openrouter
        # without litellm: prefix). Has no effect on the litellm:openrouter code path.
        apply_openrouter_hardening()
        # Determine prompts directory from env var (set by generate_env.py)
        prompts_dir_env = os.environ.get("HARMONIA_PROMPTS_DIR")
        if prompts_dir_env and Path(prompts_dir_env).exists():
            self.prompt_loader = PromptLoader(prompts_dir=Path(prompts_dir_env))
            print(f"[Harmonia] Using custom system prompt dir: {prompts_dir_env}")
        else:
            self.prompt_loader = PromptLoader()  # Default

        # Call parent (creates agent with default ReAct prelude)
        super().__init__(beaker_kernel, BDIKitAgent, config)

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
        _max_consecutive = os.environ.get("ARCHYTAS_MAX_CONSECUTIVE_TOOL_ERRORS")
        if _max_consecutive:
            self.agent.max_consecutive_tool_errors = int(_max_consecutive)
            print(f"  [HarmoniaConfig] max_consecutive_tool_errors = {self.agent.max_consecutive_tool_errors}")
        # NOTE: context_window_override, tool_output_summarization_threshold,
        # tool_output_snippet_size, summarization_model are not exposed in the
        # installed Archytas ReActAgent API and remain informational in the YAML config.

        # Override ReAct prelude if custom one specified
        react_prelude_path = os.environ.get("HARMONIA_REACT_PRELUDE")
        if react_prelude_path and Path(react_prelude_path).exists():
            custom_prelude = Path(react_prelude_path).read_text()
            self.agent.custom_prelude = custom_prelude
            self.agent.update_prompt()
            print(f"[Harmonia] Using custom ReAct prelude: {react_prelude_path}")

        # Override tool descriptions from Jinja2 templates (if custom dir specified)
        self._override_tool_descriptions()

        # Prompt composition logging (replaces _log_prompt_config)
        print_prompt_composition(self.agent, context_slug="bdikit_context")
        register_prompt_json_logger(self.agent, context_slug="bdikit_context")

    def _override_tool_descriptions(self):
        """Replace tool descriptions on StructuredTool objects with rendered Jinja2 templates.

        Uses HARMONIA_TOOL_PROMPTS_DIR env var for a custom tool prompts directory,
        or falls back to the current prompt_loader's tools/ directory.
        Only overrides tools for which a .j2 template exists.
        """
        tool_prompts_dir = os.environ.get("HARMONIA_TOOL_PROMPTS_DIR")
        if tool_prompts_dir and Path(tool_prompts_dir).exists():
            tool_loader = PromptLoader(prompts_dir=Path(tool_prompts_dir))
            print(f"[Harmonia] Using custom tool prompts dir: {tool_prompts_dir}")
        else:
            tool_loader = self.prompt_loader

        if not hasattr(self.agent, 'model') or not hasattr(self.agent.model, 'lc_tools'):
            return

        available_templates = tool_loader.list_tools()
        if not available_templates:
            return

        for lc_tool in self.agent.model.lc_tools:
            if lc_tool.name in available_templates:
                try:
                    new_desc = tool_loader.get_tool_description(lc_tool.name)
                    if new_desc and new_desc.strip():
                        lc_tool.description = new_desc
                        print(f"[Harmonia] Overrode tool description: {lc_tool.name}")
                except Exception as e:
                    print(f"[Harmonia] Warning: Could not load tool template for {lc_tool.name}: {e}")

    async def setup(self, context_info=None, parent_header=None):
        await super().setup(context_info, parent_header)

    async def auto_context(self):
        """Generate the system prompt from templates."""
        # Define tools for template
        tools = [
            {"name": "match_schema", "description": "Performs schema matching between source and target tables"},
            {"name": "rank_schema_matches", "description": "Returns top-k alternative column mappings for a given attribute"},
            {"name": "match_values", "description": "Finds value mappings between matched column pairs"},
            {"name": "materialize_mapping", "description": "Creates the final harmonized table"},
            {"name": "get_gdc_acceptable_values", "description": "Lists acceptable values for GDC attributes"},
        ]

        system_prompt = self.prompt_loader.get_system_prompt(
            tools=tools,
            suppress_output=True,
        )

        # Print the domain prompt on first call (completes Output A from prompt_logging)
        if not hasattr(self, '_auto_context_logged'):
            print(f"\n{'=' * 80}")
            print(f"AUTO-CONTEXT (domain prompt) — bdikit_context [{len(system_prompt)} chars]:")
            print(f"{'=' * 80}")
            print(system_prompt)
            print(f"{'=' * 80}\n")
            self._auto_context_logged = True

        return system_prompt
