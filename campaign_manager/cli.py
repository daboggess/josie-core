from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .constants import DEFAULT_DB_PATH
from .errors import CampaignAlreadyRunningError
from .manager import CampaignManager
from .schema import init_db


def cmd_init(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    init_db(db_path)
    print(f"Initialized database schema at {db_path}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec_file)
    if not spec_path.is_file():
        print(f"Error: spec file '{spec_path}' does not exist", file=sys.stderr)
        return 1
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error reading spec file: {exc}", file=sys.stderr)
        return 1

    manager = CampaignManager(db_path=args.db)
    try:
        campaign_id = manager.create_campaign(spec)
        print(f"Campaign created: {campaign_id}")
        return 0
    except Exception as exc:
        print(f"Failed to create campaign: {exc}", file=sys.stderr)
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    manager = CampaignManager(db_path=args.db, runner_id=args.runner_id)
    try:
        status = manager.run_campaign(args.campaign_id)
        print(f"Campaign {args.campaign_id} finished:")
        print(f"Status: {status['status']}")
        print(f"Summary: {status['summary']}")
        return 0 if status["status"] == "COMPLETED" else 1
    except CampaignAlreadyRunningError as exc:
        print(f"Campaign already running: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Execution error: {exc}", file=sys.stderr)
        return 2


def cmd_status(args: argparse.Namespace) -> int:
    manager = CampaignManager(db_path=args.db)
    try:
        info = manager.get_campaign_status(args.campaign_id)
        if args.json:
            print(json.dumps(info, indent=2))
            return 0

        print(f"Campaign: {info['name']} ({info['campaign_id']})")
        print(f"Status:   {info['status']}")
        print(f"Runner:   {info.get('runner_id') or 'None'}")
        print(f"Lease:    {info.get('lease_expires_at') or 'None'}")
        print(f"Created:  {info['created_at']}")
        print(f"Updated:  {info['updated_at']}")
        print(f"Summary:  {info['summary']}")
        print("\nJobs:")
        for job in info["jobs"]:
            reason_suffix = f" (reason: {job['failure_reason']})" if job.get("failure_reason") else ""
            print(f"  - [{job['state']}] {job['job_id']}: {job['name']} (attempts: {job['attempts_used']}/{job['max_attempts']}){reason_suffix}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_reconcile(args: argparse.Namespace) -> int:
    manager = CampaignManager(db_path=args.db)
    try:
        reconciled = manager.reconcile(args.campaign_id, force=getattr(args, "force", False))
        print(f"Reconciled {len(reconciled)} jobs:")
        for item in reconciled:
            print(f"  - {item['job_id']}: {item['state_from']} -> {item['state_to']} (reason: {item['reason']})")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_job(args: argparse.Namespace) -> int:
    manager = CampaignManager(db_path=args.db)
    try:
        job = manager.get_job(args.job_id)
        events = manager.get_job_events(args.job_id)
        if args.json:
            print(json.dumps({"job": job.to_dict(), "events": [e.to_dict() for e in events]}, indent=2))
            return 0

        print(f"Job ID:          {job.job_id}")
        print(f"Name:            {job.name}")
        print(f"Campaign ID:     {job.campaign_id}")
        print(f"State:           {job.state}")
        print(f"Attempts:        {job.attempts_used} / {job.max_attempts}")
        print(f"Attempt ID:      {job.current_attempt_id or 'None'}")
        print(f"Supervisor Job:  {job.current_supervisor_job_id or 'None'}")
        print(f"Retry Safe:      {job.retry_safe}")
        print(f"Idempotency Key: {job.idempotency_key}")
        print(f"Failure Reason:  {job.failure_reason or 'None'}")
        print(f"Last Req ID:     {job.last_supervisor_request_id or 'None'}")
        print(f"Last Receipt ID: {job.last_supervisor_receipt_id or 'None'}")
        print(f"Runner ID:       {job.runner_id or 'None'}")
        print(f"Lease Expires:   {job.lease_expires_at or 'None'}")
        print("\nEvent History:")
        for ev in events:
            details = f" - {ev.details_json}" if ev.details_json else ""
            print(f"  [{ev.created_at}] {ev.event_type} ({ev.state_from} -> {ev.state_to}){details}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_approve(args: argparse.Namespace) -> int:
    manager = CampaignManager(db_path=args.db)
    try:
        job = manager.approve_job(args.job_id)
        print(f"Job {job.job_id} approved. New state: {job.state}")
        return 0
    except Exception as exc:
        print(f"Approval error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m campaign_manager.cli", description="Josie Campaign Manager CLI")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Path to SQLite database")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_p = subparsers.add_parser("init", help="Initialize database schema")
    init_p.set_defaults(func=cmd_init)

    # create
    create_p = subparsers.add_parser("create", help="Create a campaign from a JSON spec file")
    create_p.add_argument("spec_file", type=str, help="Path to campaign spec JSON")
    create_p.set_defaults(func=cmd_create)

    # run
    run_p = subparsers.add_parser("run", help="Run/drain a campaign sequentially")
    run_p.add_argument("campaign_id", type=str, help="Campaign ID to run")
    run_p.add_argument("--runner-id", type=str, default=None, help="Custom runner identity")
    run_p.set_defaults(func=cmd_run)

    # status
    status_p = subparsers.add_parser("status", help="Show campaign status and counts")
    status_p.add_argument("campaign_id", type=str, help="Campaign ID")
    status_p.add_argument("--json", action="store_true", help="Output raw JSON")
    status_p.set_defaults(func=cmd_status)

    # reconcile
    rec_p = subparsers.add_parser("reconcile", help="Reconcile stale running jobs")
    rec_p.add_argument("campaign_id", type=str, nargs="?", default=None, help="Optional campaign ID")
    rec_p.add_argument("--force", action="store_true", help="Force reconciliation regardless of lease expiry")
    rec_p.set_defaults(func=cmd_reconcile)

    # job
    job_p = subparsers.add_parser("job", help="Show job details and event history")
    job_p.add_argument("job_id", type=str, help="Job ID")
    job_p.add_argument("--json", action="store_true", help="Output raw JSON")
    job_p.set_defaults(func=cmd_job)

    # approve
    app_p = subparsers.add_parser("approve", help="Approve a job waiting for approval")
    app_p.add_argument("job_id", type=str, help="Job ID to approve")
    app_p.set_defaults(func=cmd_approve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
