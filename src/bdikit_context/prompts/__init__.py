"""
Prompt template loading and rendering.

Uses Jinja2 for template rendering with support for:
- Variable substitution
- Conditional blocks
- Template inheritance
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound


class PromptLoader:
    """Loads and renders Jinja2 prompt templates."""

    def __init__(self, prompts_dir: Optional[Path] = None):
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent

        self.prompts_dir = Path(prompts_dir)
        self.env = Environment(
            loader=FileSystemLoader(self.prompts_dir),
            autoescape=select_autoescape(default=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, **kwargs) -> str:
        """Render a prompt template with given variables."""
        template = self.env.get_template(template_name)
        return template.render(**kwargs).strip()

    def get_system_prompt(self, **kwargs) -> str:
        """Get the main system prompt."""
        return self.render("system/main.j2", **kwargs)

    def get_tool_description(self, tool_name: str, **kwargs) -> str:
        """Get description for a specific tool."""
        try:
            return self.render(f"tools/{tool_name}.j2", **kwargs)
        except TemplateNotFound:
            # Fall back to empty string if template not found
            return ""

    def list_tools(self) -> List[str]:
        """List available tool templates."""
        tools_dir = self.prompts_dir / "tools"
        if not tools_dir.exists():
            return []
        return [f.stem for f in tools_dir.glob("*.j2")]


# Global prompt loader instance
_loader: Optional[PromptLoader] = None


def get_prompt_loader(prompts_dir: Optional[Path] = None) -> PromptLoader:
    """Get the global prompt loader instance."""
    global _loader
    if _loader is None or prompts_dir is not None:
        _loader = PromptLoader(prompts_dir)
    return _loader
