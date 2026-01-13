"""
LLM provider configuration for Harmonia.

Sets up environment variables that Beaker/Archytas expects.
"""

import os
from typing import Optional
from ..config import get_config


# Map provider names to Archytas import paths
PROVIDER_IMPORT_MAP = {
    "openai": "archytas.models.openai.OpenAIModel",
    "ollama": "archytas.models.ollama.OllamaModel",
    "openrouter": "archytas.models.openrouter.OpenRouterModel",
    "anthropic": "archytas.models.anthropic.AnthropicModel",
    "azure": "archytas.models.azure.AzureOpenAIModel",
    "bedrock": "archytas.models.bedrock.BedrockModel",
    "gemini": "archytas.models.gemini.GeminiModel",
    "groq": "archytas.models.groq.GroqModel",
}

# Map provider names to their API key environment variable names
PROVIDER_API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "ollama": None,
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "gemini": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
}


def configure_llm_environment():
    """
    Configure environment variables for Beaker/Archytas LLM integration.

    This function reads from Harmonia's config and sets the environment
    variables that Beaker expects for LLM provider configuration.
    """
    config = get_config()
    llm = config.llm

    # Set provider import path - use direct assignment to override beaker defaults
    import_path = PROVIDER_IMPORT_MAP.get(llm.provider.lower())
    if import_path:
        os.environ["LLM_PROVIDER_IMPORT_PATH"] = import_path

    # Set model name - use direct assignment to override beaker defaults
    os.environ["LLM_SERVICE_MODEL"] = llm.model

    # Set API key if provided - use direct assignment to override beaker defaults
    if llm.api_key:
        os.environ["LLM_SERVICE_TOKEN"] = llm.api_key

        # Also set provider-specific env var for compatibility
        env_var = PROVIDER_API_KEY_ENV.get(llm.provider.lower())
        if env_var:
            os.environ[env_var] = llm.api_key

    # Set base URL for custom endpoints (Ollama, proxies, etc.)
    if llm.base_url:
        os.environ.setdefault("LLM_BASE_URL", llm.base_url)

        # Provider-specific base URL handling
        if llm.provider.lower() == "ollama":
            os.environ.setdefault("OLLAMA_HOST", llm.base_url)


def get_provider_info() -> dict:
    """Get current provider configuration info (for debugging)."""
    config = get_config()
    return {
        "provider": config.llm.provider,
        "model": config.llm.model,
        "base_url": config.llm.base_url,
        "has_api_key": config.llm.api_key is not None,
        "import_path": PROVIDER_IMPORT_MAP.get(config.llm.provider.lower()),
    }
