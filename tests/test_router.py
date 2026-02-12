"""Tests for the Request Router."""

import pytest

from openfang.intelligence.router import RequestType, RoutingDecision


class TestRoutingDecision:
    def test_default_tier_is_sonnet(self) -> None:
        from openfang.intelligence.models import LLMTier

        decision = RoutingDecision(
            request_type=RequestType.SIMPLE_RESPONSE,
        )
        assert decision.suggested_tier == LLMTier.SONNET

    def test_existing_automation_includes_id(self) -> None:
        decision = RoutingDecision(
            request_type=RequestType.EXISTING_AUTOMATION,
            automation_id="youtube_daily",
        )
        assert decision.automation_id == "youtube_daily"

    def test_request_types(self) -> None:
        assert RequestType.EXISTING_AUTOMATION.value == "existing_automation"
        assert RequestType.NEW_AUTOMATION.value == "new_automation"
        assert RequestType.COMPLEX_QUESTION.value == "complex_question"
        assert RequestType.SIMPLE_RESPONSE.value == "simple_response"
