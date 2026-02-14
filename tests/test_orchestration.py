"""Tests for the Phase 3 Orchestration Engine.

Covers:
- PipelineExecutor: async execution, file loading, error handling, log aggregator integration
- CronScheduler: cron parsing, job management, lifecycle
- LogAggregator: write/read structured logs, filtering
- OrchestrationEngine: full integration wiring
- CLI: argument parsing
"""

import json
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openfang.orchestration.executor import (
    PipelineContext,
    PipelineExecutor,
    PipelineResult,
    _load_pipeline_module,
)
from openfang.orchestration.log_aggregator import LogAggregator, PipelineLog
from openfang.orchestration.scheduler import CronScheduler, _parse_cron


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def good_pipeline(tmp_dir):
    """Create a minimal working pipeline file."""
    p = tmp_dir / "good_pipeline.py"
    p.write_text(
        textwrap.dedent("""\
        from openfang.orchestration.executor import PipelineContext, PipelineResult

        async def run(context):
            numbers = context.config.get("numbers", [1, 2, 3])
            total = sum(numbers)
            return context.success(summary=f"sum={total}")
        """)
    )
    return str(p)


@pytest.fixture
def failing_pipeline(tmp_dir):
    """Create a pipeline that always raises."""
    p = tmp_dir / "failing_pipeline.py"
    p.write_text(
        textwrap.dedent("""\
        async def run(context):
            raise RuntimeError("Intentional failure for testing")
        """)
    )
    return str(p)


@pytest.fixture
def slow_pipeline(tmp_dir):
    """Create a pipeline that takes measurable time."""
    p = tmp_dir / "slow_pipeline.py"
    p.write_text(
        textwrap.dedent("""\
        import asyncio
        from openfang.orchestration.executor import PipelineContext, PipelineResult

        async def run(context):
            await asyncio.sleep(0.05)
            return context.success(summary="done after delay")
        """)
    )
    return str(p)


@pytest.fixture
def bad_import_pipeline(tmp_dir):
    """Create a pipeline with an import error."""
    p = tmp_dir / "bad_import.py"
    p.write_text("import nonexistent_module_xyz\n")
    return str(p)


@pytest.fixture
def mock_registry():
    """Create a mock AutomationRegistry with async methods."""
    registry = AsyncMock()
    registry.get = AsyncMock(return_value=None)
    registry.list_active = AsyncMock(return_value=[])
    registry.list_all = AsyncMock(return_value=[])
    registry.log_run = AsyncMock()
    registry.flag_for_review = AsyncMock()
    registry.update_status = AsyncMock()
    registry.initialize = AsyncMock()
    registry.register = AsyncMock()
    registry.get_run_history = AsyncMock(return_value=[])
    return registry


@pytest.fixture
def log_aggregator(tmp_dir):
    return LogAggregator(log_dir=str(tmp_dir / "logs"))


@pytest.fixture
def executor(mock_registry, log_aggregator):
    return PipelineExecutor(registry=mock_registry, log_aggregator=log_aggregator)


# ---------------------------------------------------------------------------
# PipelineContext & PipelineResult (extended from existing tests)
# ---------------------------------------------------------------------------


class TestPipelineContext:
    def test_success_creates_result(self) -> None:
        ctx = PipelineContext(
            automation_id="test-001",
            run_at=datetime.now(timezone.utc),
        )
        result = ctx.success(summary="All good")
        assert isinstance(result, PipelineResult)
        assert result.status == "success"
        assert result.summary == "All good"
        assert result.error is None

    def test_failure_creates_result(self) -> None:
        ctx = PipelineContext(
            automation_id="test-001",
            run_at=datetime.now(timezone.utc),
        )
        result = ctx.failure(summary="Something broke", error="ConnectionError")
        assert isinstance(result, PipelineResult)
        assert result.status == "failure"
        assert result.error == "ConnectionError"

    def test_config_defaults_to_empty_dict(self) -> None:
        ctx = PipelineContext(
            automation_id="test-001",
            run_at=datetime.now(timezone.utc),
        )
        assert ctx.config == {}

    def test_config_is_accessible(self) -> None:
        ctx = PipelineContext(
            automation_id="test-001",
            run_at=datetime.now(timezone.utc),
            config={"key": "value"},
        )
        assert ctx.config["key"] == "value"


