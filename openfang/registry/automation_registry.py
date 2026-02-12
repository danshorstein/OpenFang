"""
Automation Registry — SQLite-backed store for deployed automations.

Tracks every automation's status, schedule, run history, and costs.
Provides the source of truth for what's running, what's failed,
and what needs attention.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger("openfang.registry.automation")

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class AutomationRegistry:
    """
    SQLite-backed automation registry.

    Manages the lifecycle of deployed automations:
    - Registration of new automations
    - Status tracking (active, paused, error, deprecated)
    - Run logging and history
    - Flagging for LLM review
    """

    def __init__(self, db_path: str = "openfang_registry.db") -> None:
        self.db_path = db_path

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        schema = SCHEMA_PATH.read_text()
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(schema)
            await db.commit()
        logger.info("Registry database initialized")

    async def register(
        self,
        id: str,
        name: str,
        description: str,
        pipeline_file: str,
        cron_schedule: str | None = None,
        mcp_servers: list[str] | None = None,
        created_by: str = "llm:sonnet",
    ) -> None:
        """Register a new automation in the registry."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO automations
                   (id, name, description, pipeline_file, cron_schedule,
                    mcp_servers, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    id,
                    name,
                    description,
                    pipeline_file,
                    cron_schedule,
                    json.dumps(mcp_servers or []),
                    created_by,
                ),
            )
            await db.commit()
        logger.info(f"Registered automation: {id}")

    async def get(self, automation_id: str) -> dict[str, Any] | None:
        """Get a single automation by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM automations WHERE id = ?", (automation_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def list_active(self) -> list[dict[str, Any]]:
        """List all active automations."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM automations WHERE status = 'active' ORDER BY name"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def list_all(self) -> list[dict[str, Any]]:
        """List all automations regardless of status."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM automations ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def update_status(self, automation_id: str, status: str) -> None:
        """Update an automation's status."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE automations SET status = ? WHERE id = ?",
                (status, automation_id),
            )
            await db.commit()

    async def log_run(
        self,
        automation_id: str,
        status: str,
        runtime_ms: float,
        output_summary: str | None = None,
        error_detail: str | None = None,
        llm_tokens_used: int = 0,
    ) -> None:
        """Log a pipeline execution run."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO automation_logs
                   (automation_id, status, runtime_ms, output_summary,
                    error_detail, llm_tokens_used)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    automation_id,
                    status,
                    int(runtime_ms),
                    output_summary,
                    error_detail,
                    llm_tokens_used,
                ),
            )
            # Update automation record
            await db.execute(
                """UPDATE automations SET
                   last_run_at = ?,
                   last_run_status = ?,
                   last_error = ?,
                   run_count = run_count + 1
                   WHERE id = ?""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    error_detail,
                    automation_id,
                ),
            )
            await db.commit()

    async def flag_for_review(
        self, automation_id: str, reason: str
    ) -> None:
        """Flag an automation for LLM supervisor review."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE automations SET
                   flagged = TRUE, flag_reason = ?
                   WHERE id = ?""",
                (reason, automation_id),
            )
            await db.commit()
        logger.warning(f"Flagged {automation_id} for review: {reason}")

    async def get_flagged(self) -> list[dict[str, Any]]:
        """Get all automations flagged for review."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM automations WHERE flagged = TRUE"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def resolve_flag(self, automation_id: str) -> None:
        """Clear the review flag on an automation."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE automations SET
                   flagged = FALSE, flag_reason = NULL
                   WHERE id = ?""",
                (automation_id,),
            )
            await db.commit()

    async def get_run_history(
        self, automation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get recent run history for an automation."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM automation_logs
                   WHERE automation_id = ?
                   ORDER BY run_at DESC LIMIT ?""",
                (automation_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
