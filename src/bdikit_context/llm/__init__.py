"""
LLM provider configuration for Harmonia.

Sets up environment variables that Beaker/Archytas expects.

Supports two modes:
1. Native Archytas providers (legacy): "openai", "ollama", etc.
2. any-llm unified providers (new): "anyllm:openai", "anyllm:ollama", etc.

The any-llm providers use the unified any-llm library for LLM communication,
enabling support for 30+ providers with a consistent interface.
"""

import os
from typing import Optional
from ..config import get_config


# Map provider names to Archytas import paths
PROVIDER_IMPORT_MAP = {
    # Native Archytas providers (legacy)
    "openai": "archytas.models.openai.OpenAIModel",
    "ollama": "archytas.models.ollama.OllamaModel",
    "openrouter": "archytas.models.openrouter.OpenRouterModel",
    "anthropic": "archytas.models.anthropic.AnthropicModel",
    "azure": "archytas.models.azure.AzureOpenAIModel",
    "bedrock": "archytas.models.bedrock.BedrockModel",
    "gemini": "archytas.models.gemini.GeminiModel",
    "groq": "archytas.models.groq.GroqModel",

    # any-llm unified providers (new - use "anyllm:" prefix or just "anyllm")
    "anyllm": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:openai": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:ollama": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:anthropic": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:openrouter": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:mistral": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:groq": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:together": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:perplexity": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:bedrock": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:azure": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:cohere": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:deepseek": "bdikit_context.llm.anyllm.AnyLLMModel",
    "anyllm:fireworks": "bdikit_context.llm.anyllm.AnyLLMModel",
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

    Supports both native Archytas providers and any-llm unified providers:
    - Native: "openai", "ollama", etc. (uses archytas.models.*)
    - any-llm: "anyllm:openai", "anyllm:ollama", etc. (uses bdikit_context.llm.anyllm)
    """
    config = get_config()
    llm = config.llm

    provider_key = llm.provider.lower()

    # Handle any-llm providers: extract actual provider for env vars
    if provider_key.startswith("anyllm:"):
        actual_provider = provider_key.split(":", 1)[1]
        os.environ["LLM_SERVICE_PROVIDER"] = actual_provider
        import_path = PROVIDER_IMPORT_MAP.get(provider_key) or PROVIDER_IMPORT_MAP.get("anyllm")
    elif provider_key == "anyllm":
        # Generic any-llm - provider will be determined by LLM_SERVICE_PROVIDER env var
        actual_provider = os.getenv("LLM_SERVICE_PROVIDER", "openai")
        import_path = PROVIDER_IMPORT_MAP.get("anyllm")
    else:
        actual_provider = provider_key
        import_path = PROVIDER_IMPORT_MAP.get(provider_key)

    # Set provider import path - use direct assignment to override beaker defaults
    if import_path:
        os.environ["LLM_PROVIDER_IMPORT_PATH"] = import_path

    # Set model name - use direct assignment to override beaker defaults
    os.environ["LLM_SERVICE_MODEL"] = llm.model

    # Set API key if provided - use direct assignment to override beaker defaults
    if llm.api_key:
        os.environ["LLM_SERVICE_TOKEN"] = llm.api_key

        # Also set provider-specific env var for compatibility
        env_var = PROVIDER_API_KEY_ENV.get(actual_provider)
        if env_var:
            os.environ[env_var] = llm.api_key

    # Set base URL for custom endpoints (Ollama, proxies, etc.)
    if llm.base_url:
        os.environ.setdefault("LLM_BASE_URL", llm.base_url)

        # Provider-specific base URL handling
        if actual_provider == "ollama":
            os.environ.setdefault("OLLAMA_HOST", llm.base_url)


def get_provider_info() -> dict:
    """Get current provider configuration info (for debugging)."""
    config = get_config()
    provider_key = config.llm.provider.lower()

    # Handle any-llm provider format
    if provider_key.startswith("anyllm:"):
        actual_provider = provider_key.split(":", 1)[1]
        is_anyllm = True
    elif provider_key == "anyllm":
        actual_provider = os.getenv("LLM_SERVICE_PROVIDER", "openai")
        is_anyllm = True
    else:
        actual_provider = provider_key
        is_anyllm = False

    return {
        "provider": config.llm.provider,
        "actual_provider": actual_provider,
        "is_anyllm": is_anyllm,
        "model": config.llm.model,
        "base_url": config.llm.base_url,
        "has_api_key": config.llm.api_key is not None,
        "import_path": PROVIDER_IMPORT_MAP.get(provider_key) or PROVIDER_IMPORT_MAP.get("anyllm"),
    }
