"""
Tests for the template MCP server.

Every MCP server must test both calling patterns:
1. Direct Python function calls
2. MCP protocol tool calls (if mcp package is available)
"""

import pytest

from openfang.mcp_servers._template.server import (
    ExampleRequest,
    ExampleResponse,
    example_action,
)


class TestDirectPythonCalls:
    """Test the core functions via direct Python import."""

    async def test_example_action_returns_typed_response(self) -> None:
        request = ExampleRequest(query="test query")
        response = await example_action(request)

        assert isinstance(response, ExampleResponse)
        assert "test query" in response.result
        assert response.retrieved_at is not None

    async def test_example_action_with_empty_query(self) -> None:
        request = ExampleRequest(query="")
        response = await example_action(request)

        assert isinstance(response, ExampleResponse)
