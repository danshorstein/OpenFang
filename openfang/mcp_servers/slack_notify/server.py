"""
Slack Notify MCP Server

Sends messages to Slack channels via the Slack Web API.
Supports plain text and block-formatted messages.

Requires SLACK_BOT_TOKEN environment variable.

All functions accept an optional http_client parameter for
testability; when omitted they create a new httpx.AsyncClient.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger("openfang.mcp_servers.slack_notify")

# ── Configuration ──────────────────────────────────────────

SLACK_API_URL = "https://slack.com/api"


def _get_token() -> str:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not set")
    return token


# ── Typed Models ───────────────────────────────────────────


class SendMessageRequest(BaseModel):
    """Request to send a message to a Slack channel."""

    channel: str
    text: str
    thread_ts: str | None = None


class SendMessageResponse(BaseModel):
    """Response from sending a Slack message."""

    ok: bool
    channel: str
    ts: str | None = None
    error: str | None = None
    sent_at: datetime


class ListChannelsResponse(BaseModel):
    """Response listing available Slack channels."""

    channels: list[dict[str, Any]]
    ok: bool
    retrieved_at: datetime


# ── Core Functions (called by both MCP and Python) ─────────


async def send_message(
    request: SendMessageRequest,
    http_client: httpx.AsyncClient | None = None,
    token: str | None = None,
) -> SendMessageResponse:
    """
    Send a message to a Slack channel.

    Uses the Slack Web API chat.postMessage endpoint.
    Supports threading via thread_ts parameter.

    Args:
        request: The message to send.
        http_client: Optional httpx client (for testing).
        token: Optional token override (for testing).
    """
    bot_token = token or _get_token()

    payload: dict[str, str] = {
        "channel": request.channel,
        "text": request.text,
    }
    if request.thread_ts:
        payload["thread_ts"] = request.thread_ts

    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json",
    }

    try:
        if http_client:
            response = await http_client.post(
                f"{SLACK_API_URL}/chat.postMessage",
                json=payload,
                headers=headers,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{SLACK_API_URL}/chat.postMessage",
                    json=payload,
                    headers=headers,
                )

        data = response.json()

        return SendMessageResponse(
            ok=data.get("ok", False),
            channel=request.channel,
            ts=data.get("ts"),
            error=data.get("error"),
            sent_at=datetime.now(timezone.utc),
        )

    except httpx.HTTPError as e:
        logger.error(f"Slack API error: {e}")
        return SendMessageResponse(
            ok=False,
            channel=request.channel,
            error=f"HTTP error: {e}",
            sent_at=datetime.now(timezone.utc),
        )


async def list_channels(
    http_client: httpx.AsyncClient | None = None,
    token: str | None = None,
) -> ListChannelsResponse:
    """
    List Slack channels accessible by the bot.

    Returns channel IDs and names for use in send_message.
    """
    bot_token = token or _get_token()
    headers = {"Authorization": f"Bearer {bot_token}"}

    try:
        if http_client:
            response = await http_client.get(
                f"{SLACK_API_URL}/conversations.list",
                headers=headers,
                params={"types": "public_channel,private_channel", "limit": 200},
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{SLACK_API_URL}/conversations.list",
                    headers=headers,
                    params={"types": "public_channel,private_channel", "limit": 200},
                )

        data = response.json()

        channels = [
            {"id": ch["id"], "name": ch["name"]}
            for ch in data.get("channels", [])
        ]

        return ListChannelsResponse(
            channels=channels,
            ok=data.get("ok", False),
            retrieved_at=datetime.now(timezone.utc),
        )

    except httpx.HTTPError as e:
        logger.error(f"Slack API error: {e}")
        return ListChannelsResponse(
            channels=[],
            ok=False,
            retrieved_at=datetime.now(timezone.utc),
        )


# ── MCP Server Registration ───────────────────────────────

try:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("slack-notify")

    @server.tool()
    async def mcp_send_message(
        channel: str, text: str, thread_ts: str | None = None
    ) -> str:
        """Send a message to a Slack channel."""
        req = SendMessageRequest(
            channel=channel, text=text, thread_ts=thread_ts
        )
        result = await send_message(req)
        return result.model_dump_json()

    @server.tool()
    async def mcp_list_channels() -> str:
        """List Slack channels accessible by the bot."""
        result = await list_channels()
        return result.model_dump_json()

except ImportError:
    server = None
