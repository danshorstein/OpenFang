"""
Orchestration Engine — The top-level entry point for OpenFang.

Wires together the executor, scheduler, log aggregator, and
registries into a single runnable system. This is what you
start when you want OpenFang running 24/7.
"""

import asyncio
import logging
import signal
from pathlib import Path
from typing import Any

from openfang.orchestration.executor import PipelineExecutor
from openfang.orchestration.log_aggregator import LogAggregator
from openfang.orchestration.scheduler import CronScheduler
from openfang.registry.automation_registry import AutomationRegistry

logger = logging.getLogger("openfang.engine")


class OrchestrationEngine:
    """
    The main orchestration engine for OpenFang.

    Manages the full lifecycle:
    1. Initialize the database and registries
    2. Start the cron scheduler
    3. Execute pipelines on schedule
    4. Log results and flag failures
    5. Shut down gracefully on signal

    Usage:
        engine = OrchestrationEngine()
        await engine.start()    # initializes + starts scheduler
        await engine.wait()     # blocks until shutdown signal
        await engine.stop()     # graceful shutdown
    """

    def __init__(
        self,
        db_path: str = "openfang_registry.db",
        log_dir: str = "logs",
    ) -> None:
        self.registry = AutomationRegistry(db_path=db_path)
        self.log_aggregator = LogAggregator(log_dir=log_dir)
        self.executor = PipelineExecutor(
            registry=self.registry,
            log_aggregator=self.log_aggregator,
        )
        self.scheduler = CronScheduler(
            executor=self.executor,
            registry=self.registry,
        )
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Initialize the database and start the scheduler."""
        await self.registry.initialize()
        logger.info("Registry initialized")

        await self.scheduler.start()
        logger.info("OpenFang orchestration engine started")

    async def stop(self) -> None:
        """Shut down the scheduler and clean up."""
        await self.scheduler.stop()
        logger.info("OpenFang orchestration engine stopped")

    async def wait(self) -> None:
        """Block until a shutdown signal is received."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown_event.set)
        logger.info("Waiting for shutdown signal (Ctrl+C)...")
        await self._shutdown_event.wait()

    async def run_forever(self) -> None:
        """Start, wait for shutdown, then stop. Main entry point."""
        await self.start()
        try:
            await self.wait()
        finally:
            await self.stop()

    # --- Convenience methods for managing automations ---

    async def register_automation(
        self,
        id: str,
        name: str,
        description: str,
        pipeline_file: str,
        cron_schedule: str | None = None,
        mcp_servers: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Register a new automation and schedule it if a cron expression is given."""
        await self.registry.register(
            id=id,
            name=name,
            description=description,
            pipeline_file=pipeline_file,
            cron_schedule=cron_schedule,
            mcp_servers=mcp_servers,
        )
        if cron_schedule:
            self.scheduler.add_automation(id, cron_schedule)
        logger.info(f"Registered automation: {id}")

    async def run_now(self, automation_id: str) -> dict[str, Any]:
        """Execute a registered automation immediately (outside of schedule)."""
        return await self.executor.execute(automation_id)

    async def run_file(
        self,
        pipeline_file: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a pipeline file directly without registering it."""
        return await self.executor.execute_file(pipeline_file, config=config)

    async def list_automations(self) -> list[dict[str, Any]]:
        """List all registered automations."""
        return await self.registry.list_all()

    async def list_active(self) -> list[dict[str, Any]]:
        """List active automations."""
        return await self.registry.list_active()

    async def get_status(self, automation_id: str) -> dict[str, Any] | None:
        """Get the status of a specific automation."""
        automation = await self.registry.get(automation_id)
        if not automation:
            return None
        next_run = self.scheduler.get_next_run(automation_id)
        return {
            **automation,
            "next_run": next_run,
            "scheduled": automation_id in self.scheduler.job_ids,
        }

    async def pause(self, automation_id: str) -> None:
        """Pause an automation."""
        await self.registry.update_status(automation_id, "paused")
        self.scheduler.pause_automation(automation_id)

    async def resume(self, automation_id: str) -> None:
        """Resume a paused automation."""
        await self.registry.update_status(automation_id, "active")
        self.scheduler.resume_automation(automation_id)

    async def get_run_history(
        self, automation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get execution history for an automation."""
        return await self.registry.get_run_history(automation_id, limit=limit)
