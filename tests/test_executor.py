"""Tests for the Pipeline Executor."""

import pytest

from openfang.orchestration.executor import PipelineContext, PipelineResult


class TestPipelineContext:
    def test_success_creates_result(self) -> None:
        from datetime import datetime, timezone

        ctx = PipelineContext(
            automation_id="test-001",
            run_at=datetime.now(timezone.utc),
        )
        result = ctx.success(summary="All good")

        assert isinstance(result, PipelineResult)
        assert result.status == "success"
        assert result.summary == "All good"
        assert result.error is None

    def test_failure_creates_result(self) -> None:
        from datetime import datetime, timezone

        ctx = PipelineContext(
            automation_id="test-001",
            run_at=datetime.now(timezone.utc),
        )
        result = ctx.failure(summary="Something broke", error="ConnectionError")

        assert isinstance(result, PipelineResult)
        assert result.status == "failure"
        assert result.error == "ConnectionError"

    def test_config_defaults_to_empty_dict(self) -> None:
        from datetime import datetime, timezone

        ctx = PipelineContext(
            automation_id="test-001",
            run_at=datetime.now(timezone.utc),
        )
        assert ctx.config == {}