class TestPipelineResult:
    def test_data_defaults_to_empty(self) -> None:
        r = PipelineResult(status="success", summary="ok")
        assert r.data == {}

    def test_data_is_stored(self) -> None:
        r = PipelineResult(status="success", summary="ok", data={"count": 42})
        assert r.data["count"] == 42


# ---------------------------------------------------------------------------
# Pipeline Module Loading
# ---------------------------------------------------------------------------


class TestLoadPipelineModule:
    def test_load_from_file_path(self, good_pipeline) -> None:
        module = _load_pipeline_module(good_pipeline)
        assert hasattr(module, "run")

    def test_load_nonexistent_file_falls_back_to_import(self) -> None:
        with pytest.raises((ImportError, ModuleNotFoundError)):
            _load_pipeline_module("nonexistent.module.path")

    def test_load_with_import_error(self, bad_import_pipeline) -> None:
        with pytest.raises(ModuleNotFoundError):
            _load_pipeline_module(bad_import_pipeline)


# ---------------------------------------------------------------------------
# PipelineExecutor — execute_file (no registry needed)
# ---------------------------------------------------------------------------


class TestExecutorRunFile:
    async def test_execute_good_pipeline(self, executor, good_pipeline) -> None:
        result = await executor.execute_file(good_pipeline)
        assert result["status"] == "success"
        assert "sum=6" in result["summary"]
        assert result["runtime_ms"] >= 0

    async def test_execute_with_config(self, executor, good_pipeline) -> None:
        result = await executor.execute_file(
            good_pipeline, config={"numbers": [10, 20, 30]}
        )
        assert result["status"] == "success"
        assert "sum=60" in result["summary"]

    async def test_execute_failing_pipeline(self, executor, failing_pipeline) -> None:
        result = await executor.execute_file(failing_pipeline)
        assert result["status"] == "failure"
        assert "Intentional failure" in result["error"]
        assert result["runtime_ms"] >= 0

    async def test_execute_nonexistent_file(self, executor) -> None:
        result = await executor.execute_file("/nonexistent/pipeline.py")
        assert result["status"] == "failure"

    async def test_runtime_is_measured(self, executor, slow_pipeline) -> None:
        result = await executor.execute_file(slow_pipeline)
        assert result["status"] == "success"
        assert result["runtime_ms"] >= 40  # should be ~50ms

    async def test_writes_log_on_success(
        self, executor, log_aggregator, good_pipeline
    ) -> None:
        await executor.execute_file(good_pipeline)
        logs = log_aggregator.get_logs()
        assert len(logs) == 1
        assert logs[0].status == "success"

    async def test_writes_log_on_failure(
        self, executor, log_aggregator, failing_pipeline
    ) -> None:
        await executor.execute_file(failing_pipeline)
        logs = log_aggregator.get_logs()
        assert len(logs) == 1
        assert logs[0].status == "failure"
        assert logs[0].error_detail is not None


# ---------------------------------------------------------------------------
# PipelineExecutor — execute (registry-backed)
# ---------------------------------------------------------------------------


class TestExecutorRunRegistered:
    async def test_execute_registered_automation(
        self, executor, mock_registry, good_pipeline
    ) -> None:
        mock_registry.get.return_value = {
            "id": "auto-001",
            "pipeline_file": good_pipeline,
            "config": {"numbers": [5, 10]},
        }
        result = await executor.execute("auto-001")
        assert result["status"] == "success"
        assert "sum=15" in result["summary"]

        # Verify registry was called
        mock_registry.log_run.assert_called_once()
        call_kwargs = mock_registry.log_run.call_args
        assert call_kwargs.kwargs["automation_id"] == "auto-001"
        assert call_kwargs.kwargs["status"] == "success"

    async def test_execute_unknown_automation(self, executor) -> None:
        with pytest.raises(ValueError, match="Unknown automation"):
            await executor.execute("nonexistent-id")

    async def test_execute_flags_on_failure(
        self, executor, mock_registry, failing_pipeline
    ) -> None:
        mock_registry.get.return_value = {
            "id": "auto-fail",
            "pipeline_file": failing_pipeline,
        }
        result = await executor.execute("auto-fail")
        assert result["status"] == "failure"
        mock_registry.flag_for_review.assert_called_once()

    async def test_execute_with_pipeline_module_field(
        self, executor, mock_registry, good_pipeline
    ) -> None:
        # Supports pipeline_module as fallback field name
        mock_registry.get.return_value = {
            "id": "auto-002",
            "pipeline_module": good_pipeline,
        }
        result = await executor.execute("auto-002")
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Cron Parsing
# ---------------------------------------------------------------------------


