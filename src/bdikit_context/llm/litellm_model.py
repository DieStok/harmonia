"""
litellm adapter for Archytas/Beaker integration.

This module provides an Archytas-compatible model that uses the litellm library
for LLM communication, enabling support for 100+ providers with a unified interface.

Usage:
    Set LLM_SERVICE_PROVIDER to "litellm:ollama", "litellm:openai", etc.
    The adapter will be automatically loaded by Beaker via LLM_PROVIDER_IMPORT_PATH.
"""

import asyncio
import json
import logging
import os
from functools import lru_cache
from typing import Any, Optional, Sequence

import litellm
from archytas.exceptions import AuthenticationError
from archytas.models.base import BaseArchytasModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import ToolCall as LangChainToolCall
from litellm import acompletion, token_counter

from .provider_prefixes import LITELLM_PROVIDER_PREFIX

logger = logging.getLogger(__name__)


# Provider to API key environment variable mapping
PROVIDER_API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "ollama": None,  # No API key needed
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "azureopenai": "AZURE_OPENAI_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "gemini": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
    "perplexity": "PERPLEXITYAI_API_KEY",
    "cohere": "COHERE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
}


def to_langchain_tool_call(tool_call: dict) -> LangChainToolCall:
    """Convert litellm/OpenAI tool call to LangChain format."""
    return LangChainToolCall(
        name=tool_call['function']['name'],
        args=json.loads(tool_call['function']['arguments'] or '{}'),
        id=tool_call['id'],
        type="tool_call"
    )


def to_openai_tool_call(tool_call: LangChainToolCall) -> dict:
    """Convert LangChain tool call to OpenAI format (used by litellm)."""
    return {
        "id": tool_call.get('id', ''),
        "type": "function",
        "function": {
            "name": tool_call["name"],
            "arguments": json.dumps(tool_call["args"])
        }
    }


