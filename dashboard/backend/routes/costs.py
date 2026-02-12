"""
Costs API — Token usage and cost tracking.

Endpoints:
- GET /api/costs — Get cost overview
- GET /api/costs/breakdown — Per-automation cost breakdown
"""

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def get_costs() -> dict[str, Any]:
    """Get overall cost overview."""
    # TODO: Aggregate from automation logs
    return {
        "total_tokens_today": 0,
        "total_tokens_this_week": 0,
        "total_tokens_this_month": 0,
        "estimated_cost_today": 0.0,
        "estimated_cost_this_month": 0.0,
    }


@router.get("/breakdown")
async def get_breakdown() -> list[dict[str, Any]]:
    """Get per-automation cost breakdown."""
    # TODO: Calculate from automation run logs
    return []
