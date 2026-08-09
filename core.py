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
from josie.browser_research import extract_official_source
from josie.economic_policy import load_economic_policy
from josie.status_snapshot import build_status_snapshot, write_status_snapshot
from josie.diagnostics import recovery_snapshot, restore_drill_snapshot
from josie.research import record_opportunity, record_upgrade_target
from josie.opportunity_policy import load_opportunity_policy
from josie.foundation import build_foundation_report, write_foundation_report
from josie.genesis import build_genesis_status


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
    proposal_commands = proposals.add_subparsers(dest="proposal_command", required=True)
    proposal_commands.add_parser("ingest", help="Ingest bounded external proposal files")
    proposal_commands.add_parser("status", help="List all governed proposal reviews")
    proposal_review = proposal_commands.add_parser(
        "review", help="Record a human proposal decision without executing it"
    )
    proposal_review.add_argument("proposal_type", choices=("external", "model"))
    proposal_review.add_argument("proposal_id", type=int)
    proposal_review.add_argument("decision", choices=("accept", "reject"))
    proposal_review.add_argument("--reason", required=True)
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
    browser = subcommands.add_parser("browser", help="Inspect or use bounded read-only research")
    browser.add_argument("action", choices=("status", "extract"))
    browser.add_argument("url", nargs="?")
    economics = subcommands.add_parser("economics", help="Inspect zero-dollar economic limits")
    economics.add_argument("action", choices=("status",))
    backups = subcommands.add_parser("backups", help="Create or inspect local recovery snapshots")
    backups.add_argument(
        "action", choices=("status", "create-local", "create-checkpoint")
    )
    backups.add_argument("--label", default="manual-checkpoint")
    research = subcommands.add_parser(
        "research", help="Track research-only opportunities and hardware targets"
    )
    research_commands = research.add_subparsers(dest="research_command", required=True)
    research_commands.add_parser("status", help="List local research records")
    research_commands.add_parser("sources", help="Inspect the locked opportunity-source policy")
    opportunity = research_commands.add_parser(
        "add-opportunity", help="Record an opportunity estimate without accepting work"
    )
    opportunity.add_argument("--title", required=True)
    opportunity.add_argument("--source", required=True)
    opportunity.add_argument("--estimated-revenue", required=True)
    opportunity.add_argument("--estimated-cost", required=True)
    opportunity.add_argument("--estimated-hours", required=True)
    opportunity.add_argument("--risk", choices=("low", "medium", "high"), required=True)
    opportunity.add_argument("--notes", required=True)
    upgrade = research_commands.add_parser(
        "add-upgrade", help="Record a hardware target without authorizing a purchase"
    )
    upgrade.add_argument("--component", required=True)
    upgrade.add_argument("--target-price", default="0")
    upgrade.add_argument("--capability", required=True)
    upgrade.add_argument(
        "--compatibility",
        choices=("unknown", "needs_review", "compatible", "incompatible"),
        default="unknown",
    )
    upgrade.add_argument("--notes", required=True)
    status_snapshot = subcommands.add_parser(
        "status-snapshot", help="Show or publish the secret-free read-only status snapshot"
    )
    status_snapshot.add_argument("action", choices=("show", "write"))
    foundation = subcommands.add_parser(
        "foundation", help="Assess or publish operational readiness for Genesis"
    )
    foundation.add_argument("action", choices=("status", "write", "gates"))
    genesis = subcommands.add_parser(
        "genesis", help="Show the identity-formation protocol status"
    )
    genesis.add_argument("action", choices=("status",))
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
        if args.proposal_command == "ingest":
            result = ingest_proposal_inbox(config=config, project_root=project_root, store=store)
        elif args.proposal_command == "review":
            result = store.decide_proposal(
                proposal_type=args.proposal_type,
                proposal_id=args.proposal_id,
                decision=args.decision,
                reason=args.reason,
            )
        else:
            result = {"status": "ok", **store.proposal_review_summary()}
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
        if args.action == "status":
            result = load_browser_policy(project_root)
        else:
            if not args.url:
                raise SystemExit("browser extract requires one approved URL")
            try:
                result = extract_official_source(
                    config=config, project_root=project_root, url=args.url
                )
            except (OSError, ValueError, RuntimeError) as exc:
                print(json.dumps({
                    "status": "rejected",
                    "reason": str(exc),
                    "external_activity_may_have_occurred": isinstance(exc, RuntimeError),
                    "actions_queued": 0,
                    "actions_executed": 0,
                }, indent=2, sort_keys=True))
                return 1
            LocalStore(project_root / "data" / "josie.db").audit(
                "browser_research_completed", str(result.get("final_url", "approved source"))
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "economics":
        print(json.dumps(load_economic_policy(project_root), indent=2, sort_keys=True))
        return 0

    if args.command == "backups":
        store = LocalStore(project_root / "data" / "josie.db")
        created: list[str] = []
        backup_directories = [project_root / "data" / "backups"]
        if config.external_storage and config.external_storage.is_dir():
            backup_directories.append(
                config.external_storage / "backups" / "josie-database"
            )
        before = {
            str(path.resolve())
            for directory in backup_directories
            if directory.exists()
            for path in directory.glob("josie-*.db")
        }
        if args.action == "create-local":
            created.append(str(store.create_daily_backup(project_root / "data" / "backups")))
            if config.external_storage and config.external_storage.is_dir():
                created.append(
                    str(
                        store.create_daily_backup(
                            config.external_storage / "backups" / "josie-database"
                        )
                    )
                )
        elif args.action == "create-checkpoint":
            created.append(
                str(
                    store.create_checkpoint_backup(
                        project_root / "data" / "backups", label=args.label
                    )
                )
            )
            if config.external_storage and config.external_storage.is_dir():
                created.append(
                    str(
                        store.create_checkpoint_backup(
                            config.external_storage / "backups" / "josie-database",
                            label=args.label,
                        )
                    )
                )
        after = {
            str(path.resolve())
            for directory in backup_directories
            if directory.exists()
            for path in directory.glob("josie-*.db")
        }
        deleted = sorted(before - after)
        result = {
            "status": "ok",
            "created_or_verified": created,
            "local": recovery_snapshot(config=config, project_root=project_root),
            "restore_drill": restore_drill_snapshot(
                config=config, project_root=project_root
            ),
            "deletion_performed": bool(deleted),
            "deleted_by_retention": deleted,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "research":
        store = LocalStore(project_root / "data" / "josie.db")
        if args.research_command == "sources":
            result = load_opportunity_policy(project_root)
        elif args.research_command == "add-opportunity":
            result = record_opportunity(
                store=store,
                title=args.title,
                source=args.source,
                estimated_revenue=args.estimated_revenue,
                estimated_cost=args.estimated_cost,
                estimated_hours=args.estimated_hours,
                risk=args.risk,
                notes=args.notes,
            )
        elif args.research_command == "add-upgrade":
            result = record_upgrade_target(
                store=store,
                component=args.component,
                target_price=args.target_price,
                expected_capability=args.capability,
                compatibility=args.compatibility,
                notes=args.notes,
            )
        else:
            result = store.research_summary()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "foundation":
        result = (
            write_foundation_report(config=config, project_root=project_root)
            if args.action == "write"
            else build_foundation_report(config=config, project_root=project_root)
        )
        if args.action == "gates":
            result = {
                "state": result["state"],
                "foundation_ready": result["foundation_ready"],
                "ready_to_begin_genesis": result["ready_to_begin_genesis"],
                "human_gate_count": result["human_gate_count"],
                "human_gates": result["human_gates"],
                "actions_queued": 0,
                "actions_executed": 0,
                "external_activity": False,
            }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "genesis":
        print(json.dumps(build_genesis_status(project_root=project_root), indent=2, sort_keys=True))
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
