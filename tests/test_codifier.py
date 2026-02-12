"""Tests for the Codification Engine."""

import pytest

from openfang.intelligence.codifier import ParsedIntent, PipelineDesign


class TestParsedIntent:
    def test_basic_intent(self) -> None:
        intent = ParsedIntent(
            summary="Track YouTube analytics daily",
            required_capabilities=["get_channel_stats"],
            relevant_tags=["analytics", "youtube"],
            suggested_schedule="0 7 * * *",
        )
        assert intent.summary == "Track YouTube analytics daily"
        assert "analytics" in intent.relevant_tags
        assert intent.suggested_schedule == "0 7 * * *"

    def test_intent_defaults(self) -> None:
        intent = ParsedIntent(
            summary="Test",
            required_capabilities=[],
            relevant_tags=[],
        )
        assert intent.data_sources == []
        assert intent.output_targets == []
        assert intent.suggested_schedule is None


class TestPipelineDesign:
    def test_basic_design(self) -> None:
        design = PipelineDesign(
            name="youtube_ctr_monitor",
            description="Monitor YouTube CTR daily",
            steps=[
                {"action": "fetch_stats", "server": "youtube-analytics"},
                {"action": "store", "server": "database"},
            ],
            mcp_servers_used=["youtube-analytics", "database"],
            cron_schedule="0 7 * * *",
        )
        assert design.name == "youtube_ctr_monitor"
        assert len(design.steps) == 2
        assert "youtube-analytics" in design.mcp_servers_used
