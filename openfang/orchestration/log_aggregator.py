"""
Log Aggregator — Structured logging for pipeline executions.

Collects execution logs from all pipelines in structured
JSON format. Feeds into LLM review cycles and the
dashboard health view.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("openfang.log_aggregator")


@dataclass
class PipelineLog:
    """A single structured log entry from a pipeline execution."""

    automation_id: str
    run_at: datetime
    status: str  # "success" | "failure" | "partial"
    runtime_ms: float
    output_summary: str | None = None
    error_detail: str | None = None
    llm_tokens_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class LogAggregator:
    """
    Collects and stores structured execution logs from all pipelines.

    Logs are stored as JSON lines for easy parsing and analysis
    by both the LLM supervisor and the web dashboard.
    """

    def __init__(self, log_dir: str = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, entry: PipelineLog) -> None:
        """Write a structured log entry."""
        log_file = self.log_dir / f"{entry.run_at.strftime('%Y-%m-%d')}.jsonl"

        log_data = asdict(entry)
        log_data["run_at"] = entry.run_at.isoformat()

        with open(log_file, "a") as f:
            f.write(json.dumps(log_data) + "\n")

        logger.debug(
            f"Logged [{entry.automation_id}] {entry.status} "
            f"in {entry.runtime_ms:.0f}ms"
        )

    def get_logs(
        self,
        date: datetime | None = None,
        automation_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[PipelineLog]:
        """
        Retrieve structured logs with optional filtering.

        Args:
            date: Filter to a specific date (defaults to today).
            automation_id: Filter to a specific automation.
            status: Filter by status (success/failure/partial).
            limit: Maximum number of entries to return.
        """
        if date is None:
            date = datetime.now(timezone.utc)

        log_file = self.log_dir / f"{date.strftime('%Y-%m-%d')}.jsonl"
        if not log_file.exists():
            return []

        entries: list[PipelineLog] = []
        with open(log_file) as f:
            for line in f:
                data = json.loads(line.strip())
                data["run_at"] = datetime.fromisoformat(data["run_at"])

                if automation_id and data["automation_id"] != automation_id:
                    continue
                if status and data["status"] != status:
                    continue

                entries.append(PipelineLog(**data))
                if len(entries) >= limit:
                    break

        return entries

    def get_unreviewed_count(self) -> int:
        """Get the count of log entries not yet reviewed by the LLM supervisor."""
        # TODO: Integrate with registry to track review status
        return 0


def pipeline_logger(name: str) -> logging.Logger:
    """
    Create a logger for a specific pipeline.

    This is a convenience function used by pipeline scripts
    to get a properly namespaced logger.
    """
    return logging.getLogger(f"openfang.pipeline.{name}")
