"""LLM Service - Unified interface for Claude and OpenAI APIs."""

import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Literal

from app.config import get_settings


class BaseLLMProvider(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Generate a response from the LLM."""
        pass

    @abstractmethod
    async def generate_stream(
        self, prompt: str, system: str | None = None
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response from the LLM."""
        pass


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Generate a response from Claude."""
        messages = [{"role": "user", "content": prompt}]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system or "",
            messages=messages,
        )

        return response.content[0].text

    async def generate_stream(
        self, prompt: str, system: str | None = None
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response from Claude."""
        messages = [{"role": "user", "content": prompt}]

        async with self.client.messages.stream(
            model=self.model,
            max_tokens=8192,
            system=system or "",
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT API provider."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Generate a response from OpenAI."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=8192,
        )

        return response.choices[0].message.content or ""

    async def generate_stream(
        self, prompt: str, system: str | None = None
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response from OpenAI."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=8192,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class LLMService:
    """Unified LLM service supporting multiple providers."""

    def __init__(
        self,
        provider: Literal["anthropic", "openai"] = "anthropic",
        api_key: str | None = None,
        model: str | None = None,
    ):
        settings = get_settings()

        if provider == "anthropic":
            key = api_key or settings.anthropic_api_key
            mdl = model or settings.anthropic_model
            if not key:
                raise ValueError("Anthropic API key not configured")
            self._provider = AnthropicProvider(key, mdl)
        elif provider == "openai":
            key = api_key or settings.openai_api_key
            mdl = model or settings.openai_model
            if not key:
                raise ValueError("OpenAI API key not configured")
            self._provider = OpenAIProvider(key, mdl)
        else:
            raise ValueError(f"Unknown provider: {provider}")

        self.provider_name = provider

    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Generate a response."""
        return await self._provider.generate(prompt, system)

    async def generate_stream(
        self, prompt: str, system: str | None = None
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response."""
        async for chunk in self._provider.generate_stream(prompt, system):
            yield chunk

    async def generate_json(
        self, prompt: str, system: str | None = None
    ) -> dict:
        """Generate a JSON response (extracts JSON from the response)."""
        response = await self.generate(prompt, system)

        # Try to extract JSON from the response
        # Handle cases where model might wrap JSON in markdown code blocks
        text = response.strip()

        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Failed to parse JSON from response: {e}")


def get_llm_service(
    provider: Literal["anthropic", "openai"] | None = None
) -> LLMService:
    """Get an LLM service instance using default settings."""
    settings = get_settings()
    provider = provider or settings.default_llm_provider
    return LLMService(provider=provider)
