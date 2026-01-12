"""
BDIKit Context - Data Harmonization Agent for Beaker

Supports multiple LLM providers: OpenAI, OpenRouter, Anthropic, Ollama, etc.
"""

from .llm import configure_llm_environment

# Configure LLM environment on package import
configure_llm_environment()
