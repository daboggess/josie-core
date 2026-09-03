"""Safe manifest validation and an isolated Phase 0B restore fixture."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

REQUIRED_FIELDS = {
    "id", "capability", "restore_priority", "state_type", "sensitivity",
    "backup_required", "rebuildable", "verification_method", "restore_method",
    "interactive_dustin_required", "currently_verified", "notes",
}
FIXTURE_FILES = {
    "identity.txt": b"JOSIE-HARBOR-FREIGHT-PHASE0B\n",
    "state/config.json": b'{"fixture":true,"schema":1}\n',
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("objectives"), dict):
        raise ValueError("unsupported schema or missing objectives")
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("entries must be a non-empty list")
    seen = set()
    for entry in entries:
        missing = REQUIRED_FIELDS - entry.keys()
        if missing or not (entry.get("path") or entry.get("discovery_rule")):
            raise ValueError(f"invalid entry {entry.get('id')!r}: missing {sorted(missing)} or location")
        if entry["id"] in seen or entry["restore_priority"] not in {"CORE", "FULL_DATA"}:
            raise ValueError(f"invalid id or priority: {entry['id']!r}")
        if not isinstance(entry["currently_verified"], bool):
            raise ValueError(f"currently_verified must be boolean: {entry['id']}")
        seen.add(entry["id"])
    return data


def run_fixture(work_root: Path) -> dict:
    """Round-trip known files below an empty caller-provided temporary directory."""
    work_root = work_root.resolve()
    if work_root.exists() and any(work_root.iterdir()):
        raise ValueError("fixture root must be empty")
    source, backup, restored = (work_root / name for name in ("source", "backup", "restored"))
    try:
        for relative, content in FIXTURE_FILES.items():
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        expected = {name: sha256(source / name) for name in FIXTURE_FILES}
        shutil.copytree(source, backup)
        shutil.rmtree(source)  # only fixture data created above
        shutil.copytree(backup, restored)
        actual = {name: sha256(restored / name) for name in FIXTURE_FILES}
        return {"status": "PASS" if actual == expected else "FAIL", "checksums": actual}
    finally:
        for target in (source, backup, restored):
            if target.exists():
                shutil.rmtree(target)
