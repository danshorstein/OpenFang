"""
Cron Scheduler — Manages scheduled execution of pipelines.

Wraps APScheduler to provide cron-based scheduling for
deployed automation pipelines. Integrates with the
AutomationRegistry to discover and manage schedules.
"""

import logging
from typing import Any

logger = logging.getLogger("openfang.scheduler")


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

    async def start(self) -> None:
        """
        Start the scheduler and load all active automation schedules.

        Reads cron schedules from the registry and registers them
        with APScheduler.
        """
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        self._scheduler = AsyncIOScheduler()

        automations = self.registry.list_active()
        for automation in automations:
            if automation.get("cron_schedule"):
                self._add_job(automation, CronTrigger)

        self._scheduler.start()
        logger.info(
            f"Scheduler started with {len(automations)} active automations"
        )

    def _add_job(self, automation: dict[str, Any], trigger_class: type) -> None:
        """Add a single automation job to the scheduler."""
        cron_parts = automation["cron_schedule"].split()
        if len(cron_parts) != 5:
            logger.warning(
                f"Invalid cron schedule for {automation['id']}: "
                f"{automation['cron_schedule']}"
            )
            return

        trigger = trigger_class(
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
        )

        self._scheduler.add_job(
            self.executor.execute,
            trigger=trigger,
            args=[automation["id"]],
            id=automation["id"],
            replace_existing=True,
        )
        logger.info(
            f"Scheduled {automation['id']} with cron: {automation['cron_schedule']}"
        )

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")

    def add_automation(self, automation_id: str, cron_schedule: str) -> None:
        """Add or update a scheduled automation at runtime."""
        from apscheduler.triggers.cron import CronTrigger

        automation = {
            "id": automation_id,
            "cron_schedule": cron_schedule,
        }
        self._add_job(automation, CronTrigger)

    def remove_automation(self, automation_id: str) -> None:
        """Remove a scheduled automation."""
        if self._scheduler:
            self._scheduler.remove_job(automation_id)
            logger.info(f"Removed schedule for {automation_id}")

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
