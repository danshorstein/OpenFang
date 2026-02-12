"""
Insights API — LLM-generated synthesis and trends.

Endpoints:
- GET /api/insights — Get latest insights
- GET /api/insights/summary — Get daily/weekly summary
"""

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def get_insights() -> list[dict[str, Any]]:
    """Get the latest LLM-generated insights."""
    # TODO: Integrate with supervisor review summaries
    return []


@router.get("/summary")
async def get_summary(period: str = "daily") -> dict[str, Any]:
    """Get a daily or weekly summary from the supervisor."""
    # TODO: Generate summary from recent review cycles
    return {"period": period, "summary": "No insights available yet."}
