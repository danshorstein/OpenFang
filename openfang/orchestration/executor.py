"""
Pipeline Executor — Runs deployed Python pipelines.

Each pipeline is a Python module with a standard entry point:
    async def run(context: PipelineContext) -> PipelineResult

The executor handles loading, execution, logging, error capture,
and escalation flagging.
"""

import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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


def _load_pipeline_module(pipeline_file: str) -> Any:
    """Load a pipeline module from a file path or dotted module path.

    Supports two forms:
        - File path: "openfang/pipelines/example_fetch_and_store.py"
        - Module path: "openfang.pipelines.example_fetch_and_store"
    """
    path = Path(pipeline_file)
    if path.exists() and path.suffix == ".py":
        module_name = f"openfang_pipeline_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec from: {pipeline_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    # Fall back to dotted module import
    return importlib.import_module(pipeline_file)


class PipelineExecutor:
    """
    Executes deployed Python pipelines.

    Each pipeline is a Python module with a standard entry point:
        async def run(context: PipelineContext) -> PipelineResult

    The executor handles loading, execution, logging, error capture,
    and escalation flagging.
    """

    def __init__(self, registry: Any, log_aggregator: Any | None = None) -> None:
        self.registry = registry
        self.log_aggregator = log_aggregator

    async def execute(self, automation_id: str) -> dict[str, Any]:
        """Execute a pipeline by its automation ID."""
        automation = await self.registry.get(automation_id)
        if not automation:
            raise ValueError(f"Unknown automation: {automation_id}")

        start_time = datetime.now(timezone.utc)
        context = PipelineContext(
            automation_id=automation_id,
            run_at=start_time,
            config=automation.get("config", {}) or {},
        )

        # Determine what to load — pipeline_file or pipeline_module
        pipeline_ref = automation.get("pipeline_file") or automation.get(
            "pipeline_module"
        )
        if not pipeline_ref:
            raise ValueError(
                f"Automation {automation_id} has no pipeline_file or pipeline_module"
            )

        try:
            module = _load_pipeline_module(pipeline_ref)
            result = await module.run(context)

            runtime_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            await self.registry.log_run(
                automation_id=automation_id,
                status=result.status,
                runtime_ms=runtime_ms,
                output_summary=result.summary,
            )

            self._write_log(
                automation_id=automation_id,
                run_at=start_time,
                status=result.status,
                runtime_ms=runtime_ms,
                output_summary=result.summary,
            )

            logger.info(
                f"[{automation_id}] {result.status} in {runtime_ms:.0f}ms — "
                f"{result.summary}"
            )
            return {
                "status": result.status,
                "summary": result.summary,
                "runtime_ms": runtime_ms,
            }

        except Exception as e:
            runtime_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            await self.registry.log_run(
                automation_id=automation_id,
                status="failure",
                runtime_ms=runtime_ms,
                error_detail=str(e),
            )

            self._write_log(
                automation_id=automation_id,
                run_at=start_time,
                status="failure",
                runtime_ms=runtime_ms,
                error_detail=str(e),
            )

            logger.error(f"[{automation_id}] FAILED in {runtime_ms:.0f}ms: {e}")
            await self.registry.flag_for_review(automation_id, str(e))

            return {"status": "failure", "error": str(e), "runtime_ms": runtime_ms}

    async def execute_file(
        self,
        pipeline_file: str,
        config: dict[str, Any] | None = None,
        automation_id: str = "manual-run",
    ) -> dict[str, Any]:
        """Execute a pipeline directly from a file path (without registry lookup).

        Useful for manual/ad-hoc runs and testing.
        """
        start_time = datetime.now(timezone.utc)
        context = PipelineContext(
            automation_id=automation_id,
            run_at=start_time,
            config=config or {},
        )

        try:
            module = _load_pipeline_module(pipeline_file)
            result = await module.run(context)

            runtime_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            self._write_log(
                automation_id=automation_id,
                run_at=start_time,
                status=result.status,
                runtime_ms=runtime_ms,
                output_summary=result.summary,
            )

            logger.info(
                f"[{automation_id}] {result.status} in {runtime_ms:.0f}ms — "
                f"{result.summary}"
            )
            return {
                "status": result.status,
                "summary": result.summary,
                "runtime_ms": runtime_ms,
            }

        except Exception as e:
            runtime_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            self._write_log(
                automation_id=automation_id,
                run_at=start_time,
                status="failure",
                runtime_ms=runtime_ms,
                error_detail=str(e),
            )

            logger.error(f"[{automation_id}] FAILED in {runtime_ms:.0f}ms: {e}")
            return {"status": "failure", "error": str(e), "runtime_ms": runtime_ms}

    def _write_log(self, **kwargs: Any) -> None:
        """Write to the log aggregator if available."""
        if self.log_aggregator is None:
            return
        from openfang.orchestration.log_aggregator import PipelineLog

        self.log_aggregator.log(PipelineLog(**kwargs))
