"""Josie 1.0 command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from josie.config import load_config
from josie.logging_setup import configure_logging
from josie.gui import launch_gui
from josie.instance import gui_instance
from josie.deployment import DeploymentController
from josie.providers import probe_gemini, probe_openai, provider_status
from josie.tools import available_tools, run_tool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Josie local-first orchestration kernel")
    subcommands = parser.add_subparsers(dest="command", required=True)

    health = subcommands.add_parser("health", help="Run safe system diagnostics")
    health.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    tools = subcommands.add_parser("tools", help="Inspect or run an allowed tool")
    tools_subcommands = tools.add_subparsers(dest="tools_command", required=True)
    tools_subcommands.add_parser("list", help="List explicitly allowed tools")
    run = tools_subcommands.add_parser("run", help="Run one explicitly allowed tool")
    run.add_argument("name", choices=available_tools())
    run.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    providers = subcommands.add_parser("providers", help="Inspect or test cloud providers")
    provider_subcommands = providers.add_subparsers(dest="provider_command", required=True)
    provider_subcommands.add_parser("status", help="Show configuration without revealing keys")
    check = provider_subcommands.add_parser("check", help="Send one minimal live request")
    check.add_argument("provider", choices=("openai", "gemini"))

    subcommands.add_parser("gui", help="Open Josie's local graphical interface")
    deploy = subcommands.add_parser("deploy", help="Run or inspect resumable deployment")
    deploy.add_argument("action", choices=("status", "safe"))
    return parser


def main() -> int:
    project_root = Path(__file__).resolve().parent
    config = load_config(project_root / ".env")
    logger = configure_logging(project_root / "logs", config.log_level)
    args = build_parser().parse_args()

    if args.command == "tools" and args.tools_command == "list":
        print("\n".join(available_tools()))
        return 0

    if args.command == "providers":
        if args.provider_command == "status":
            print(json.dumps(provider_status(config), indent=2, sort_keys=True))
            return 0
        probe = probe_openai if args.provider == "openai" else probe_gemini
        logger.info("Running minimal provider check: %s", args.provider)
        print(json.dumps(probe(config), indent=2, sort_keys=True))
        return 0

    if args.command == "gui":
        with gui_instance() as acquired:
            if not acquired:
                logger.info("Josie GUI is already running")
                return 0
            logger.info("Starting local GUI")
            launch_gui(config=config, project_root=project_root)
        return 0

    if args.command == "deploy":
        controller = DeploymentController(config=config, project_root=project_root)
        result = controller.status() if args.action == "status" else controller.run_safe_phase()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    tool_name = "health" if args.command == "health" else args.name
    logger.info("Running allowed tool: %s", tool_name)
    result = run_tool(tool_name, config=config, project_root=project_root)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
