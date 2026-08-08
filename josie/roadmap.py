"""Read-only access to Josie's canonical Markdown roadmap."""

from __future__ import annotations

from pathlib import Path
import re


def roadmap_summary(project_root: Path) -> dict[str, object]:
    path = project_root / "docs" / "JOSIE_SETUP_CHECKLIST.md"
    if not path.exists():
        return {"status": "missing", "completed": 0, "pending": 0, "critical_path": []}
    text = path.read_text(encoding="utf-8")
    completed = len(re.findall(r"^- \[x\] ", text, flags=re.MULTILINE | re.IGNORECASE))
    pending = len(re.findall(r"^- \[ \] ", text, flags=re.MULTILINE))
    critical_match = re.search(
        r"^## Critical path\s*(.*?)(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL
    )
    critical_path: list[str] = []
    if critical_match:
        critical_path = [
            match.group(1).strip()
            for match in re.finditer(r"^\d+\.\s+(.+)$", critical_match.group(1), flags=re.MULTILINE)
        ]
    return {
        "status": "ok",
        "completed": completed,
        "pending": pending,
        "critical_path": critical_path,
        "path": str(path),
    }

