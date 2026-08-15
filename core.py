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
from josie.ebay_source import import_ebay_fixture, load_ebay_source_policy
from josie.hardware_titles import classify_hardware_title, load_hardware_title_rules
from josie.evidence_policy import evaluate_claim_evidence, load_evidence_policy
from josie.deal_hunter import score_and_record_deal
from josie.foundation import build_foundation_report, write_foundation_report
from josie.genesis import build_genesis_status
from josie.learning import (
    foundational_learning_status,
    foundational_learning_unit,
    sync_foundational_curriculum,
)
from josie.learning_assessment import (
    assess_local_foundational_judgment,
    assess_local_holdout_judgment,
)


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
    research_commands.add_parser(
        "ebay-source", help="Inspect the staged, network-disabled eBay source policy"
    )
    research_commands.add_parser(
        "ebay-discoveries", help="List the local unresolved eBay discovery inbox"
    )
    ebay_fixture = research_commands.add_parser(
        "import-ebay-fixture", help="Import one offline fixture from the local staging inbox"
    )
    ebay_fixture.add_argument("--file", required=True)
    ebay_fixture.add_argument("--observed-at", required=True)
    research_commands.add_parser(
        "hardware-title-rules", help="Inspect deterministic research-only title rules"
    )
    classify_title = research_commands.add_parser(
        "classify-title", help="Classify one untrusted listing title without resolving specs"
    )
    classify_title.add_argument("--title", required=True)
    research_commands.add_parser(
        "classify-discoveries", help="Classify unresolved titles without changing records"
    )
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
    deal = research_commands.add_parser(
        "score-deal", help="Score one manually supplied hardware listing locally"
    )
    deal.add_argument("--title", required=True)
    deal.add_argument("--source-reference", required=True)
    deal.add_argument(
        "--source-kind",
        choices=(
            "canonical_versioned", "primary_authoritative",
            "direct_system_observation", "model_output", "retrieved_memory",
            "secondary", "unknown", "user_supplied",
        ),
        required=True,
    )
    deal.add_argument("--observed-at", required=True)
    deal.add_argument("--ask-price", required=True)
    deal.add_argument("--shipping", default="0")
    deal.add_argument("--tax", default="0")
    deal.add_argument("--required-platform-cost", default="0")
    deal.add_argument("--benchmark-index", required=True)
    deal.add_argument("--vram-gb", required=True)
    deal.add_argument("--power-watts", type=int, required=True)
    deal.add_argument(
        "--compatibility",
        choices=("compatible", "needs_review", "unknown", "incompatible"),
        required=True,
    )
    deal.add_argument(
        "--condition",
        choices=("new", "used_good", "used_unknown", "parts_only"),
        required=True,
    )
    deal.add_argument("--seller-risk", choices=("low", "medium", "high"), required=True)
    deal.add_argument("--notes", required=True)
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
    prayer = subcommands.add_parser(
        "prayer", help="Inspect the sensitive local manual prayer registry"
    )
    prayer_commands = prayer.add_subparsers(dest="prayer_command", required=True)
    prayer_commands.add_parser("status", help="Show counts and locked connection state")
    prayer_list = prayer_commands.add_parser(
        "list", help="List metadata only; prayer text is omitted"
    )
    prayer_list.add_argument("--limit", type=int, default=50)
    prayer_show = prayer_commands.add_parser(
        "show", help="Show one locally stored prayer request explicitly"
    )
    prayer_show.add_argument("prayer_id", type=int)
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
    learning = subcommands.add_parser(
        "learning", help="Inspect or synchronize bounded local foundational learning"
    )
    learning.add_argument(
        "action", choices=("status", "sync", "show", "assess-local", "assess-holdout")
    )
    learning.add_argument("learning_id", nargs="?")
    evidence = subcommands.add_parser(
        "evidence", help="Inspect or apply the deterministic evidence-verification gate"
    )
    evidence.add_argument("action", choices=("status", "check"))
    evidence.add_argument("--stability", choices=("stable", "unstable"))
    evidence.add_argument(
        "--source-kind",
        choices=(
            "canonical_versioned", "primary_authoritative",
            "direct_system_observation", "model_output", "retrieved_memory",
            "secondary", "unknown", "user_supplied",
        ),
    )
    evidence.add_argument("--observed-at")
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
        elif args.research_command == "ebay-source":
            result = load_ebay_source_policy(project_root)
        elif args.research_command == "ebay-discoveries":
            result = {
                "status": "unresolved_research_only",
                "discoveries": store.recent_deal_discoveries(),
                "external_activity": False,
                "actions_queued": 0,
                "actions_executed": 0,
                "purchase_authorized": False,
            }
        elif args.research_command == "import-ebay-fixture":
            result = import_ebay_fixture(
                store=store, project_root=project_root,
                filename=args.file, observed_at=args.observed_at,
            )
        elif args.research_command == "hardware-title-rules":
            result = load_hardware_title_rules(project_root)
        elif args.research_command == "classify-title":
            result = classify_hardware_title(project_root=project_root, title=args.title)
        elif args.research_command == "classify-discoveries":
            discoveries = store.recent_deal_discoveries(limit=100)
            result = {
                "status": "read_only_title_candidates",
                "results": [
                    {
                        "discovery_id": item["discovery_id"],
                        "external_item_id": item["external_item_id"],
                        "title": item["title"],
                        "classification": classify_hardware_title(
                            project_root=project_root, title=str(item["title"])
                        ),
                    }
                    for item in discoveries
                ],
                "records_changed": 0,
                "external_activity": False,
                "network_requests": 0,
                "actions_queued": 0,
                "actions_executed": 0,
                "purchase_authorized": False,
                "capability_change": "none",
            }
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
        elif args.research_command == "score-deal":
            result = score_and_record_deal(
                store=store,
                project_root=project_root,
                title=args.title,
                source_reference=args.source_reference,
                source_kind=args.source_kind,
                observed_at=args.observed_at,
                ask_price=args.ask_price,
                shipping=args.shipping,
                tax=args.tax,
                required_platform_cost=args.required_platform_cost,
                benchmark_index=args.benchmark_index,
                vram_gb=args.vram_gb,
                power_watts=args.power_watts,
                compatibility=args.compatibility,
                condition=args.condition,
                seller_risk=args.seller_risk,
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

    if args.command == "evidence":
        policy = load_evidence_policy(project_root)
        if args.action == "status":
            if any((args.stability, args.source_kind, args.observed_at)):
                raise ValueError("Evidence status does not accept claim parameters")
            result = policy
        else:
            if not all((args.stability, args.source_kind, args.observed_at)):
                raise ValueError(
                    "Evidence check requires --stability, --source-kind, and --observed-at"
                )
            result = evaluate_claim_evidence(
                policy=policy,
                stability=args.stability,
                source_kind=args.source_kind,
                observed_at=args.observed_at,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "prayer":
        store = LocalStore(project_root / "data" / "josie.db")
        if args.prayer_command == "status":
            result = store.prayer_summary()
        elif args.prayer_command == "list":
            requests = store.recent_prayer_requests(args.limit)
            result = {
                **store.prayer_summary(),
                "requests": [
                    {
                        "prayer_id": item["prayer_id"],
                        "received_at": item["received_at"],
                        "last_reviewed_at": item["last_reviewed_at"],
                        "source_context": item["source_context"],
                        "identity_handling": item["identity_handling"],
                        "status": item["status"],
                        "follow_up_at": item["follow_up_at"],
                        "sensitivity": item["sensitivity"],
                        "redacted": item["redacted"],
                    }
                    for item in requests
                ],
                "prayer_text_included": False,
                "requester_identity_included": False,
            }
        else:
            item = store.prayer_request(args.prayer_id)
            result = {
                "status": "local_sensitive_record",
                "request": item,
                "change_history": store.prayer_request_changes(args.prayer_id),
                "external_activity": False,
                "messages_sent": 0,
                "cloud_processing_authorized": False,
                "cross_post_authorized": False,
            }
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

    if args.command == "learning":
        store = LocalStore(project_root / "data" / "josie.db")
        if args.action == "sync":
            if args.learning_id is not None:
                raise ValueError("Learning sync does not accept a learning ID")
            result = sync_foundational_curriculum(project_root=project_root, store=store)
        elif args.action == "assess-local":
            if args.learning_id is not None:
                raise ValueError("Local learning assessment does not accept a learning ID")
            result = assess_local_foundational_judgment(
                config=config, project_root=project_root, store=store
            )
        elif args.action == "assess-holdout":
            if args.learning_id is not None:
                raise ValueError("Local holdout assessment does not accept a learning ID")
            result = assess_local_holdout_judgment(
                config=config, project_root=project_root, store=store
            )
        elif args.action == "show":
            if args.learning_id is None:
                raise ValueError("Learning show requires a learning ID")
            result = foundational_learning_unit(store=store, learning_id=args.learning_id)
        else:
            if args.learning_id is not None:
                raise ValueError("Learning status does not accept a learning ID")
            result = foundational_learning_status(project_root=project_root, store=store)
        print(json.dumps(result, indent=2, sort_keys=True))
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
