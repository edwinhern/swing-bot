"""Perplexity AI API client for stock research."""

import json
import os
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from perplexity import AsyncPerplexity, Perplexity

# Type-safe model selection
PerplexityModel = Literal[
    "sonar",  # Quick queries, cheapest - use for Stage 2
    "sonar-pro",  # Complex research - use for Stage 3
    "sonar-reasoning",  # Problem-solving and scoring - use for Stage 4
    "sonar-reasoning-pro",  # Advanced reasoning
    "sonar-deep-research",  # Exhaustive research (100 RPM limit)
]

T = TypeVar("T", bound=BaseModel)


class PerplexityClient:
    """Client for interacting with Perplexity AI API.

    Supports both synchronous and asynchronous operations with structured
    output using JSON schemas.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Perplexity client.

        Args:
            api_key: Perplexity API key. If not provided, uses PERPLEXITY_API_KEY env var.
        """
        self._api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not self._api_key:
            raise ValueError("Perplexity API key is required. Set PERPLEXITY_API_KEY env var or pass api_key.")

        self._sync_client = Perplexity(api_key=self._api_key)
        self._async_client = AsyncPerplexity(api_key=self._api_key)

    def _build_json_schema(self, model_class: type[T]) -> dict[str, Any]:
        """Build a JSON schema from a Pydantic model for structured output.

        Args:
            model_class: Pydantic model class to convert to JSON schema

        Returns:
            JSON schema dict compatible with Perplexity API
        """
        schema = model_class.model_json_schema()
        return {"type": "json_schema", "json_schema": {"schema": schema}}

    def chat(
        self,
        prompt: str,
        model: PerplexityModel = "sonar-pro",
        system_message: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Send a chat completion request (synchronous).

        Args:
            prompt: User prompt/question
            model: Perplexity model to use
            system_message: Optional system message for context
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens in response

        Returns:
            Response content as string
        """
        messages: list[dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        response = self._sync_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content or ""

    async def achat(
        self,
        prompt: str,
        model: PerplexityModel = "sonar-pro",
        system_message: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Send a chat completion request (asynchronous).

        Args:
            prompt: User prompt/question
            model: Perplexity model to use
            system_message: Optional system message for context
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens in response

        Returns:
            Response content as string
        """
        messages: list[dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        response = await self._async_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content or ""

    def chat_structured(
        self,
        prompt: str,
        response_model: type[T],
        model: PerplexityModel = "sonar-pro",
        system_message: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> T:
        """Send a chat request with structured JSON output (synchronous).

        Args:
            prompt: User prompt/question
            response_model: Pydantic model class for response parsing
            model: Perplexity model to use
            system_message: Optional system message for context
            temperature: Sampling temperature (lower for structured output)
            max_tokens: Maximum tokens in response

        Returns:
            Parsed Pydantic model instance
        """
        messages: list[dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        response_format = self._build_json_schema(response_model)

        response = self._sync_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return response_model.model_validate(data)

    async def achat_structured(
        self,
        prompt: str,
        response_model: type[T],
        model: PerplexityModel = "sonar-pro",
        system_message: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> T:
        """Send a chat request with structured JSON output (asynchronous).

        Args:
            prompt: User prompt/question
            response_model: Pydantic model class for response parsing
            model: Perplexity model to use
            system_message: Optional system message for context
            temperature: Sampling temperature (lower for structured output)
            max_tokens: Maximum tokens in response

        Returns:
            Parsed Pydantic model instance
        """
        messages: list[dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        response_format = self._build_json_schema(response_model)

        response = await self._async_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return response_model.model_validate(data)


# Singleton instance
_perplexity_client: PerplexityClient | None = None


def get_perplexity_client() -> PerplexityClient:
    """Get or create the singleton Perplexity client instance."""
    global _perplexity_client
    if _perplexity_client is None:
        _perplexity_client = PerplexityClient()
    return _perplexity_client
