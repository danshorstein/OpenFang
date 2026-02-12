"""
Request Router — Classifies and routes incoming messages.

Determines whether a user request can be handled by an existing
automation (cache hit), needs a new automation (codification),
or requires direct LLM synthesis (complex question).
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from openfang.intelligence.models import LLMClient, LLMTier

logger = logging.getLogger("openfang.intelligence.router")


class RequestType(Enum):
    """Classification of incoming user requests."""

    EXISTING_AUTOMATION = "existing_automation"
    NEW_AUTOMATION = "new_automation"
    COMPLEX_QUESTION = "complex_question"
    SIMPLE_RESPONSE = "simple_response"


@dataclass
class RoutingDecision:
    """The router's decision about how to handle a request."""

    request_type: RequestType
    automation_id: str | None = None
    suggested_tier: LLMTier = LLMTier.SONNET
    reasoning: str = ""


class RequestRouter:
    """
    Classifies incoming messages and routes them appropriately.

    Routes to one of:
    - Existing automation query (cache hit, minimal tokens)
    - New automation request (triggers codification engine)
    - Complex question requiring LLM synthesis
    - Simple response (greeting, clarification, etc.)
    """

    def __init__(self, registry: Any, llm_client: LLMClient) -> None:
        self.registry = registry
        self.llm_client = llm_client

    async def route(self, message: str) -> RoutingDecision:
        """
        Classify a user message and decide how to handle it.

        First checks for keyword matches against existing automations.
        If no match, uses a lightweight LLM call to classify the intent.
        """
        # Step 1: Check for direct matches with existing automations
        match = self._check_existing_automations(message)
        if match:
            return RoutingDecision(
                request_type=RequestType.EXISTING_AUTOMATION,
                automation_id=match,
                reasoning="Matched existing automation by keyword",
            )

        # Step 2: Use LLM to classify the request
        classification = await self._classify_with_llm(message)
        return classification

    def _check_existing_automations(self, message: str) -> str | None:
        """
        Check if the message matches an existing automation by keywords.

        Returns the automation_id if found, None otherwise.
        """
        automations = self.registry.list_active()
        message_lower = message.lower()

        for automation in automations:
            name = automation.get("name", "").lower()
            description = automation.get("description", "").lower()

            # Simple keyword matching — can be made smarter
            if name and name in message_lower:
                return automation["id"]
            if description and any(
                word in message_lower
                for word in description.split()
                if len(word) > 4
            ):
                return automation["id"]

        return None

    async def _classify_with_llm(self, message: str) -> RoutingDecision:
        """Use a lightweight LLM call to classify the request type."""
        system_prompt = """You are a request classifier for OpenFang.
Classify the user's message into one of these categories:
- EXISTING_AUTOMATION: Asking about data that a recurring automation would collect
- NEW_AUTOMATION: Requesting a new recurring task or workflow be set up
- COMPLEX_QUESTION: Requires synthesis, analysis, or creative reasoning
- SIMPLE_RESPONSE: Greeting, clarification, or simple factual question

Respond with ONLY the category name."""

        response = await self.llm_client.complete(
            prompt=message,
            tier=LLMTier.HAIKU,
            system=system_prompt,
            max_tokens=50,
        )

        category = response.content.strip().upper()

        type_map = {
            "EXISTING_AUTOMATION": RequestType.EXISTING_AUTOMATION,
            "NEW_AUTOMATION": RequestType.NEW_AUTOMATION,
            "COMPLEX_QUESTION": RequestType.COMPLEX_QUESTION,
            "SIMPLE_RESPONSE": RequestType.SIMPLE_RESPONSE,
        }

        request_type = type_map.get(category, RequestType.SIMPLE_RESPONSE)

        # Determine suggested tier based on classification
        tier_map = {
            RequestType.EXISTING_AUTOMATION: LLMTier.HAIKU,
            RequestType.NEW_AUTOMATION: LLMTier.SONNET,
            RequestType.COMPLEX_QUESTION: LLMTier.OPUS,
            RequestType.SIMPLE_RESPONSE: LLMTier.HAIKU,
        }

        return RoutingDecision(
            request_type=request_type,
            suggested_tier=tier_map[request_type],
            reasoning=f"LLM classified as {category}",
        )
