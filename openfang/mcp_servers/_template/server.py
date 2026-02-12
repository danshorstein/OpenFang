"""
MCP Server Template — server.py

This is the template for creating a new dual-interface MCP server.
Replace 'template' with your server name throughout.

Architecture:
    Core functions (async, typed) are defined first.
    MCP tool wrappers delegate to core functions.
    Both Python scripts and LLM can call the same logic.
"""

from datetime import datetime, timezone

from pydantic import BaseModel

# ── Typed Models ───────────────────────────────────────────
# Define your request/response models here.
# These are used by both the MCP interface and direct Python calls.


class ExampleRequest(BaseModel):
    """Example request model. Replace with your actual request schema."""

    query: str


class ExampleResponse(BaseModel):
    """Example response model. Replace with your actual response schema."""

    result: str
    retrieved_at: datetime


# ── Core Functions (called by both MCP and Python) ─────────
# These are the actual implementations. They should be async,
# accept typed inputs, and return typed outputs.


async def example_action(request: ExampleRequest) -> ExampleResponse:
    """
    Example action. Replace with your actual implementation.

    This function is called by both:
    - Python orchestration scripts (direct import)
    - LLM via MCP protocol (through the wrapper below)
    """
    # TODO: Implement your actual logic here
    return ExampleResponse(
        result=f"Processed: {request.query}",
        retrieved_at=datetime.now(timezone.utc),
    )


# ── MCP Server Registration ───────────────────────────────
# These wrappers expose the core functions via the MCP protocol.
# The LLM sees these as tools it can call.

try:
    from mcp.server import Server

    server = Server("template-server")

    @server.tool()
    async def mcp_example_action(query: str) -> str:
        """Execute an example action. Replace with your actual tool description."""
        request = ExampleRequest(query=query)
        result = await example_action(request)
        return result.model_dump_json()

except ImportError:
    # MCP package not installed — server runs in Python-only mode
    server = None
