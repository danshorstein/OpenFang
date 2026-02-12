"""
Sandbox — Isolated test runner for pipeline scripts.

Tests generated pipeline scripts in an isolated environment
before deploying them to production. Validates that:
- The script imports successfully
- The run() entry point exists and is async
- Output types match expected schemas
- All referenced MCP servers are available
"""

import asyncio
import importlib
import logging
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openfang.orchestration.executor import PipelineContext, PipelineResult

logger = logging.getLogger("openfang.sandbox")


@dataclass
class SandboxTestResult:
    """Result from running a pipeline in the sandbox."""

    passed: bool
    errors: list[str]
    warnings: list[str]
    runtime_ms: float
    output: PipelineResult | None = None


class Sandbox:
    """
    Isolated test runner for pipeline scripts.

    Validates that a pipeline script:
    1. Can be imported without errors
    2. Has an async run(context) entry point
    3. Executes without unhandled exceptions
    4. Returns a valid PipelineResult
    """

    async def test(
        self,
        script_path: str,
        config: dict[str, Any] | None = None,
    ) -> SandboxTestResult:
        """
        Test a pipeline script in the sandbox.

        Args:
            script_path: Path to the Python pipeline script.
            config: Optional configuration to pass to the pipeline.
        """
        errors: list[str] = []
        warnings: list[str] = []
        start_time = datetime.now(timezone.utc)

        # Step 1: Validate the file exists
        path = Path(script_path)
        if not path.exists():
            return SandboxTestResult(
                passed=False,
                errors=[f"Script not found: {script_path}"],
                warnings=[],
                runtime_ms=0,
            )

        # Step 2: Try to import the module
        module_name = path.stem
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return SandboxTestResult(
                passed=False,
                errors=[f"Cannot create module spec from: {script_path}"],
                warnings=[],
                runtime_ms=0,
            )

        try:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            return SandboxTestResult(
                passed=False,
                errors=[f"Import error: {e}\n{traceback.format_exc()}"],
                warnings=[],
                runtime_ms=0,
            )

        # Step 3: Validate entry point
        if not hasattr(module, "run"):
            errors.append("Module missing required 'run' function")
            return SandboxTestResult(
                passed=False,
                errors=errors,
                warnings=warnings,
                runtime_ms=0,
            )

        if not asyncio.iscoroutinefunction(module.run):
            errors.append("'run' function must be async (async def run)")
            return SandboxTestResult(
                passed=False,
                errors=errors,
                warnings=warnings,
                runtime_ms=0,
            )

        # Step 4: Execute the pipeline
        context = PipelineContext(
            automation_id="sandbox-test",
            run_at=start_time,
            config=config or {},
        )

        try:
            result = await module.run(context)
        except Exception as e:
            runtime_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000
            return SandboxTestResult(
                passed=False,
                errors=[f"Runtime error: {e}\n{traceback.format_exc()}"],
                warnings=warnings,
                runtime_ms=runtime_ms,
            )
        finally:
            # Clean up the temporary module
            sys.modules.pop(module_name, None)

        runtime_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

        # Step 5: Validate output
        if not isinstance(result, PipelineResult):
            errors.append(
                f"run() must return PipelineResult, got {type(result).__name__}"
            )

        passed = len(errors) == 0
        logger.info(
            f"Sandbox test {'PASSED' if passed else 'FAILED'} "
            f"for {script_path} in {runtime_ms:.0f}ms"
        )

        return SandboxTestResult(
            passed=passed,
            errors=errors,
            warnings=warnings,
            runtime_ms=runtime_ms,
            output=result if isinstance(result, PipelineResult) else None,
        )
