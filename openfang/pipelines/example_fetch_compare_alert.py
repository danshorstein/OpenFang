"""
Example Pipeline: Fetch, Compare, and Alert

A reference pipeline demonstrating a more complex pattern:
fetch data, compare against stored thresholds, and send
an alert if conditions are met.

Created: Reference implementation
Schedule: Every 30 minutes (*/30 * * * *)
MCP servers: brave-search, database, slack-notify
"""

from datetime import datetime, timezone

from openfang.mcp_servers.brave_search.server import SearchRequest, search
from openfang.mcp_servers.database.server import QueryRequest, InsertRequest, insert, query
from openfang.mcp_servers.slack_notify.server import SendMessageRequest, send_message
from openfang.orchestration.executor import PipelineContext, PipelineResult
from openfang.orchestration.log_aggregator import pipeline_logger

logger = pipeline_logger("example_fetch_compare_alert")


async def run(context: PipelineContext) -> PipelineResult:
    """
    Fetch search results, compare against previous count, alert on changes.

    Config params:
        search_query: The query to monitor.
        alert_channel: Slack channel for alerts.
        threshold_delta: Minimum change to trigger alert (default: 5).
    """
    search_query = context.config.get("search_query", "OpenFang")
    alert_channel = context.config.get("alert_channel", "#alerts")
    threshold = context.config.get("threshold_delta", 5)

    # Step 1: Fetch current results
    logger.info(f"Monitoring search results for: {search_query}")
    current = await search(SearchRequest(query=search_query, count=20))
    current_count = current.total_count

    # Step 2: Get previous count from database
    previous_records = await query(QueryRequest(
        table="monitoring_snapshots",
        where={"query": search_query},
        order_by="fetched_at DESC",
        limit=1,
    ))

    previous_count = (
        previous_records.rows[0]["result_count"]
        if previous_records.rows
        else current_count
    )

    # Step 3: Store current snapshot
    await insert(InsertRequest(
        table="monitoring_snapshots",
        data={
            "query": search_query,
            "result_count": current_count,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    ))

    # Step 4: Compare and alert if threshold exceeded
    delta = abs(current_count - previous_count)
    if delta >= threshold:
        direction = "increased" if current_count > previous_count else "decreased"
        message = (
            f"Search results for '{search_query}' {direction} "
            f"by {delta} (was {previous_count}, now {current_count})"
        )

        await send_message(SendMessageRequest(
            channel=alert_channel,
            text=message,
        ))
        logger.info(f"Alert sent: {message}")
    else:
        logger.info(
            f"No significant change: {previous_count} → {current_count} "
            f"(delta {delta} < threshold {threshold})"
        )

    return context.success(
        summary=(
            f"Monitored '{search_query}': {current_count} results "
            f"(delta: {delta})"
        )
    )
