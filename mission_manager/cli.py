from __future__ import annotations

import argparse
import json
from pathlib import Path

from .campaign_bridge import CampaignBridge, MissionNotFoundError
from .dispatcher import MissionManager


def main() -> int:
    parser = argparse.ArgumentParser(prog="mission-manager")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("plan", type=Path)
    submit = commands.add_parser("submit")
    submit.add_argument("plan", type=Path)
    submit.add_argument("--json", action="store_true", help="emit only machine-readable mission JSON")
    status = commands.add_parser("status")
    status.add_argument("mission_id")
    status.add_argument("--json", action="store_true", help="emit only machine-readable mission JSON")
    dispatch = commands.add_parser("dispatch-next")
    dispatch.add_argument("mission_id")
    args = parser.parse_args()

    if args.command == "submit":
        bridge = CampaignBridge()
        plan_data = json.loads(args.plan.read_text(encoding="utf-8"))
        result = bridge.submit_mission(plan_data)
        print(json.dumps(result, indent=2) if args.json else bridge.render_mission_summary(result["mission_id"]))
        return 0

    if args.command == "status":
        bridge = CampaignBridge()
        try:
            b_status = bridge.get_mission_status(args.mission_id)
            print(json.dumps(b_status, indent=2) if args.json else bridge.render_mission_summary(args.mission_id))
            return 0
        except MissionNotFoundError:
            pass

    manager = MissionManager()
    if args.command == "create":
        result = manager.create(json.loads(args.plan.read_text(encoding="utf-8")))
        print(json.dumps(result, indent=2))
    elif args.command == "status":
        result = manager.status(args.mission_id)
        print(json.dumps(result["mission"], indent=2) if args.json else result["human"])
    else:
        result = manager.dispatch_next(args.mission_id)
        print(json.dumps(result, indent=2))
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
