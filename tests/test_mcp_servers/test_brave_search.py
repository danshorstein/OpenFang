"""Tests for the Brave Search MCP Server.

Tests both calling patterns using a mock HTTP client
so no real Brave Search API calls are made.
"""

import httpx
import pytest

from openfang.mcp_servers.brave_search.server import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    search,
)


def _mock_transport(response_data: dict, status_code: int = 200) -> httpx.AsyncClient:
    """Create an httpx client with a mocked transport."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json=response_data,
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


MOCK_SEARCH_RESPONSE = {
    "web": {
        "results": [
            {
                "title": "OpenFang GitHub",
                "url": "https://github.com/openfang/openfang",
                "description": "LLMs write automations, not be automations.",
            },
            {
                "title": "OpenFang Docs",
                "url": "https://docs.openfang.dev",
                "description": "Documentation for the OpenFang framework.",
            },
            {
                "title": "MCP Protocol Spec",
                "url": "https://modelcontextprotocol.io",
                "description": "The Model Context Protocol specification.",
            },
        ]
    }
}


class TestSearch:
    async def test_successful_search(self) -> None:
        client = _mock_transport(MOCK_SEARCH_RESPONSE)

        result = await search(
            SearchRequest(query="OpenFang"),
            http_client=client,
            api_key="test-key",
        )

        assert isinstance(result, SearchResponse)
        assert result.query == "OpenFang"
        assert result.total_count == 3
        assert len(result.results) == 3
        assert result.retrieved_at is not None

    async def test_result_structure(self) -> None:
        client = _mock_transport(MOCK_SEARCH_RESPONSE)

        result = await search(
            SearchRequest(query="OpenFang"),
            http_client=client,
            api_key="test-key",
        )

        first = result.results[0]
        assert isinstance(first, SearchResult)
        assert first.title == "OpenFang GitHub"
        assert first.url == "https://github.com/openfang/openfang"
        assert "automations" in first.description

    async def test_empty_results(self) -> None:
        client = _mock_transport({"web": {"results": []}})

        result = await search(
            SearchRequest(query="xyznonexistent"),
            http_client=client,
            api_key="test-key",
        )

        assert result.total_count == 0
        assert result.results == []

    async def test_count_parameter(self) -> None:
        """Verify count parameter is passed to the API."""
        received_params = {}

        async def capturing_handler(request: httpx.Request) -> httpx.Response:
            received_params.update(dict(request.url.params))
            return httpx.Response(200, json={"web": {"results": []}})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(capturing_handler)
        )

        await search(
            SearchRequest(query="test", count=5, offset=10),
            http_client=client,
            api_key="test-key",
        )

        assert received_params["q"] == "test"
        assert received_params["count"] == "5"
        assert received_params["offset"] == "10"

    async def test_api_key_header(self) -> None:
        """Verify API key is sent in the header."""
        received_headers = {}

        async def capturing_handler(request: httpx.Request) -> httpx.Response:
            received_headers.update(dict(request.headers))
            return httpx.Response(200, json={"web": {"results": []}})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(capturing_handler)
        )

        await search(
            SearchRequest(query="test"),
            http_client=client,
            api_key="my-secret-key",
        )

        assert received_headers.get("x-subscription-token") == "my-secret-key"

    async def test_network_error_handled(self) -> None:
        """HTTP errors should return an empty result, not crash."""

        async def failing_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(failing_handler)
        )

        result = await search(
            SearchRequest(query="test"),
            http_client=client,
            api_key="test-key",
        )

        assert result.total_count == 0
        assert result.results == []
        assert result.query == "test"

    async def test_malformed_api_response(self) -> None:
        """Handles API responses missing expected fields."""
        client = _mock_transport({"unexpected": "data"})

        result = await search(
            SearchRequest(query="test"),
            http_client=client,
            api_key="test-key",
        )

        assert result.total_count == 0
        assert result.results == []


class TestModels:
    def test_search_request_defaults(self) -> None:
        req = SearchRequest(query="hello")
        assert req.count == 10
        assert req.offset == 0

    def test_search_result(self) -> None:
        result = SearchResult(
            title="Test",
            url="https://example.com",
            description="A test result",
        )
        assert result.title == "Test"
