"""
Brave Search MCP Server

Performs web searches via the Brave Search API and returns
structured results with titles, URLs, and descriptions.

Requires BRAVE_SEARCH_API_KEY environment variable.

All functions accept an optional http_client parameter for
testability; when omitted they create a new httpx.AsyncClient.
"""

import logging
import os
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel

logger = logging.getLogger("openfang.mcp_servers.brave_search")

# ── Configuration ──────────────────────────────────────────

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def _get_api_key() -> str:
    key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    if not key:
        logger.warning("BRAVE_SEARCH_API_KEY not set")
    return key


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


async def search(
    request: SearchRequest,
    http_client: httpx.AsyncClient | None = None,
    api_key: str | None = None,
) -> SearchResponse:
    """
    Perform a web search via the Brave Search API.

    Returns structured results with titles, URLs, and descriptions.

    Args:
        request: The search request.
        http_client: Optional httpx client (for testing).
        api_key: Optional API key override (for testing).
    """
    key = api_key or _get_api_key()

    params = {
        "q": request.query,
        "count": request.count,
        "offset": request.offset,
    }
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": key,
    }

    try:
        if http_client:
            response = await http_client.get(
                BRAVE_SEARCH_URL, params=params, headers=headers,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    BRAVE_SEARCH_URL, params=params, headers=headers,
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

    except httpx.HTTPError as e:
        logger.error(f"Brave Search API error: {e}")
        return SearchResponse(
            query=request.query,
            results=[],
            total_count=0,
            retrieved_at=datetime.now(timezone.utc),
        )


# ── MCP Server Registration ───────────────────────────────

try:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("brave-search")

    @server.tool()
    async def mcp_search(query: str, count: int = 10) -> str:
        """Search the web using Brave Search API."""
        req = SearchRequest(query=query, count=count)
        result = await search(req)
        return result.model_dump_json()

except ImportError:
    server = None
