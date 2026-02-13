"""Tests for the Slack Notify MCP Server.

Tests both calling patterns using a mock HTTP client
so no real Slack API calls are made.
"""

import json
from datetime import datetime

import httpx
import pytest

from openfang.mcp_servers.slack_notify.server import (
    ListChannelsResponse,
    SendMessageRequest,
    SendMessageResponse,
    list_channels,
    send_message,
)


def _mock_transport(response_data: dict, status_code: int = 200) -> httpx.AsyncClient:
    """Create an httpx client with a mocked transport."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json=response_data,
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestSendMessage:
    async def test_successful_send(self) -> None:
        client = _mock_transport({
            "ok": True,
            "channel": "C123",
            "ts": "1234567890.123456",
        })

        result = await send_message(
            SendMessageRequest(channel="C123", text="Hello!"),
            http_client=client,
            token="xoxb-test-token",
        )

        assert isinstance(result, SendMessageResponse)
        assert result.ok is True
        assert result.channel == "C123"
        assert result.ts == "1234567890.123456"
        assert result.error is None
        assert result.sent_at is not None

    async def test_send_with_thread(self) -> None:
        client = _mock_transport({"ok": True, "channel": "C123", "ts": "111.222"})

        result = await send_message(
            SendMessageRequest(
                channel="C123",
                text="Thread reply",
                thread_ts="100.200",
            ),
            http_client=client,
            token="xoxb-test",
        )

        assert result.ok is True

    async def test_api_error_response(self) -> None:
        client = _mock_transport({
            "ok": False,
            "error": "channel_not_found",
        })

        result = await send_message(
            SendMessageRequest(channel="C999", text="Hello!"),
            http_client=client,
            token="xoxb-test",
        )

        assert result.ok is False
        assert result.error == "channel_not_found"
        assert result.channel == "C999"

    async def test_network_error_handled(self) -> None:
        """HTTP errors should be caught and returned gracefully."""

        async def failing_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(failing_handler)
        )

        result = await send_message(
            SendMessageRequest(channel="C123", text="Hello!"),
            http_client=client,
            token="xoxb-test",
        )

        assert result.ok is False
        assert "HTTP error" in (result.error or "")


class TestListChannels:
    async def test_successful_list(self) -> None:
        client = _mock_transport({
            "ok": True,
            "channels": [
                {"id": "C001", "name": "general"},
                {"id": "C002", "name": "random"},
            ],
        })

        result = await list_channels(http_client=client, token="xoxb-test")

        assert isinstance(result, ListChannelsResponse)
        assert result.ok is True
        assert len(result.channels) == 2
        assert result.channels[0]["name"] == "general"

    async def test_empty_channels(self) -> None:
        client = _mock_transport({"ok": True, "channels": []})

        result = await list_channels(http_client=client, token="xoxb-test")

        assert result.ok is True
        assert result.channels == []

    async def test_network_error_handled(self) -> None:
        async def failing_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(failing_handler)
        )

        result = await list_channels(http_client=client, token="xoxb-test")

        assert result.ok is False
        assert result.channels == []


class TestModels:
    def test_send_message_request(self) -> None:
        req = SendMessageRequest(channel="C123", text="Hello")
        assert req.channel == "C123"
        assert req.text == "Hello"
        assert req.thread_ts is None

    def test_send_message_request_with_thread(self) -> None:
        req = SendMessageRequest(
            channel="C123", text="Reply", thread_ts="100.200"
        )
        assert req.thread_ts == "100.200"