class TestCronParsing:
    def test_valid_5_field_cron(self) -> None:
        result = _parse_cron("*/5 * * * *")
        assert result == {
            "minute": "*/5",
            "hour": "*",
            "day": "*",
            "month": "*",
            "day_of_week": "*",
        }

    def test_specific_cron(self) -> None:
        result = _parse_cron("0 8 * * 1-5")
        assert result["minute"] == "0"
        assert result["hour"] == "8"
        assert result["day_of_week"] == "1-5"

    def test_invalid_too_few_fields(self) -> None:
        assert _parse_cron("* *") is None

    def test_invalid_too_many_fields(self) -> None:
        assert _parse_cron("* * * * * *") is None

    def test_empty_string(self) -> None:
        assert _parse_cron("") is None

    def test_whitespace_handling(self) -> None:
        result = _parse_cron("  0  */4  *  *  *  ")
        assert result is not None
        assert result["hour"] == "*/4"


# ---------------------------------------------------------------------------
# CronScheduler
# ---------------------------------------------------------------------------


class TestCronScheduler:
    async def test_start_with_no_automations(self, executor, mock_registry) -> None:
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        await scheduler.start()
        assert scheduler.running is True
        assert scheduler.job_ids == []
        await scheduler.stop()
        assert scheduler.running is False

    async def test_start_loads_active_automations(
        self, executor, mock_registry
    ) -> None:
        mock_registry.list_active.return_value = [
            {"id": "auto-a", "cron_schedule": "*/5 * * * *"},
            {"id": "auto-b", "cron_schedule": "0 8 * * 1-5"},
        ]
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        await scheduler.start()

        assert scheduler.running is True
        assert "auto-a" in scheduler.job_ids
        assert "auto-b" in scheduler.job_ids
        await scheduler.stop()

    async def test_skips_invalid_cron(self, executor, mock_registry) -> None:
        mock_registry.list_active.return_value = [
            {"id": "auto-bad", "cron_schedule": "not a cron"},
        ]
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        await scheduler.start()
        assert "auto-bad" not in scheduler.job_ids
        await scheduler.stop()

    async def test_skips_automations_without_schedule(
        self, executor, mock_registry
    ) -> None:
        mock_registry.list_active.return_value = [
            {"id": "auto-manual", "cron_schedule": None},
        ]
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        await scheduler.start()
        assert scheduler.job_ids == []
        await scheduler.stop()

    async def test_add_automation_at_runtime(self, executor, mock_registry) -> None:
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        await scheduler.start()

        added = scheduler.add_automation("new-job", "*/10 * * * *")
        assert added is True
        assert "new-job" in scheduler.job_ids
        await scheduler.stop()

    async def test_remove_automation(self, executor, mock_registry) -> None:
        mock_registry.list_active.return_value = [
            {"id": "auto-rm", "cron_schedule": "*/5 * * * *"},
        ]
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        await scheduler.start()

        assert "auto-rm" in scheduler.job_ids
        scheduler.remove_automation("auto-rm")
        assert "auto-rm" not in scheduler.job_ids
        await scheduler.stop()

    async def test_remove_nonexistent_is_safe(self, executor, mock_registry) -> None:
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        await scheduler.start()
        scheduler.remove_automation("does-not-exist")  # should not raise
        await scheduler.stop()

    async def test_get_next_run(self, executor, mock_registry) -> None:
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        await scheduler.start()
        scheduler.add_automation("future-job", "0 0 * * *")  # midnight daily
        next_run = scheduler.get_next_run("future-job")
        assert next_run is not None
        await scheduler.stop()

    async def test_get_next_run_nonexistent(self, executor, mock_registry) -> None:
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        await scheduler.start()
        assert scheduler.get_next_run("nope") is None
        await scheduler.stop()

    def test_add_before_start_returns_false(self, executor, mock_registry) -> None:
        scheduler = CronScheduler(executor=executor, registry=mock_registry)
        assert scheduler.add_automation("early", "* * * * *") is False


