from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


class MissionStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, mission_id: str) -> Path:
        return self.directory / f"{mission_id}.json"

    def events_path(self, mission_id: str) -> Path:
        return self.directory / f"{mission_id}.events.jsonl"

    def create(self, mission: dict[str, Any]) -> Path:
        target = self.path(mission["mission_id"])
        if target.exists():
            raise FileExistsError(f"mission already exists: {mission['mission_id']}")
        self.save(mission)
        self.append_event(mission["mission_id"], {"event": "MISSION_CREATED", "at": mission["created_at"]})
        return target

    def load(self, mission_id: str) -> dict[str, Any]:
        return json.loads(self.path(mission_id).read_text(encoding="utf-8"))

    def save(self, mission: dict[str, Any]) -> Path:
        target = self.path(mission["mission_id"])
        temporary = self.directory / f".{target.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(mission, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    def append_event(self, mission_id: str, event: dict[str, Any]) -> None:
        with self.events_path(mission_id).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
