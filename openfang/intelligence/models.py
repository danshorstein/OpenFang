"""
LLM Client Configuration — Model routing and tier management.

Configures LLM clients for different tiers (Opus, Sonnet, Haiku)
and provides a unified interface for making LLM calls with
automatic cost tracking.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("openfang.intelligence.models")


class LLMTier(Enum):
    """Available LLM tiers ordered by capability and cost."""

    OPUS = "opus"
    SONNET = "sonnet"
    HAIKU = "haiku"


@dataclass
class LLMConfig:
    """Configuration for a specific LLM tier."""

    tier: LLMTier
    model_id: str
    max_tokens: int = 4096
    temperature: float = 0.0


# Default model configurations
DEFAULT_CONFIGS: dict[LLMTier, LLMConfig] = {
    LLMTier.OPUS: LLMConfig(
        tier=LLMTier.OPUS,
        model_id="claude-opus-4-20250514",
        max_tokens=4096,
        temperature=0.0,
    ),
    LLMTier.SONNET: LLMConfig(
        tier=LLMTier.SONNET,
        model_id="claude-sonnet-4-20250514",
        max_tokens=4096,
        temperature=0.0,
    ),
    LLMTier.HAIKU: LLMConfig(
        tier=LLMTier.HAIKU,
        model_id="claude-haiku-4-20250514",
        max_tokens=4096,
        temperature=0.0,
    ),
}


@dataclass
class LLMResponse:
    """Response from an LLM call with cost tracking."""

    content: str
    model_id: str
    tier: LLMTier
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMClient:
    """
    Unified LLM client supporting tiered model routing.

    Wraps the Anthropic SDK to provide:
    - Tier-based model selection
    - Automatic cost tracking per call
    - Structured prompt/response handling
    """

    def __init__(self, configs: dict[LLMTier, LLMConfig] | None = None) -> None:
        self.configs = configs or DEFAULT_CONFIGS
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazily initialize the Anthropic client."""
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic()
        return self._client

    async def complete(
        self,
        prompt: str,
        tier: LLMTier = LLMTier.SONNET,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Make an LLM completion call at the specified tier.

        Args:
            prompt: The user message to send.
            tier: Which LLM tier to use (defaults to Sonnet).
            system: Optional system prompt.
            max_tokens: Override default max tokens.
        """
        config = self.configs[tier]
        client = self._get_client()

        messages = [{"role": "user", "content": prompt}]

        kwargs: dict[str, Any] = {
            "model": config.model_id,
            "max_tokens": max_tokens or config.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)

        result = LLMResponse(
            content=response.content[0].text,
            model_id=config.model_id,
            tier=tier,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        logger.info(
            f"LLM call [{tier.value}]: {result.total_tokens} tokens"
        )

        return result
