"""
LLM provider configuration for Harmonia.

Sets up environment variables that Beaker/Archytas expects.

Supports three modes:
1. Native Archytas providers (legacy): "openai", "ollama", etc.
2. litellm unified providers (preferred): "litellm:openai", "litellm:ollama", etc.
3. any-llm prefix (backwards compatible): "anyllm:openai", "anyllm:ollama", etc.
   (maps to litellm under the hood)

The litellm providers use the litellm library for LLM communication,
enabling support for 100+ providers with a consistent interface.
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

    # litellm unified providers (preferred — use "litellm:" prefix)
    "litellm": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:openai": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:ollama": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:anthropic": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:openrouter": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:mistral": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:groq": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:together": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:perplexity": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:bedrock": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:azure": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:cohere": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:deepseek": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:fireworks": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "litellm:gemini": "bdikit_context.llm.litellm_model.LiteLLMModel",

    # Backwards compatibility: anyllm: prefix still works (maps to litellm)
    "anyllm": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:openai": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:ollama": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:anthropic": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:openrouter": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:mistral": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:groq": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:together": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:perplexity": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:bedrock": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:azure": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:cohere": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:deepseek": "bdikit_context.llm.litellm_model.LiteLLMModel",
    "anyllm:fireworks": "bdikit_context.llm.litellm_model.LiteLLMModel",
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

    Supports native Archytas providers, litellm unified providers, and
    backwards-compatible anyllm: prefixed providers:
    - Native: "openai", "ollama", etc. (uses archytas.models.*)
    - litellm: "litellm:openai", "litellm:ollama", etc. (uses bdikit_context.llm.litellm_model)
    - anyllm: "anyllm:openai", "anyllm:ollama", etc. (backwards compatible, maps to litellm)
    """
    config = get_config()
    llm = config.llm

    provider_key = llm.provider.lower()

    # Handle litellm: or anyllm: prefixed providers
    if provider_key.startswith("litellm:") or provider_key.startswith("anyllm:"):
        actual_provider = provider_key.split(":", 1)[1]
        os.environ["LLM_SERVICE_PROVIDER"] = actual_provider
        import_path = PROVIDER_IMPORT_MAP.get(provider_key) or PROVIDER_IMPORT_MAP.get("litellm")
    elif provider_key in ("litellm", "anyllm"):
        # Generic litellm/anyllm - provider will be determined by LLM_SERVICE_PROVIDER env var
        actual_provider = os.getenv("LLM_SERVICE_PROVIDER", "openai")
        import_path = PROVIDER_IMPORT_MAP.get("litellm")
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

    # Handle litellm: or anyllm: provider format
    if provider_key.startswith("litellm:") or provider_key.startswith("anyllm:"):
        actual_provider = provider_key.split(":", 1)[1]
        is_litellm = True
    elif provider_key in ("litellm", "anyllm"):
        actual_provider = os.getenv("LLM_SERVICE_PROVIDER", "openai")
        is_litellm = True
    else:
        actual_provider = provider_key
        is_litellm = False

    return {
        "provider": config.llm.provider,
        "actual_provider": actual_provider,
        "is_litellm": is_litellm,
        "model": config.llm.model,
        "base_url": config.llm.base_url,
        "has_api_key": config.llm.api_key is not None,
        "import_path": PROVIDER_IMPORT_MAP.get(provider_key) or PROVIDER_IMPORT_MAP.get("litellm"),
    }
