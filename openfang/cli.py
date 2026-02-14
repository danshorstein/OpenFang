"""
OpenFang CLI — Command-line interface for the orchestration engine.

Usage:
    openfang start                              Start the scheduler daemon
    openfang run <pipeline_file> [--config JSON] Run a pipeline file directly
    openfang run-id <automation_id>             Run a registered automation now
    openfang register <id> <name> <file> [...]  Register an automation
    openfang list                               List all automations
    openfang status <automation_id>             Show automation status
    openfang history <automation_id>            Show run history
    openfang pause <automation_id>              Pause an automation
    openfang resume <automation_id>             Resume an automation
"""

import argparse
import asyncio
import json
import logging
import sys

from openfang.orchestration.engine import OrchestrationEngine


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openfang",
        description="OpenFang — LLMs write automations, not be automations.",
    )
    parser.add_argument(
        "--db", default="openfang_registry.db", help="Path to registry database"
    )
    parser.add_argument(
        "--log-dir", default="logs", help="Directory for execution logs"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    sub = parser.add_subparsers(dest="command")

    # start
    sub.add_parser("start", help="Start the scheduler daemon")

    # run <pipeline_file>
    run_p = sub.add_parser("run", help="Run a pipeline file directly")
    run_p.add_argument("pipeline_file", help="Path to pipeline .py file")
    run_p.add_argument("--config", default="{}", help="JSON config for the pipeline")

    # run-id <automation_id>
    run_id_p = sub.add_parser("run-id", help="Run a registered automation now")
    run_id_p.add_argument("automation_id", help="Automation ID to execute")

    # register
    reg_p = sub.add_parser("register", help="Register a new automation")
    reg_p.add_argument("id", help="Unique automation ID")
    reg_p.add_argument("name", help="Human-readable name")
    reg_p.add_argument("pipeline_file", help="Path to pipeline .py file")
    reg_p.add_argument("--description", default="", help="Description")
    reg_p.add_argument("--cron", default=None, help="Cron schedule (5-field)")
    reg_p.add_argument(
        "--mcp-servers", default=None, help="Comma-separated MCP server names"
    )

    # list
    sub.add_parser("list", help="List all automations")

    # status
    status_p = sub.add_parser("status", help="Show automation status")
    status_p.add_argument("automation_id", help="Automation ID")

    # history
    hist_p = sub.add_parser("history", help="Show run history")
    hist_p.add_argument("automation_id", help="Automation ID")
    hist_p.add_argument("-n", "--limit", type=int, default=20, help="Max entries")

    # pause / resume
    pause_p = sub.add_parser("pause", help="Pause an automation")
    pause_p.add_argument("automation_id", help="Automation ID")

    resume_p = sub.add_parser("resume", help="Resume a paused automation")
    resume_p.add_argument("automation_id", help="Automation ID")

    return parser


async def _cmd_start(engine: OrchestrationEngine) -> None:
    await engine.run_forever()


async def _cmd_run(engine: OrchestrationEngine, args: argparse.Namespace) -> None:
    await engine.registry.initialize()
    config = json.loads(args.config)
    result = await engine.run_file(args.pipeline_file, config=config)
    _print_result(result)


async def _cmd_run_id(engine: OrchestrationEngine, args: argparse.Namespace) -> None:
    await engine.registry.initialize()
    result = await engine.run_now(args.automation_id)
    _print_result(result)


async def _cmd_register(engine: OrchestrationEngine, args: argparse.Namespace) -> None:
    await engine.registry.initialize()
    mcp_servers = args.mcp_servers.split(",") if args.mcp_servers else None
    await engine.register_automation(
        id=args.id,
        name=args.name,
        description=args.description,
        pipeline_file=args.pipeline_file,
        cron_schedule=args.cron,
        mcp_servers=mcp_servers,
    )
    print(f"Registered: {args.id}")
    if args.cron:
        print(f"  Schedule: {args.cron}")


async def _cmd_list(engine: OrchestrationEngine) -> None:
    await engine.registry.initialize()
    automations = await engine.list_automations()
    if not automations:
        print("No automations registered.")
        return
    print(f"{'ID':<30} {'Status':<10} {'Schedule':<20} {'Last Run':<12} {'Runs':>5}")
    print("-" * 80)
    for a in automations:
        print(
            f"{a['id']:<30} {a['status']:<10} "
            f"{a.get('cron_schedule') or '(manual)':<20} "
            f"{a.get('last_run_status') or '-':<12} "
            f"{a.get('run_count', 0):>5}"
        )


async def _cmd_status(engine: OrchestrationEngine, args: argparse.Namespace) -> None:
    await engine.registry.initialize()
    status = await engine.get_status(args.automation_id)
    if not status:
        print(f"Automation not found: {args.automation_id}")
        sys.exit(1)
    for key, val in status.items():
        print(f"  {key}: {val}")


async def _cmd_history(engine: OrchestrationEngine, args: argparse.Namespace) -> None:
    await engine.registry.initialize()
    history = await engine.get_run_history(args.automation_id, limit=args.limit)
    if not history:
        print(f"No runs recorded for: {args.automation_id}")
        return
    print(f"{'Run At':<22} {'Status':<10} {'Runtime':<10} {'Summary'}")
    print("-" * 70)
    for h in history:
        rt = f"{h.get('runtime_ms', 0)}ms"
        summary = h.get("output_summary") or h.get("error_detail") or ""
        print(f"{h.get('run_at', '-'):<22} {h['status']:<10} {rt:<10} {summary[:40]}")


async def _cmd_pause(engine: OrchestrationEngine, args: argparse.Namespace) -> None:
    await engine.registry.initialize()
    await engine.pause(args.automation_id)
    print(f"Paused: {args.automation_id}")


async def _cmd_resume(engine: OrchestrationEngine, args: argparse.Namespace) -> None:
    await engine.registry.initialize()
    await engine.resume(args.automation_id)
    print(f"Resumed: {args.automation_id}")


def _print_result(result: dict) -> None:
    status = result.get("status", "unknown")
    symbol = "OK" if status == "success" else "FAIL"
    print(f"[{symbol}] {status}")
    if result.get("summary"):
        print(f"  Summary: {result['summary']}")
    if result.get("error"):
        print(f"  Error: {result['error']}")
    if result.get("runtime_ms"):
        print(f"  Runtime: {result['runtime_ms']:.0f}ms")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    _setup_logging(verbose=args.verbose)

    engine = OrchestrationEngine(db_path=args.db, log_dir=args.log_dir)

    commands = {
        "start": lambda: _cmd_start(engine),
        "run": lambda: _cmd_run(engine, args),
        "run-id": lambda: _cmd_run_id(engine, args),
        "register": lambda: _cmd_register(engine, args),
        "list": lambda: _cmd_list(engine),
        "status": lambda: _cmd_status(engine, args),
        "history": lambda: _cmd_history(engine, args),
        "pause": lambda: _cmd_pause(engine, args),
        "resume": lambda: _cmd_resume(engine, args),
    }

    handler = commands.get(args.command)
    if handler:
        asyncio.run(handler())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
