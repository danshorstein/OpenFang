"""
Components API — MCP server component library.

Endpoints:
- GET /api/components — List all available components
- GET /api/components/servers — List MCP servers
- GET /api/components/search — Search components by tags/query
"""

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
async def list_components(request: Request) -> list[dict[str, Any]]:
    """List all available MCP server components."""
    registry = request.app.state.component_registry
    return registry.components


@router.get("/servers")
async def list_servers(request: Request) -> list[str]:
    """List all discovered MCP server names."""
    registry = request.app.state.component_registry
    return registry.list_servers()


@router.get("/search")
async def search_components(
    request: Request,
    query: str | None = None,
    tags: str | None = None,
) -> list[dict[str, Any]]:
    """Search components by query or tags."""
    registry = request.app.state.component_registry
    tag_list = tags.split(",") if tags else None
    return registry.search(query=query, tags=tag_list)
