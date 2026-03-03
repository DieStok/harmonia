"""
Direct LLM experiment runner using litellm.

This module provides a simple way to run LLM experiments without the
Beaker/Archytas agent framework. Useful for:
- Simple prompt->response experiments
- Comparing LLM outputs across providers
- Code-only agents (no predefined tool schemas)
- Quick testing without Beaker server overhead

Replaces the previous any-llm-based direct.py.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import litellm

from .litellm_model import LITELLM_PROVIDER_PREFIX


@dataclass
class DirectLLMConfig:
    """Configuration for direct LLM experiments."""
    provider: str
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 4096
    system_prompt: Optional[str] = None


@dataclass
class DirectLLMResult:
    """Result from a direct LLM call."""
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_seconds: float = 0.0
    raw_response: Optional[Any] = None


class DirectLiteLLMRunner:
    """
    Run LLM experiments directly using litellm without Beaker overhead.

    This is useful for:
    - Simple prompt->response experiments
    - Testing different models quickly
    - Code-only agents without predefined tools

    Example:
        runner = DirectLiteLLMRunner(
            provider="ollama",
            model="devstral:latest",
            api_base="http://localhost:11434"
        )

        result = await runner.complete("What is 2+2?")
        print(result.content)

        # Or with conversation history
        history = [
            {"role": "user", "content": "My name is Alice"},
            {"role": "assistant", "content": "Hello Alice!"}
        ]
        result = await runner.complete("What's my name?", conversation_history=history)
    """

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ):
        self.config = DirectLLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )
        self._litellm_model = self._build_model_string()

    def _build_model_string(self) -> str:
        """Build litellm model string from provider + model."""
        prefix = LITELLM_PROVIDER_PREFIX.get(self.config.provider)
        if prefix is None:
            return self.config.model
        return f"{prefix}/{self.config.model}"

    def _build_messages(
        self,
        prompt: str,
        conversation_history: Optional[list[dict]] = None
    ) -> list[dict[str, str]]:
        """Build message list for completion."""
        messages = []

        if self.config.system_prompt:
            messages.append({"role": "system", "content": self.config.system_prompt})

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_completion_kwargs(self, **kwargs) -> dict:
        """Build kwargs dict for litellm.acompletion."""
        completion_kwargs = {
            "model": self._litellm_model,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }

        if self.config.api_key:
            completion_kwargs["api_key"] = self.config.api_key
        if self.config.api_base:
            completion_kwargs["api_base"] = self.config.api_base

        return completion_kwargs

    async def complete(
        self,
        prompt: str,
        conversation_history: Optional[list[dict]] = None,
        **kwargs
    ) -> DirectLLMResult:
        """
        Run a single completion request.

        Args:
            prompt: The user prompt
            conversation_history: Optional list of previous messages
            **kwargs: Additional arguments (temperature, max_tokens)

        Returns:
            DirectLLMResult with the response
        """
        start_time = datetime.now()
        messages = self._build_messages(prompt, conversation_history)

        completion_kwargs = self._build_completion_kwargs(**kwargs)
        completion_kwargs["messages"] = messages
        completion_kwargs["stream"] = False

        response = await litellm.acompletion(**completion_kwargs)

        duration = (datetime.now() - start_time).total_seconds()

        return DirectLLMResult(
            content=response.choices[0].message.content or "",
            model=self.config.model,
            provider=self.config.provider,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
            duration_seconds=duration,
            raw_response=response,
        )

    async def complete_stream(
        self,
        prompt: str,
        conversation_history: Optional[list[dict]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Run a streaming completion request.

        Yields:
            Text chunks as they arrive
        """
        messages = self._build_messages(prompt, conversation_history)

        completion_kwargs = self._build_completion_kwargs(**kwargs)
        completion_kwargs["messages"] = messages
        completion_kwargs["stream"] = True

        response = await litellm.acompletion(**completion_kwargs)

        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def complete_sync(
        self,
        prompt: str,
        conversation_history: Optional[list[dict]] = None,
        **kwargs
    ) -> DirectLLMResult:
        """Synchronous version of complete()."""
        return asyncio.run(self.complete(prompt, conversation_history, **kwargs))

    async def multi_turn_conversation(
        self,
        prompts: list[str],
        **kwargs
    ) -> list[DirectLLMResult]:
        """
        Run a multi-turn conversation.

        Args:
            prompts: List of user prompts to send in sequence
            **kwargs: Additional arguments passed to complete()

        Returns:
            List of DirectLLMResult for each turn
        """
        results = []
        history = []

        for prompt in prompts:
            result = await self.complete(prompt, conversation_history=history, **kwargs)
            results.append(result)

            # Update history
            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": result.content})

        return results


# Convenience function for one-off calls
async def quick_complete(
    prompt: str,
    provider: str = "openai",
    model: str = "gpt-4o",
    **kwargs
) -> str:
    """
    Quick one-off completion without creating a runner.

    Example:
        result = await quick_complete(
            "What is 2+2?",
            provider="ollama",
            model="llama3"
        )
        print(result)
    """
    runner = DirectLiteLLMRunner(provider=provider, model=model, **kwargs)
    result = await runner.complete(prompt)
    return result.content


def quick_complete_sync(
    prompt: str,
    provider: str = "openai",
    model: str = "gpt-4o",
    **kwargs
) -> str:
    """
    Synchronous version of quick_complete().

    Example:
        result = quick_complete_sync(
            "What is 2+2?",
            provider="ollama",
            model="llama3"
        )
        print(result)
    """
    return asyncio.run(quick_complete(prompt, provider, model, **kwargs))