class ChatLiteLLM:
    """
    Minimal adapter that emulates a LangChain-like chat model interface
    over litellm's unified API.

    This class provides the interface expected by Archytas (invoke, ainvoke,
    bind_tools, get_num_tokens_from_messages) while using litellm for the
    actual LLM communication.
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._tools: Optional[Sequence[Any]] = None
        self._tool_schemas: Optional[list[dict]] = None

        # Construct litellm model string
        self._litellm_model = self._build_model_string()
        logger.info(f"Creating ChatLiteLLM: provider={provider}, model={model}, "
                     f"litellm_model={self._litellm_model}, api_base={api_base}")

    def _build_model_string(self) -> str:
        """
        Build litellm model string from provider + model.

        litellm uses a "provider/model" format. See:
        https://docs.litellm.ai/docs/providers

        Examples:
            ollama + devstral:latest -> ollama_chat/devstral:latest
            openai + gpt-4o -> gpt-4o
            openrouter + mistralai/devstral -> openrouter/mistralai/devstral
            anthropic + claude-sonnet-4-5-20250929 -> anthropic/claude-sonnet-4-5-20250929
        """
        prefix = LITELLM_PROVIDER_PREFIX.get(self.provider)
        if prefix is None:
            # No prefix needed (e.g., OpenAI)
            return self.model
        return f"{prefix}/{self.model}"

    def bind_tools(self, tools: Sequence[Any]) -> "ChatLiteLLM":
        """Bind LangChain StructuredTools to the model for tool calling."""
        self._tools = tools
        self._tool_schemas = []

        for tool in tools:
            langchain_schema: dict = tool.tool_call_schema.schema()
            schema = {
                'type': 'function',
                'function': {
                    'name': tool.name,
                    'description': tool.description,
                    'parameters': {
                        'type': 'object',
                        'properties': langchain_schema.get('properties', {}),
                        'required': langchain_schema.get('required', [])
                    },
                }
            }
            self._tool_schemas.append(schema)
            logger.debug(f"Bound tool: {tool.name}")

        return self

    def _convert_messages(self, messages: list[BaseMessage]) -> list[dict[str, Any]]:
        """Convert LangChain messages to OpenAI/litellm format."""

        def serialize_content(content: Any) -> str:
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text" and "text" in item:
                        parts.append(item["text"])
                    else:
                        parts.append(json.dumps(item))
                return "\n".join(parts)
            return json.dumps(content)

        converted: list[dict[str, Any]] = []
        for msg in messages:
            content = serialize_content(msg.content)

            if isinstance(msg, HumanMessage):
                converted.append({"role": "user", "content": content})
            elif isinstance(msg, AIMessage):
                tool_calls = getattr(msg, 'tool_calls', None)
                if tool_calls:
                    converted.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [to_openai_tool_call(tc) for tc in tool_calls]
                    })
                else:
                    converted.append({"role": "assistant", "content": content})
            elif isinstance(msg, SystemMessage):
                converted.append({"role": "system", "content": content})
            elif isinstance(msg, ToolMessage):
                converted.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": content
                })
            else:
                # Fallback for unknown message types
                logger.warning(f"Unknown message type: {type(msg)}, treating as user message")
                converted.append({"role": "user", "content": content})

        return converted

    def _convert_response(self, response: litellm.ModelResponse) -> AIMessage:
        """Convert litellm response to LangChain AIMessage."""
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(to_langchain_tool_call({
                    'id': tc.id,
                    'function': {
                        'name': tc.function.name,
                        'arguments': tc.function.arguments
                    }
                }))

        usage_metadata = None
        if response.usage:
            usage_metadata = {
                'input_tokens': response.usage.prompt_tokens,
                'output_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }

        return AIMessage(
            content=content,
            tool_calls=tool_calls,
            usage_metadata=usage_metadata
        )

    def invoke(self, input: list[BaseMessage], *args, **kwargs) -> AIMessage:
        """Synchronous completion (runs async in executor)."""
        try:
            asyncio.get_running_loop()  # noqa: F841 -- detect running loop
        except RuntimeError:
            # No running loop, create one
            return asyncio.run(self.ainvoke(input, *args, **kwargs))

        # Running loop exists, use executor
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.ainvoke(input, *args, **kwargs))
            return future.result()

    async def ainvoke(self, input: list[BaseMessage], *args, **kwargs) -> AIMessage:
        """Async completion using litellm."""
        messages = self._convert_messages(input)

        logger.debug(f"Calling litellm acompletion: model={self._litellm_model}, messages={len(messages)}")

        # Build kwargs for litellm.acompletion
        completion_kwargs = {
            "model": self._litellm_model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        # Only pass tools if we have them
        if self._tool_schemas:
            completion_kwargs["tools"] = self._tool_schemas

        # Only pass api_key if we have one
        if self.api_key:
            completion_kwargs["api_key"] = self.api_key

        # Only pass api_base if we have one
        if self.api_base:
            completion_kwargs["api_base"] = self.api_base

        response = await acompletion(**completion_kwargs)

        result = self._convert_response(response)
        logger.debug(f"Response: content_len={len(result.content)}, tool_calls={len(result.tool_calls)}")

        return result

    def get_num_tokens_from_messages(
        self,
        *,
        messages: list[BaseMessage],
        tools: Optional[Sequence[Any]] = None
    ) -> int:
        """
        Estimate token count using litellm's model-specific token counter.

        Falls back to rough character-based estimate if litellm can't count
        tokens for this model.
        """
        try:
            converted = self._convert_messages(messages)
            return token_counter(model=self._litellm_model, messages=converted)
        except Exception:
            # Fallback: rough estimate (~4 chars per token)
            total_chars = 0
            for msg in messages:
                if isinstance(msg.content, str):
                    total_chars += len(msg.content)
                elif isinstance(msg.content, list):
                    for item in msg.content:
                        if isinstance(item, dict) and 'text' in item:
                            total_chars += len(item['text'])

            if tools:
                for tool in tools:
                    total_chars += len(str(getattr(tool, 'description', '')))

            return total_chars // 4


class LiteLLMModel(BaseArchytasModel):
    """
    Archytas model backend using litellm library for unified LLM access.

    Supports 100+ providers including:
    - Local: Ollama, LMStudio, vLLM, LlamaFile
    - Cloud: OpenAI, Anthropic, Mistral, Groq, Together, Perplexity, DeepSeek
    - Gateway: OpenRouter, Azure, Bedrock, VertexAI

    Configuration via environment variables:
    - LLM_SERVICE_PROVIDER: Provider name (e.g., "ollama", "openai", "litellm:ollama")
    - LLM_SERVICE_MODEL: Model name (e.g., "devstral:latest", "gpt-4o")
    - LLM_BASE_URL: Custom API endpoint (for Ollama, proxies)
    - LLM_SERVICE_TOKEN: API key (or provider-specific env var)
    - LLM_TEMPERATURE: Temperature (default 0.0)
    - LLM_MAX_TOKENS: Max tokens (default 4096)

    Example .env configuration:
        LLM_SERVICE_PROVIDER=litellm:ollama
        LLM_SERVICE_MODEL=devstral:latest
        LLM_BASE_URL=http://localhost:11434
    """

    DEFAULT_MODEL = "gpt-4o"
    DEFAULT_PROVIDER = "openai"

    provider: str = ""
    api_key: str = ""
    api_base: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 4096

    def auth(self, **kwargs) -> None:
        """Set up authentication from config/environment."""
        # Determine provider - handle "litellm:provider" format (anyllm: accepted as legacy)
        raw_provider = (
            kwargs.get("provider")
            or getattr(self.config, "provider", None)
            or os.getenv("LLM_SERVICE_PROVIDER", self.DEFAULT_PROVIDER)
        )

        # Strip "litellm:" prefix (or legacy "anyllm:" prefix) if present
        if raw_provider.lower().startswith("litellm:"):
            self.provider = raw_provider.lower().split(":", 1)[1]
        elif raw_provider.lower().startswith("anyllm:"):
            self.provider = raw_provider.lower().split(":", 1)[1]
        else:
            self.provider = raw_provider.lower()

        # Get API key
        env_var = PROVIDER_API_KEY_ENV.get(self.provider)
        self.api_key = (
            kwargs.get("api_key")
            or getattr(self.config, "api_key", None)
            or os.getenv("LLM_SERVICE_TOKEN", "")
            or (os.getenv(env_var, "") if env_var else "")
        )

        # Validate API key (skip for local providers)
        local_providers = ("ollama", "lmstudio", "vllm", "llamafile", "llamacpp")
        if self.provider not in local_providers:
            if not self.api_key:
                raise AuthenticationError(
                    f"No API key found for provider '{self.provider}'. "
                    f"Set LLM_SERVICE_TOKEN or {env_var or 'provider-specific'} env var."
                )

        # Get optional base URL
        self.api_base = (
            kwargs.get("api_base")
            or getattr(self.config, "base_url", None)
            or os.getenv("LLM_BASE_URL")
        )

        # For Ollama, use OLLAMA_HOST if LLM_BASE_URL not set
        if self.provider == "ollama" and not self.api_base:
            self.api_base = os.getenv("OLLAMA_HOST", "http://localhost:11434")

        # Get temperature and max_tokens
        self.temperature = float(
            kwargs.get("temperature")
            or getattr(self.config, "temperature", None)
            or os.getenv("LLM_TEMPERATURE", "0.0")
        )
        self.max_tokens = int(
            kwargs.get("max_tokens")
            or getattr(self.config, "max_tokens", None)
            or os.getenv("LLM_MAX_TOKENS", "4096")
        )

        logger.info(
            f"LiteLLMModel auth: provider={self.provider}, "
            f"api_base={self.api_base}, has_key={bool(self.api_key)}"
        )

    def initialize_model(self, **kwargs) -> ChatLiteLLM:
        """Create the ChatLiteLLM adapter."""
        model_name = (
            getattr(self.config, "model_name", None)
            or os.getenv("LLM_SERVICE_MODEL")
            or self.DEFAULT_MODEL
        )

        logger.info(
            f"Initializing LiteLLMModel: provider={self.provider}, "
            f"model={model_name}, api_base={self.api_base}"
        )

        return ChatLiteLLM(
            provider=self.provider,
            model=model_name,
            api_key=self.api_key if self.api_key else None,
            api_base=self.api_base,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    async def get_num_tokens_from_messages(
        self,
        messages: list[BaseMessage],
        tools: Optional[Sequence] = None,
    ) -> int:
        """Estimate token count using litellm's model-specific counter."""
        try:
            return self._model.get_num_tokens_from_messages(
                messages=messages,
                tools=tools
            )
        except Exception:
            return 0

    @lru_cache()
    def contextsize(self, model_name: Optional[str] = None) -> int | None:
        """
        Return context size for the model using litellm's model info.

        litellm maintains a comprehensive database of model context sizes,
        which is more accurate and complete than a hardcoded dict.
        """
        name = model_name or self.model_name or ""

        # Build the litellm model string to look up context size
        prefix = LITELLM_PROVIDER_PREFIX.get(self.provider)
        if prefix is not None:
            litellm_model = f"{prefix}/{name}"
        else:
            litellm_model = name

        try:
            return litellm.get_max_tokens(litellm_model)
        except Exception:
            logger.warning(
                f"Unknown context size for model '{name}' (litellm_model='{litellm_model}'). "
                f"Using default 128000."
            )
            return 128000
