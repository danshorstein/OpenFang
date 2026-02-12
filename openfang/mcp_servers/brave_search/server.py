"""
Brave Search MCP Server

Performs web searches via the Brave Search API and returns
structured results with titles, URLs, and descriptions.

Requires BRAVE_SEARCH_API_KEY environment variable.
"""

import os
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel


# ── Configuration ──────────────────────────────────────────

BRAVE_API_KEY = os.environ.get("BRAVE_SEARCH_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


# ── Typed Models ───────────────────────────────────────────


class SearchRequest(BaseModel):
    """Request to perform a web search."""

    query: str
    count: int = 10
    offset: int = 0


class SearchResult(BaseModel):
    """A single search result."""

    title: str
    url: str
    description: str


class SearchResponse(BaseModel):
    """Response containing search results."""

    query: str
    results: list[SearchResult]
    total_count: int
    retrieved_at: datetime


# ── Core Functions (called by both MCP and Python) ─────────


async def search(request: SearchRequest) -> SearchResponse:
    """
    Perform a web search via the Brave Search API.

    Returns structured results with titles, URLs, and descriptions.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            BRAVE_SEARCH_URL,
            params={
                "q": request.query,
                "count": request.count,
                "offset": request.offset,
            },
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
        )
        data = response.json()

    web_results = data.get("web", {}).get("results", [])

    results = [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            description=r.get("description", ""),
        )
        for r in web_results
    ]

    return SearchResponse(
        query=request.query,
        results=results,
        total_count=len(results),
        retrieved_at=datetime.now(timezone.utc),
    )


# ── MCP Server Registration ───────────────────────────────

try:
    from mcp.server import Server

    server = Server("brave-search")

    @server.tool()
    async def mcp_search(query: str, count: int = 10) -> str:
        """Search the web using Brave Search API."""
        request = SearchRequest(query=query, count=count)
        result = await search(request)
        return result.model_dump_json()

except ImportError:
    server = None
