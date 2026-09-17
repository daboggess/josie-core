from __future__ import annotations

import argparse
import json
from pathlib import Path

from .coding_lane import CodingLaneRepair
from .models import RepairTicket


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded Josie Coding Lane Repair Worker v0")
    parser.add_argument("ticket", type=Path)
    args = parser.parse_args()
    ticket = RepairTicket.from_dict(json.loads(args.ticket.read_text(encoding="utf-8")))
    receipt = CodingLaneRepair().repair(ticket)
    print(json.dumps(receipt.to_dict(), indent=2, sort_keys=True))
    return 0 if receipt.final_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
