"""Local project-history provenance helpers."""

from __future__ import annotations

from pathlib import Path


INTERVIEW_QUESTIONS = (
    "What problem was Josie originally intended to solve?",
    "Which decisions came directly from Dustin, and which were suggestions?",
    "Why were the names Josie, Sophie, and Bernie chosen?",
    "Which safety and spending rules are permanent?",
    "What may Josie do autonomously when Dustin is unavailable?",
    "Which past decisions are obsolete or still disputed?",
    "Which private conversations may be imported, and at what level of detail?",
    "What does Josie 1.0 is alive mean as a verifiable acceptance test?",
)


def origin_workflow_status(project_root: Path) -> dict[str, object]:
    document = project_root / "docs" / "ORIGIN_AND_PROVENANCE.md"
    return {
        "status": "ready" if document.is_file() else "waiting",
        "document": str(document),
        "question_count": len(INTERVIEW_QUESTIONS),
        "cloud_activity": False,
        "automatic_import": False,
    }
