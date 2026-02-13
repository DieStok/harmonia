import os
from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING
from beaker_kernel.lib.context import BeakerContext

from .agent import BDIKitAgent
from .prompts import PromptLoader, get_prompt_loader

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
        # Determine prompts directory from env var (set by generate_env.py)
        prompts_dir_env = os.environ.get("HARMONIA_PROMPTS_DIR")
        if prompts_dir_env and Path(prompts_dir_env).exists():
            self.prompt_loader = PromptLoader(prompts_dir=Path(prompts_dir_env))
            print(f"[Harmonia] Using custom system prompt dir: {prompts_dir_env}")
        else:
            self.prompt_loader = PromptLoader()  # Default

        # Call parent (creates agent with default ReAct prelude)
        super().__init__(beaker_kernel, BDIKitAgent, config)

        # Override ReAct prelude if custom one specified
        react_prelude_path = os.environ.get("HARMONIA_REACT_PRELUDE")
        if react_prelude_path and Path(react_prelude_path).exists():
            custom_prelude = Path(react_prelude_path).read_text()
            self.agent.custom_prelude = custom_prelude
            self.agent.update_prompt()
            print(f"[Harmonia] Using custom ReAct prelude: {react_prelude_path}")

        # Override tool descriptions from Jinja2 templates (if custom dir specified)
        self._override_tool_descriptions()

        # Log the full system prompt for diagnostics
        self._log_prompt_config()

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

    def _log_prompt_config(self):
        """Log the current prompt configuration for diagnostics."""
        import json
        config_info = {
            "prompts_dir": str(self.prompt_loader.prompts_dir),
            "react_prelude_override": os.environ.get("HARMONIA_REACT_PRELUDE", None),
            "tool_prompts_dir_override": os.environ.get("HARMONIA_TOOL_PROMPTS_DIR", None),
            "code_context_prompt_override": os.environ.get("HARMONIA_CODE_CONTEXT_PROMPT", None),
        }
        print(f"[Harmonia] Prompt configuration: {json.dumps(config_info, indent=2)}")

    async def setup(self, context_info=None, parent_header=None):
        await super().setup(context_info, parent_header)

    async def auto_context(self):
        """Generate the system prompt from templates."""
        # Define tools for template
        tools = [
            {"name": "match_schema", "description": "Performs schema mapping between source and target tables"},
            {"name": "top_matches", "description": "Returns top 10 alternative column mappings for evaluation"},
            {"name": "match_values", "description": "Finds value matches between column pairs"},
            {"name": "materialize_mapping", "description": "Creates the final harmonized table"},
            {"name": "get_gdc_acceptable_values", "description": "Lists acceptable values for GDC columns"},
        ]

        system_prompt = self.prompt_loader.get_system_prompt(
            tools=tools,
            suppress_output=True,
        )

        # Print the full system prompt on first call for diagnostics
        if not hasattr(self, '_system_prompt_logged'):
            print(f"[Harmonia] Full system prompt ({len(system_prompt)} chars):")
            print(system_prompt)
            self._system_prompt_logged = True

        return system_prompt
