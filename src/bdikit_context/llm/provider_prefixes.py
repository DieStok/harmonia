"""
Shared litellm provider prefix mapping for all Harmonia contexts.

Maps Harmonia provider names to litellm model string prefixes.
See: https://docs.litellm.ai/docs/providers

Import this from any context or agent module that needs to build litellm model strings.
"""

LITELLM_PROVIDER_PREFIX = {
    "ollama": "ollama_chat",    # ollama_chat/ for chat completions
    "openai": None,             # No prefix needed for OpenAI
    "openrouter": "openrouter",
    "anthropic": "anthropic",
    "azure": "azure",
    "azureopenai": "azure",
    "bedrock": "bedrock",
    "gemini": "gemini",
    "groq": "groq",
    "mistral": "mistral",
    "together": "together_ai",
    "perplexity": "perplexity",
    "cohere": "cohere_chat",
    "deepseek": "deepseek",
    "fireworks": "fireworks_ai",
}
