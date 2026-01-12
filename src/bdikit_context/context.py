from typing import Dict, Any, TYPE_CHECKING
from beaker_kernel.lib.context import BeakerContext

from .agent import BDIKitAgent
from .prompts import get_prompt_loader

if TYPE_CHECKING:
    from beaker_kernel.kernel import BeakerKernel


class BDIKitContext(BeakerContext):
    """
    Beaker context for BDIKit data harmonization.

    Provides system prompts and manages the data harmonization workflow.
    """

    enabled_subkernels = ["python3"]

    SLUG = "bdikit_context"

    def __init__(self, beaker_kernel: "BeakerKernel", config: Dict[str, Any]):
        super().__init__(beaker_kernel, BDIKitAgent, config)
        self.prompt_loader = get_prompt_loader()

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

        return self.prompt_loader.get_system_prompt(
            tools=tools,
            suppress_output=True,
        )
