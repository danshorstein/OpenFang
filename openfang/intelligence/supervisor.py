"""
Supervisor — Periodic LLM review of system health.

Runs 2-3x daily (configurable). Reviews logs from all automations,
identifies failures, auto-patches when possible, and escalates
to higher tiers or the user when necessary.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from openfang.intelligence.models import LLMClient, LLMTier

logger = logging.getLogger("openfang.intelligence.supervisor")


@dataclass
class ReviewAction:
    """An action the supervisor decides to take."""

    type: str  # "auto_patch" | "escalate_to_opus" | "escalate_to_user" | "mark_resolved"
    automation_id: str
    reason: str
    patch_code: str | None = None
    message: str | None = None


@dataclass
class ReviewResult:
    """Result from a supervisor review cycle."""

    summary: str
    actions: list[ReviewAction] = field(default_factory=list)
    logs_reviewed: int = 0
    issues_found: int = 0


class Supervisor:
    """
    Periodic LLM review of system health.

    The supervisor:
    1. Gathers all logs since the last review
    2. Identifies failures and anomalies
    3. Decides on actions (auto-patch, escalate, resolve)
    4. Executes those actions
    5. Marks logs as reviewed
    """

    def __init__(
        self,
        llm_client: LLMClient,
        registry: Any,
        log_aggregator: Any,
    ) -> None:
        self.llm_client = llm_client
        self.registry = registry
        self.log_aggregator = log_aggregator

    async def review_cycle(
        self, llm_tier: LLMTier = LLMTier.SONNET
    ) -> ReviewResult:
        """
        Run a complete review cycle.

        Gathers unreviewed logs, compiles a summary, sends to
        the LLM for analysis, and executes recommended actions.
        """
        # Gather logs and flagged automations
        logs = self.log_aggregator.get_logs(status="failure")
        flagged = self.registry.get_flagged()

        if not logs and not flagged:
            logger.info("Review cycle: no issues found")
            return ReviewResult(
                summary="All clear. No issues found.",
                logs_reviewed=0,
                issues_found=0,
            )

        # Compile review summary
        summary = self._compile_summary(logs, flagged)

        # LLM reviews and recommends actions
        review = await self._llm_review(summary, llm_tier)

        # Execute actions
        for action in review.actions:
            await self._execute_action(action)

        logger.info(
            f"Review cycle complete: {review.logs_reviewed} logs reviewed, "
            f"{review.issues_found} issues found, "
            f"{len(review.actions)} actions taken"
        )

        return review

    def _compile_summary(
        self, logs: list[Any], flagged: list[Any]
    ) -> str:
        """Compile a structured summary for LLM review."""
        parts = ["## Automation Health Review\n"]

        if logs:
            parts.append(f"### Failed Runs ({len(logs)})\n")
            for log in logs[:20]:  # Cap at 20 to manage token usage
                parts.append(
                    f"- **{log.automation_id}** at {log.run_at}: "
                    f"{log.error_detail or 'Unknown error'}\n"
                )

        if flagged:
            parts.append(f"\n### Flagged Automations ({len(flagged)})\n")
            for item in flagged:
                parts.append(
                    f"- **{item.get('id', 'unknown')}**: "
                    f"{item.get('flag_reason', 'No reason')}\n"
                )

        return "".join(parts)

    async def _llm_review(
        self, summary: str, llm_tier: LLMTier
    ) -> ReviewResult:
        """Send the summary to the LLM for review and action recommendations."""
        system = """You are the OpenFang supervisor. Review automation health logs
and recommend actions for each issue:
- auto_patch: You can fix this with a code change (provide the fix)
- escalate_to_opus: This needs a higher-tier model to redesign
- escalate_to_user: This needs human attention
- mark_resolved: This was a transient issue that resolved itself

Be conservative with auto-patching. When in doubt, escalate."""

        response = await self.llm_client.complete(
            prompt=summary,
            tier=llm_tier,
            system=system,
        )

        # TODO: Parse LLM response into structured actions
        return ReviewResult(
            summary=response.content,
            actions=[],
            logs_reviewed=0,
            issues_found=0,
        )

    async def _execute_action(self, action: ReviewAction) -> None:
        """Execute a single review action."""
        match action.type:
            case "auto_patch":
                logger.info(
                    f"Auto-patching {action.automation_id}: {action.reason}"
                )
                # TODO: Apply the patch code to the automation script
            case "escalate_to_opus":
                logger.info(
                    f"Escalating {action.automation_id} to Opus: {action.reason}"
                )
                # TODO: Queue for Opus review
            case "escalate_to_user":
                logger.info(
                    f"Escalating {action.automation_id} to user: {action.reason}"
                )
                # TODO: Send notification to user
            case "mark_resolved":
                logger.info(
                    f"Marking {action.automation_id} as resolved: {action.reason}"
                )
                self.registry.resolve_flag(action.automation_id)
