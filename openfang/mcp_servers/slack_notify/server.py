"""
Slack Notify MCP Server

Sends messages to Slack channels via the Slack Web API.
Supports plain text and block-formatted messages.

Requires SLACK_BOT_TOKEN environment variable.
"""

import os
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel


# ── Configuration ──────────────────────────────────────────

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_API_URL = "https://slack.com/api"


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


# ── Core Functions (called by both MCP and Python) ─────────


async def send_message(request: SendMessageRequest) -> SendMessageResponse:
    """
    Send a message to a Slack channel.

    Uses the Slack Web API chat.postMessage endpoint.
    Supports threading via thread_ts parameter.
    """
    payload: dict[str, str] = {
        "channel": request.channel,
        "text": request.text,
    }
    if request.thread_ts:
        payload["thread_ts"] = request.thread_ts

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SLACK_API_URL}/chat.postMessage",
            json=payload,
            headers={
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        data = response.json()

    return SendMessageResponse(
        ok=data.get("ok", False),
        channel=request.channel,
        ts=data.get("ts"),
        error=data.get("error"),
        sent_at=datetime.now(timezone.utc),
    )


# ── MCP Server Registration ───────────────────────────────

try:
    from mcp.server import Server

    server = Server("slack-notify")

    @server.tool()
    async def mcp_send_message(
        channel: str, text: str, thread_ts: str | None = None
    ) -> str:
        """Send a message to a Slack channel."""
        request = SendMessageRequest(
            channel=channel, text=text, thread_ts=thread_ts
        )
        result = await send_message(request)
        return result.model_dump_json()

except ImportError:
    server = None
