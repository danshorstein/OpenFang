"""Tests for the Supervisor."""

import pytest

from openfang.intelligence.supervisor import ReviewAction, ReviewResult


class TestReviewResult:
    def test_empty_review(self) -> None:
        result = ReviewResult(summary="All clear.")
        assert result.summary == "All clear."
        assert result.actions == []
        assert result.logs_reviewed == 0
        assert result.issues_found == 0

    def test_review_with_actions(self) -> None:
        action = ReviewAction(
            type="auto_patch",
            automation_id="test-001",
            reason="Rate limit hit",
            patch_code="# add retry logic",
        )
        result = ReviewResult(
            summary="Found 1 issue",
            actions=[action],
            logs_reviewed=10,
            issues_found=1,
        )
        assert len(result.actions) == 1
        assert result.actions[0].type == "auto_patch"
