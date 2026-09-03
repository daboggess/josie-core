"""Read-only Phase 0A backup coverage verifier.

This utility reports repository-local restoration inputs.  It never copies,
opens, hashes, or modifies the inputs it checks.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class BackupItem:
    path: str
    purpose: str
    required: bool = True
    sensitive: bool = False


DEFAULT_ITEMS = (
    BackupItem("data/josie.db", "primary SQLite durable state"),
    BackupItem("data/backups", "local SQLite recovery generations"),
    BackupItem("data/private", "private runtime state and worker receipts", sensitive=True),
    BackupItem("config", "policies and repository-local configuration"),
    BackupItem("deploy", "service definitions and integration helpers"),
    BackupItem(".env", "root secret configuration", sensitive=True),
    BackupItem("deploy/.env.services", "service secrets and image pins", sensitive=True),
    BackupItem("docs/identity", "locally owned identity and genesis records"),
    BackupItem("docs/constitution", "root governance records"),
)

EXTERNAL_DEPENDENCIES = (
    "Docker named volumes josie_open_webui_data and josie_n8n_data",
    "D:/Josie-Storage apps, models, evidence, proposals, status, secrets, and backups",
    "native Ollama user state and model/runtime compatibility",
    "Tailscale account recovery and Serve configuration",
    "matching authentication/encryption material for service databases",
)


def verify(root: Path, items: Iterable[BackupItem] = DEFAULT_ITEMS) -> dict:
    """Return an existence-only report without reading item contents."""
    root = root.resolve()
    results = []
    failures = []
    for item in items:
        target = root / item.path
        exists = target.exists()
        if item.required and not exists:
            failures.append(item.path)
        results.append({**asdict(item), "exists": exists})
    return {
        "mode": "dry-run",
        "root": str(root),
        "would_back_up": results,
        "external_dependencies_not_checked": list(EXTERNAL_DEPENDENCIES),
        "validation_failures": failures,
        "ok": not failures,
        "notice": "No files were copied, opened, hashed, or modified.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report Phase 0A backup coverage (dry-run only).")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = verify(args.root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("JOSIE backup verification: DRY RUN (no copies or content reads)")
        for item in report["would_back_up"]:
            marker = "FOUND" if item["exists"] else "MISSING"
            sensitivity = "; sensitive" if item["sensitive"] else ""
            print(f"[{marker}] {item['path']}: {item['purpose']}{sensitivity}")
        print("External dependencies not checked:")
        for dependency in report["external_dependencies_not_checked"]:
            print(f"- {dependency}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
