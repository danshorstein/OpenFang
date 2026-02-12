"""
Pipeline Executor — Runs deployed Python pipelines.

Each pipeline is a Python module with a standard entry point:
    async def run(context: PipelineContext) -> PipelineResult

The executor handles scheduling, logging, error capture,
and escalation flagging.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

logger = logging.getLogger("openfang.executor")


@dataclass
class PipelineContext:
    """Context passed to every pipeline execution."""

    automation_id: str
    run_at: datetime
    config: dict[str, Any] = field(default_factory=dict)

    def success(self, summary: str) -> "PipelineResult":
        """Create a successful result."""
        return PipelineResult(status="success", summary=summary)

    def failure(self, summary: str, error: str | None = None) -> "PipelineResult":
        """Create a failure result."""
        return PipelineResult(status="failure", summary=summary, error=error)


@dataclass
class PipelineResult:
    """Result returned from a pipeline execution."""

    status: str  # "success" | "failure" | "partial"
    summary: str
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class PipelineExecutor:
    """
    Executes deployed Python pipelines.

    Each pipeline is a Python module with a standard entry point:
        async def run(context: PipelineContext) -> PipelineResult

    The executor handles loading, execution, logging, error capture,
    and escalation flagging.
    """

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    async def execute(self, automation_id: str) -> dict[str, Any]:
        """Execute a pipeline by its automation ID."""
        automation = self.registry.get(automation_id)
        if not automation:
            raise ValueError(f"Unknown automation: {automation_id}")

        start_time = datetime.now(timezone.utc)
        context = PipelineContext(
            automation_id=automation_id,
            run_at=start_time,
            config=automation.get("config", {}),
        )

        try:
            module = import_module(automation["pipeline_module"])
            result = await module.run(context)

            runtime_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            self.registry.log_run(
                automation_id=automation_id,
                status=result.status,
                runtime_ms=runtime_ms,
                output_summary=result.summary,
            )

            logger.info(f"[{automation_id}] completed in {runtime_ms:.0f}ms")
            return {"status": result.status, "runtime_ms": runtime_ms}

        except Exception as e:
            runtime_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            self.registry.log_run(
                automation_id=automation_id,
                status="failure",
                runtime_ms=runtime_ms,
                error_detail=str(e),
            )

            logger.error(f"[{automation_id}] FAILED: {e}")
            self.registry.flag_for_review(automation_id, str(e))

            return {"status": "failure", "error": str(e)}
