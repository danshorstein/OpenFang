"""
Escalation Logic — Tier-based problem escalation.

Implements the escalation protocol:
    Python → Sonnet → Opus → User

Problems flow upward only as far as they need to.
"""

import logging
from dataclasses import dataclass
from typing import Any

from openfang.intelligence.models import LLMClient, LLMTier

logger = logging.getLogger("openfang.intelligence.escalation")


@dataclass
class EscalationRecord:
    """Record of an escalation event."""

    automation_id: str
    from_tier: str
    to_tier: str
    reason: str
    resolved: bool = False
    resolution: str | None = None


class EscalationManager:
    """
    Manages the escalation protocol between tiers.

    Escalation flows upward:
        Python failure → Sonnet review → Opus redesign → User notification

    Each tier attempts to resolve the issue before escalating.
    """

    def __init__(self, llm_client: LLMClient, registry: Any) -> None:
        self.llm_client = llm_client
        self.registry = registry
        self.history: list[EscalationRecord] = []

    async def escalate(
        self,
        automation_id: str,
        error: str,
        current_tier: str = "python",
    ) -> EscalationRecord:
        """
        Escalate a problem to the next tier.

        Args:
            automation_id: The failing automation.
            error: Description of the problem.
            current_tier: The tier that couldn't resolve it.
        """
        tier_chain = ["python", "haiku", "sonnet", "opus", "user"]
        current_idx = tier_chain.index(current_tier)

        if current_idx >= len(tier_chain) - 1:
            # Already at user level
            return EscalationRecord(
                automation_id=automation_id,
                from_tier=current_tier,
                to_tier="user",
                reason=error,
            )

        next_tier = tier_chain[current_idx + 1]

        record = EscalationRecord(
            automation_id=automation_id,
            from_tier=current_tier,
            to_tier=next_tier,
            reason=error,
        )

        logger.info(
            f"Escalating {automation_id}: {current_tier} → {next_tier}"
        )

        # If escalating to an LLM tier, attempt resolution
        if next_tier in ("haiku", "sonnet", "opus"):
            resolved = await self._attempt_resolution(
                automation_id, error, next_tier
            )
            if resolved:
                record.resolved = True
                record.resolution = f"Resolved by {next_tier}"
                logger.info(f"Resolved by {next_tier}: {automation_id}")
            else:
                # Escalate further
                logger.info(
                    f"{next_tier} could not resolve {automation_id}, "
                    f"escalating further"
                )
                record = await self.escalate(
                    automation_id, error, next_tier
                )

        self.history.append(record)
        return record

    async def _attempt_resolution(
        self,
        automation_id: str,
        error: str,
        tier: str,
    ) -> bool:
        """Attempt to resolve an issue at a specific LLM tier."""
        tier_map = {
            "haiku": LLMTier.HAIKU,
            "sonnet": LLMTier.SONNET,
            "opus": LLMTier.OPUS,
        }
        llm_tier = tier_map.get(tier, LLMTier.SONNET)

        system = f"""You are an OpenFang automation debugger at the {tier} tier.
Analyze this automation failure and determine if you can fix it.

If you can fix it, respond with "RESOLVED" followed by the fix.
If you cannot fix it, respond with "ESCALATE" followed by why."""

        prompt = f"""Automation: {automation_id}
Error: {error}

Can you resolve this?"""

        response = await self.llm_client.complete(
            prompt=prompt,
            tier=llm_tier,
            system=system,
            max_tokens=1000,
        )

        return response.content.strip().startswith("RESOLVED")
