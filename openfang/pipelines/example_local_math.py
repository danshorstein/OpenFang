"""
Example Pipeline: Local Math

A simple pipeline that requires zero external APIs.
Computes some stats and returns a result. Perfect for
testing that the executor and scheduler actually work.

Created: Reference implementation
Schedule: Every minute (* * * * *)
MCP servers: (none)
"""

import statistics

from openfang.orchestration.executor import PipelineContext, PipelineResult
from openfang.orchestration.log_aggregator import pipeline_logger

logger = pipeline_logger("example_local_math")


async def run(context: PipelineContext) -> PipelineResult:
    """
    Compute basic statistics on a list of numbers.

    Config params:
        numbers: List of numbers to analyze (default: [1, 2, 3, 4, 5]).
    """
    numbers = context.config.get("numbers", [1, 2, 3, 4, 5])

    if not numbers:
        return context.failure(summary="No numbers provided", error="empty input")

    mean = statistics.mean(numbers)
    median = statistics.median(numbers)
    stdev = statistics.stdev(numbers) if len(numbers) > 1 else 0.0
    total = sum(numbers)

    logger.info(f"Computed stats for {len(numbers)} numbers: mean={mean}, median={median}")

    return context.success(
        summary=(
            f"Stats for {len(numbers)} numbers: "
            f"mean={mean:.2f}, median={median:.2f}, "
            f"stdev={stdev:.2f}, sum={total}"
        )
    )