# ---------------------------------------------------------------------------
# LogAggregator
# ---------------------------------------------------------------------------


class TestLogAggregator:
    def test_log_creates_file(self, log_aggregator) -> None:
        now = datetime.now(timezone.utc)
        entry = PipelineLog(
            automation_id="test-001",
            run_at=now,
            status="success",
            runtime_ms=123.4,
            output_summary="all good",
        )
        log_aggregator.log(entry)

        log_file = Path(log_aggregator.log_dir) / f"{now.strftime('%Y-%m-%d')}.jsonl"
        assert log_file.exists()

        with open(log_file) as f:
            data = json.loads(f.readline())
        assert data["automation_id"] == "test-001"
        assert data["status"] == "success"

    def test_log_multiple_entries(self, log_aggregator) -> None:
        now = datetime.now(timezone.utc)
        for i in range(5):
            log_aggregator.log(
                PipelineLog(
                    automation_id=f"test-{i}",
                    run_at=now,
                    status="success",
                    runtime_ms=float(i * 10),
                )
            )
        logs = log_aggregator.get_logs(date=now)
        assert len(logs) == 5

    def test_get_logs_filter_by_automation(self, log_aggregator) -> None:
        now = datetime.now(timezone.utc)
        log_aggregator.log(
            PipelineLog(
                automation_id="alpha",
                run_at=now,
                status="success",
                runtime_ms=10,
            )
        )
        log_aggregator.log(
            PipelineLog(
                automation_id="beta",
                run_at=now,
                status="failure",
                runtime_ms=20,
            )
        )

        alpha_logs = log_aggregator.get_logs(date=now, automation_id="alpha")
        assert len(alpha_logs) == 1
        assert alpha_logs[0].automation_id == "alpha"

    def test_get_logs_filter_by_status(self, log_aggregator) -> None:
        now = datetime.now(timezone.utc)
        log_aggregator.log(
            PipelineLog(
                automation_id="a1",
                run_at=now,
                status="success",
                runtime_ms=10,
            )
        )
        log_aggregator.log(
            PipelineLog(
                automation_id="a2",
                run_at=now,
                status="failure",
                runtime_ms=20,
            )
        )

        failures = log_aggregator.get_logs(date=now, status="failure")
        assert len(failures) == 1
        assert failures[0].automation_id == "a2"

    def test_get_logs_with_limit(self, log_aggregator) -> None:
        now = datetime.now(timezone.utc)
        for i in range(10):
            log_aggregator.log(
                PipelineLog(
                    automation_id=f"t-{i}",
                    run_at=now,
                    status="success",
                    runtime_ms=1.0,
                )
            )
        logs = log_aggregator.get_logs(date=now, limit=3)
        assert len(logs) == 3

    def test_get_logs_empty_date(self, log_aggregator) -> None:
        from datetime import timedelta

        old = datetime(2000, 1, 1, tzinfo=timezone.utc)
        logs = log_aggregator.get_logs(date=old)
        assert logs == []

    def test_log_dir_created_automatically(self, tmp_dir) -> None:
        new_dir = str(tmp_dir / "new_log_dir")
        agg = LogAggregator(log_dir=new_dir)
        assert Path(new_dir).exists()


# ---------------------------------------------------------------------------
# OrchestrationEngine Integration
# ---------------------------------------------------------------------------


