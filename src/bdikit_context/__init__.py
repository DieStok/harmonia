"""
BDIKit Context - Data Harmonization Agent for Beaker

Supports multiple LLM providers: OpenAI, OpenRouter, Anthropic, Ollama, etc.
"""

from .llm import configure_llm_environment

# Configure LLM environment on package import
configure_llm_environment()

# Reset beaker-kernel config to pick up the new environment variables
# This is needed because beaker's config is a lazy-loaded singleton that may
# have been instantiated before this module was imported
try:
    from beaker_kernel.lib.config import reset_config
    reset_config()
except ImportError:
    pass  # beaker_kernel not installed, skip
