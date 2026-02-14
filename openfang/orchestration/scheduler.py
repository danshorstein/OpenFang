"""
Cron Scheduler — Manages scheduled execution of pipelines.

Wraps APScheduler to provide cron-based scheduling for
deployed automation pipelines. Integrates with the
AutomationRegistry to discover and manage schedules.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("openfang.scheduler")


def _parse_cron(cron_expr: str) -> dict[str, str] | None:
    """Parse a 5-field cron expression into APScheduler trigger kwargs.

    Returns None if the expression is invalid.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return None
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


class CronScheduler:
    """
    Manages cron-based scheduling for automation pipelines.

    Uses APScheduler under the hood. Schedules are defined
    using standard cron expressions and stored in the
    AutomationRegistry.
    """

    def __init__(self, executor: Any, registry: Any) -> None:
        self.executor = executor
        self.registry = registry
        self._scheduler: Any = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def job_ids(self) -> list[str]:
        """List IDs of all scheduled jobs."""
        if not self._scheduler:
            return []
        return [job.id for job in self._scheduler.get_jobs()]

    async def start(self) -> None:
        """Start the scheduler and load all active automation schedules."""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        self._scheduler = AsyncIOScheduler()

        # Load schedules from the registry (async)
        automations = await self.registry.list_active()
        loaded = 0
        for automation in automations:
            cron_schedule = automation.get("cron_schedule")
            if cron_schedule:
                added = self._add_job(automation["id"], cron_schedule)
                if added:
                    loaded += 1

        self._scheduler.start()
        self._running = True
        logger.info(
            f"Scheduler started with {loaded} scheduled automations "
            f"(of {len(automations)} active)"
        )

    def _add_job(self, automation_id: str, cron_schedule: str) -> bool:
        """Add a single automation job to the scheduler. Returns True if added."""
        from apscheduler.triggers.cron import CronTrigger

        cron_kwargs = _parse_cron(cron_schedule)
        if not cron_kwargs:
            logger.warning(
                f"Invalid cron schedule for {automation_id}: {cron_schedule}"
            )
            return False

        trigger = CronTrigger(**cron_kwargs)

        # APScheduler expects a sync callable; wrap async execute
        def _run_pipeline() -> None:
            loop = asyncio.get_event_loop()
            asyncio.ensure_future(self.executor.execute(automation_id))

        self._scheduler.add_job(
            _run_pipeline,
            trigger=trigger,
            id=automation_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled {automation_id} with cron: {cron_schedule}")
        return True

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Scheduler stopped")

    def add_automation(self, automation_id: str, cron_schedule: str) -> bool:
        """Add or update a scheduled automation at runtime. Returns True if added."""
        if not self._scheduler:
            logger.warning("Scheduler not started — cannot add job")
            return False
        return self._add_job(automation_id, cron_schedule)

    def remove_automation(self, automation_id: str) -> None:
        """Remove a scheduled automation."""
        if self._scheduler:
            try:
                self._scheduler.remove_job(automation_id)
                logger.info(f"Removed schedule for {automation_id}")
            except Exception:
                logger.warning(f"Job {automation_id} not found in scheduler")

    def pause_automation(self, automation_id: str) -> None:
        """Pause a scheduled automation."""
        if self._scheduler:
            self._scheduler.pause_job(automation_id)
            logger.info(f"Paused {automation_id}")

    def resume_automation(self, automation_id: str) -> None:
        """Resume a paused automation."""
        if self._scheduler:
            self._scheduler.resume_job(automation_id)
            logger.info(f"Resumed {automation_id}")

    def get_next_run(self, automation_id: str) -> str | None:
        """Get the next scheduled run time for an automation."""
        if not self._scheduler:
            return None
        try:
            job = self._scheduler.get_job(automation_id)
            if job and job.next_run_time:
                return job.next_run_time.isoformat()
        except Exception:
            pass
        return None