class TestOrchestrationEngine:
    async def test_engine_initializes(self, tmp_dir) -> None:
        from openfang.orchestration.engine import OrchestrationEngine

        engine = OrchestrationEngine(
            db_path=str(tmp_dir / "test.db"),
            log_dir=str(tmp_dir / "logs"),
        )
        # start initializes DB and starts scheduler
        await engine.start()
        assert engine.scheduler.running is True
        await engine.stop()
        assert engine.scheduler.running is False

    async def test_engine_register_and_list(self, tmp_dir, good_pipeline) -> None:
        from openfang.orchestration.engine import OrchestrationEngine

        engine = OrchestrationEngine(
            db_path=str(tmp_dir / "test.db"),
            log_dir=str(tmp_dir / "logs"),
        )
        await engine.start()

        await engine.register_automation(
            id="math-demo",
            name="Math Demo",
            description="Adds numbers",
            pipeline_file=good_pipeline,
            cron_schedule="*/5 * * * *",
        )

        automations = await engine.list_automations()
        assert len(automations) == 1
        assert automations[0]["id"] == "math-demo"

        # Verify it was scheduled
        assert "math-demo" in engine.scheduler.job_ids

        await engine.stop()

    async def test_engine_run_now(self, tmp_dir, good_pipeline) -> None:
        from openfang.orchestration.engine import OrchestrationEngine

        engine = OrchestrationEngine(
            db_path=str(tmp_dir / "test.db"),
            log_dir=str(tmp_dir / "logs"),
        )
        await engine.start()

        await engine.register_automation(
            id="run-now-test",
            name="Run Now Test",
            description="Test immediate execution",
            pipeline_file=good_pipeline,
        )

        result = await engine.run_now("run-now-test")
        assert result["status"] == "success"
        assert "sum=6" in result["summary"]

        # Check run was logged
        history = await engine.get_run_history("run-now-test")
        assert len(history) == 1
        assert history[0]["status"] == "success"

        await engine.stop()

    async def test_engine_run_file(self, tmp_dir, good_pipeline) -> None:
        from openfang.orchestration.engine import OrchestrationEngine

        engine = OrchestrationEngine(
            db_path=str(tmp_dir / "test.db"),
            log_dir=str(tmp_dir / "logs"),
        )
        await engine.start()

        result = await engine.run_file(
            good_pipeline, config={"numbers": [100, 200]}
        )
        assert result["status"] == "success"
        assert "sum=300" in result["summary"]

        await engine.stop()

    async def test_engine_get_status(self, tmp_dir, good_pipeline) -> None:
        from openfang.orchestration.engine import OrchestrationEngine

        engine = OrchestrationEngine(
            db_path=str(tmp_dir / "test.db"),
            log_dir=str(tmp_dir / "logs"),
        )
        await engine.start()

        await engine.register_automation(
            id="status-test",
            name="Status Test",
            description="...",
            pipeline_file=good_pipeline,
            cron_schedule="0 * * * *",
        )

        status = await engine.get_status("status-test")
        assert status is not None
        assert status["id"] == "status-test"
        assert status["status"] == "active"
        assert status["scheduled"] is True
        assert status["next_run"] is not None

        await engine.stop()

    async def test_engine_pause_resume(self, tmp_dir, good_pipeline) -> None:
        from openfang.orchestration.engine import OrchestrationEngine

        engine = OrchestrationEngine(
            db_path=str(tmp_dir / "test.db"),
            log_dir=str(tmp_dir / "logs"),
        )
        await engine.start()

        await engine.register_automation(
            id="pause-test",
            name="Pause Test",
            description="...",
            pipeline_file=good_pipeline,
            cron_schedule="*/5 * * * *",
        )

        await engine.pause("pause-test")
        status = await engine.get_status("pause-test")
        assert status["status"] == "paused"

        await engine.resume("pause-test")
        status = await engine.get_status("pause-test")
        assert status["status"] == "active"

        await engine.stop()

    async def test_engine_status_not_found(self, tmp_dir) -> None:
        from openfang.orchestration.engine import OrchestrationEngine

        engine = OrchestrationEngine(
            db_path=str(tmp_dir / "test.db"),
            log_dir=str(tmp_dir / "logs"),
        )
        await engine.start()
        status = await engine.get_status("nonexistent")
        assert status is None
        await engine.stop()


# ---------------------------------------------------------------------------
# Local Math Pipeline
# ---------------------------------------------------------------------------


