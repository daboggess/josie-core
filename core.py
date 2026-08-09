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
from josie.acceptance import acceptance_audit
from josie.jobs import JobRunner, available_job_handlers
from josie.storage import LocalStore
from josie.local_model import propose_local_actions
from josie.proposal_inbox import ingest_proposal_inbox
from josie.handoffs import export_model_handoff
from josie.browser_policy import load_browser_policy
from josie.economic_policy import load_economic_policy
from josie.status_snapshot import build_status_snapshot, write_status_snapshot


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
    deploy.add_argument("action", choices=("status", "safe", "services-preflight", "validate"))
    subcommands.add_parser("audit", help="Audit Josie 1.0 acceptance evidence")
    jobs = subcommands.add_parser("jobs", help="Manage bounded local orchestration jobs")
    jobs_subcommands = jobs.add_subparsers(dest="jobs_command", required=True)
    jobs_subcommands.add_parser("status", help="Show local job counts")
    jobs_subcommands.add_parser("run-one", help="Run one queued allowlisted job")
    queue = jobs_subcommands.add_parser("queue", help="Queue an allowlisted local job")
    queue.add_argument("handler", choices=available_job_handlers())
    propose = subcommands.add_parser("propose", help="Ask the local model for non-executing proposals")
    propose.add_argument("request", nargs="+", help="Untrusted request text")
    proposals = subcommands.add_parser("proposals", help="Manage the bounded external proposal inbox")
    proposals.add_argument("action", choices=("ingest", "status"))
    handoffs = subcommands.add_parser("handoffs", help="Manage zero-spend manual model handoffs")
    handoff_commands = handoffs.add_subparsers(dest="handoff_command", required=True)
    handoff_commands.add_parser("list", help="List local handoff drafts")
    handoff_create = handoff_commands.add_parser("create", help="Create a local handoff draft")
    handoff_create.add_argument("target", choices=("sophie", "bernie"))
    handoff_create.add_argument("request", nargs="+")
    handoff_export = handoff_commands.add_parser("export", help="Export one draft locally")
    handoff_export.add_argument("handoff_id", type=int)
    handoff_answer = handoff_commands.add_parser("answer", help="Record a manually relayed answer")
    handoff_answer.add_argument("handoff_id", type=int)
    handoff_answer.add_argument("response", nargs="+")
    browser = subcommands.add_parser("browser", help="Inspect the locked browser policy")
    browser.add_argument("action", choices=("status",))
    economics = subcommands.add_parser("economics", help="Inspect zero-dollar economic limits")
    economics.add_argument("action", choices=("status",))
    status_snapshot = subcommands.add_parser(
        "status-snapshot", help="Show or publish the secret-free read-only status snapshot"
    )
    status_snapshot.add_argument("action", choices=("show", "write"))
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
        if args.action == "status":
            result = controller.status()
        elif args.action == "services-preflight":
            result = controller.service_preflight()
        elif args.action == "validate":
            result = controller.validate_runtime()
        else:
            result = controller.run_safe_phase()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "audit":
        result = acceptance_audit(config=config, project_root=project_root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] != "failed" else 1

    if args.command == "jobs":
        store = LocalStore(project_root / "data" / "josie.db")
        runner = JobRunner(config=config, project_root=project_root, store=store)
        if args.jobs_command == "status":
            result = store.job_summary()
        elif args.jobs_command == "queue":
            result = {"status": "queued", "job_id": runner.queue(args.handler)}
        else:
            result = runner.run_one()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "propose":
        request_text = " ".join(args.request).strip()
        store = LocalStore(project_root / "data" / "josie.db")
        result = propose_local_actions(request_text, config=config, project_root=project_root)
        proposal_id = store.record_model_proposal(
            user_input=request_text,
            model=str(result["model"]),
            response_json=json.dumps(result, sort_keys=True),
        )
        result["proposal_id"] = proposal_id
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "proposals":
        store = LocalStore(project_root / "data" / "josie.db")
        if args.action == "ingest":
            result = ingest_proposal_inbox(config=config, project_root=project_root, store=store)
        else:
            result = {"status": "ok", "proposals": store.recent_external_proposals()}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "handoffs":
        store = LocalStore(project_root / "data" / "josie.db")
        if args.handoff_command == "list":
            result = {"status": "ok", "handoffs": store.recent_model_handoffs()}
        elif args.handoff_command == "create":
            result = store.create_model_handoff(
                target=args.target, request=" ".join(args.request)
            )
        elif args.handoff_command == "export":
            result = export_model_handoff(
                config=config, store=store, handoff_id=args.handoff_id
            )
        else:
            changed = store.record_model_handoff_answer(
                handoff_id=args.handoff_id, response=" ".join(args.response)
            )
            result = {
                "status": "answered" if changed else "not_found_or_not_draft",
                "handoff_id": args.handoff_id,
                "external_activity": False,
                "response_untrusted": True,
            }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "browser":
        print(json.dumps(load_browser_policy(project_root), indent=2, sort_keys=True))
        return 0

    if args.command == "economics":
        print(json.dumps(load_economic_policy(project_root), indent=2, sort_keys=True))
        return 0

    if args.command == "status-snapshot":
        if args.action == "write":
            result = write_status_snapshot(config=config, project_root=project_root)
        else:
            result = build_status_snapshot(config=config, project_root=project_root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if args.action == "write" or result["overall"] != "critical" else 1

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
