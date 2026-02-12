"""
Example Pipeline: Fetch and Store

A reference pipeline demonstrating the simplest pattern:
fetch data from an external source and store it in the database.

Created: Reference implementation
Schedule: Every 4 hours (0 */4 * * *)
MCP servers: brave-search, database
"""

from datetime import datetime, timezone

from openfang.mcp_servers.brave_search.server import SearchRequest, search
from openfang.mcp_servers.database.server import InsertRequest, insert
from openfang.orchestration.executor import PipelineContext, PipelineResult
from openfang.orchestration.log_aggregator import pipeline_logger

logger = pipeline_logger("example_fetch_and_store")


async def run(context: PipelineContext) -> PipelineResult:
    """
    Fetch search results for a configured query and store them.

    Config params:
        search_query: The query to search for.
        result_count: Number of results to fetch (default: 5).
    """
    query = context.config.get("search_query", "OpenFang automation framework")
    count = context.config.get("result_count", 5)

    # Step 1: Search the web
    logger.info(f"Searching for: {query}")
    results = await search(SearchRequest(query=query, count=count))
    logger.info(f"Got {results.total_count} results")

    # Step 2: Store each result
    stored = 0
    for result in results.results:
        await insert(InsertRequest(
            table="search_results",
            data={
                "query": query,
                "title": result.title,
                "url": result.url,
                "description": result.description,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
        ))
        stored += 1

    logger.info(f"Stored {stored} results")
    return context.success(
        summary=f"Fetched and stored {stored} results for '{query}'"
    )