class TestLocalMathPipeline:
    async def test_runs_with_defaults(self) -> None:
        from openfang.pipelines.example_local_math import run

        ctx = PipelineContext(
            automation_id="test", run_at=datetime.now(timezone.utc)
        )
        result = await run(ctx)
        assert result.status == "success"
        assert "mean=3.00" in result.summary

    async def test_runs_with_custom_numbers(self) -> None:
        from openfang.pipelines.example_local_math import run

        ctx = PipelineContext(
            automation_id="test",
            run_at=datetime.now(timezone.utc),
            config={"numbers": [10, 20, 30]},
        )
        result = await run(ctx)
        assert result.status == "success"
        assert "mean=20.00" in result.summary
        assert "sum=60" in result.summary

    async def test_empty_numbers_returns_failure(self) -> None:
        from openfang.pipelines.example_local_math import run

        ctx = PipelineContext(
            automation_id="test",
            run_at=datetime.now(timezone.utc),
            config={"numbers": []},
        )
        result = await run(ctx)
        assert result.status == "failure"
        assert "No numbers" in result.summary


# ---------------------------------------------------------------------------
# CLI Argument Parsing
# ---------------------------------------------------------------------------


class TestCLI:
    def test_parser_accepts_start(self) -> None:
        from openfang.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["start"])
        assert args.command == "start"

    def test_parser_accepts_run(self) -> None:
        from openfang.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["run", "my_pipeline.py"])
        assert args.command == "run"
        assert args.pipeline_file == "my_pipeline.py"

    def test_parser_accepts_run_with_config(self) -> None:
        from openfang.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["run", "p.py", "--config", '{"x": 1}'])
        assert args.config == '{"x": 1}'

    def test_parser_accepts_register(self) -> None:
        from openfang.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "register", "my-id", "My Name", "pipeline.py",
            "--cron", "*/5 * * * *",
            "--description", "Test automation",
        ])
        assert args.command == "register"
        assert args.id == "my-id"
        assert args.name == "My Name"
        assert args.cron == "*/5 * * * *"

    def test_parser_accepts_list(self) -> None:
        from openfang.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["list"])
        assert args.command == "list"

    def test_parser_accepts_status(self) -> None:
        from openfang.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["status", "auto-001"])
        assert args.command == "status"
        assert args.automation_id == "auto-001"

    def test_parser_accepts_history(self) -> None:
        from openfang.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["history", "auto-001", "-n", "10"])
        assert args.command == "history"
        assert args.limit == 10

    def test_parser_default_db(self) -> None:
        from openfang.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["list"])
        assert args.db == "openfang_registry.db"

    def test_parser_custom_db(self) -> None:
        from openfang.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--db", "/tmp/custom.db", "list"])
        assert args.db == "/tmp/custom.db"


# ---------------------------------------------------------------------------
# Sandbox (pre-existing but verify it still works with updated executor)
# ---------------------------------------------------------------------------


class TestSandboxIntegration:
    async def test_sandbox_validates_good_pipeline(self, good_pipeline) -> None:
        from openfang.orchestration.sandbox import Sandbox

        sandbox = Sandbox()
        result = await sandbox.test(good_pipeline)
        assert result.passed is True
        assert result.output is not None
        assert result.output.status == "success"

    async def test_sandbox_catches_failing_pipeline(self, failing_pipeline) -> None:
        from openfang.orchestration.sandbox import Sandbox

        sandbox = Sandbox()
        result = await sandbox.test(failing_pipeline)
        assert result.passed is False
        assert any("Runtime error" in e for e in result.errors)

    async def test_sandbox_catches_import_error(self, bad_import_pipeline) -> None:
        from openfang.orchestration.sandbox import Sandbox

        sandbox = Sandbox()
        result = await sandbox.test(bad_import_pipeline)
        assert result.passed is False
        assert any("Import error" in e for e in result.errors)

    async def test_sandbox_catches_missing_file(self) -> None:
        from openfang.orchestration.sandbox import Sandbox

        sandbox = Sandbox()
        result = await sandbox.test("/nonexistent/pipeline.py")
        assert result.passed is False
        assert any("not found" in e for e in result.errors)
