"""
Automations API — CRUD operations for automation management.

Endpoints:
- GET /api/automations — List all automations
- GET /api/automations/{id} — Get automation details
- PATCH /api/automations/{id}/status — Update status (pause/resume)
- GET /api/automations/{id}/history — Get run history
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("")
async def list_automations(request: Request) -> list[dict[str, Any]]:
    """List all automations with their current status."""
    registry = request.app.state.automation_registry
    return await registry.list_all()


@router.get("/{automation_id}")
async def get_automation(
    automation_id: str, request: Request
) -> dict[str, Any]:
    """Get details for a specific automation."""
    registry = request.app.state.automation_registry
    automation = await registry.get(automation_id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return automation


@router.patch("/{automation_id}/status")
async def update_status(
    automation_id: str, status: str, request: Request
) -> dict[str, str]:
    """Update an automation's status (active/paused)."""
    registry = request.app.state.automation_registry
    automation = await registry.get(automation_id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")

    await registry.update_status(automation_id, status)
    return {"id": automation_id, "status": status}


@router.get("/{automation_id}/history")
async def get_history(
    automation_id: str, request: Request, limit: int = 50
) -> list[dict[str, Any]]:
    """Get run history for an automation."""
    registry = request.app.state.automation_registry
    return await registry.get_run_history(automation_id, limit=limit)
