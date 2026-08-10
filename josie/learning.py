"""Bounded, local-only foundational learning with deterministic grounding checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .genesis import build_genesis_status
from .storage import LocalStore


CURRICULUM_PATH = Path("docs/learning/FOUNDATIONAL_CURRICULUM.json")
MAX_CURRICULUM_BYTES = 256_000
MAX_SOURCE_BYTES = 256_000
MAX_UNITS = 20
MAX_SOURCES_PER_UNIT = 10
MAX_CLAIMS_PER_UNIT = 20
MAX_CHECKS_PER_UNIT = 20


def _read_json(path: Path) -> tuple[dict[str, object], bytes]:
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_CURRICULUM_BYTES:
        raise ValueError("Foundational curriculum is empty or exceeds its size limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Foundational curriculum is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Foundational curriculum must be a JSON object")
    return payload, raw


def _text(value: object, *, label: str, maximum: int = 2_000) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    clean = value.strip()
    if not clean or len(clean) > maximum:
        raise ValueError(f"{label} must contain 1 to {maximum} characters")
    return clean


def _string_list(value: object, *, label: str, maximum: int) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label} must be a bounded list")
    return [_text(item, label=label) for item in value]


def _source_path(project_root: Path, relative: str) -> Path:
    if "\\" in relative:
        raise ValueError("Learning source paths must use repository-relative forward slashes")
    candidate = (project_root / relative).resolve()
    docs_root = (project_root / "docs").resolve()
    try:
        candidate.relative_to(docs_root)
    except ValueError as exc:
        raise ValueError("Learning sources must remain inside the versioned docs directory") from exc
    if not candidate.is_file():
        raise ValueError(f"Learning source does not exist: {relative}")
    return candidate


def load_foundational_curriculum(project_root: Path) -> dict[str, object]:
    payload, raw = _read_json(project_root / CURRICULUM_PATH)
    expected = {
        "schema_version", "curriculum_version", "status", "requirements", "units"
    }
    if set(payload) != expected or payload.get("schema_version") != 1:
        raise ValueError("Foundational curriculum top-level schema is invalid")
    version = _text(payload["curriculum_version"], label="Curriculum version", maximum=32)
    status = _text(payload["status"], label="Curriculum status", maximum=64)
    if status != "ACTIVE_BOUNDED_LOCAL_ONLY":
        raise ValueError("Foundational curriculum is not in its governed active state")
    requirements = payload["requirements"]
    if not isinstance(requirements, dict) or set(requirements) != {
        "genesis_phase", "api_budget_cents", "network_requests", "capability_change"
    }:
        raise ValueError("Foundational curriculum requirements are invalid")
    if requirements != {
        "genesis_phase": "complete",
        "api_budget_cents": 0,
        "network_requests": 0,
        "capability_change": "none",
    }:
        raise ValueError("Foundational curriculum attempts to exceed its authority")
    units = payload["units"]
    if not isinstance(units, list) or not units or len(units) > MAX_UNITS:
        raise ValueError("Foundational curriculum unit list is invalid")
    seen: set[str] = set()
    normalized_units: list[dict[str, object]] = []
    unit_keys = {
        "learning_id", "track", "title", "objective", "authority", "budgets",
        "sources", "claims", "contradictions", "corrections", "assessment",
        "capability_change",
    }
    for raw_unit in units:
        if not isinstance(raw_unit, dict) or set(raw_unit) != unit_keys:
            raise ValueError("Foundational learning unit schema is invalid")
        learning_id = _text(raw_unit["learning_id"], label="Learning ID", maximum=64).upper()
        if learning_id in seen:
            raise ValueError("Foundational curriculum contains duplicate learning IDs")
        seen.add(learning_id)
        budgets = raw_unit["budgets"]
        if not isinstance(budgets, dict) or set(budgets) != {
            "time_minutes", "api_cents", "network_requests", "storage_kb"
        }:
            raise ValueError("Learning budgets are invalid")
        if (
            not isinstance(budgets["time_minutes"], int)
            or not 1 <= budgets["time_minutes"] <= 30
            or budgets["api_cents"] != 0
            or budgets["network_requests"] != 0
            or not isinstance(budgets["storage_kb"], int)
            or not 1 <= budgets["storage_kb"] <= 256
        ):
            raise ValueError("Learning unit exceeds its local zero-spend budget")
        sources = _string_list(
            raw_unit["sources"], label="Learning source", maximum=MAX_SOURCES_PER_UNIT
        )
        if not sources:
            raise ValueError("Learning unit must cite at least one source")
        for source in sources:
            _source_path(project_root, source)
        claims = raw_unit["claims"]
        if not isinstance(claims, list) or not claims or len(claims) > MAX_CLAIMS_PER_UNIT:
            raise ValueError("Learning claims must be a non-empty bounded list")
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {
                "claim_id", "statement", "status", "source"
            }:
                raise ValueError("Learning claim schema is invalid")
            _text(claim["claim_id"], label="Learning claim ID", maximum=64)
            _text(claim["statement"], label="Learning claim", maximum=1_000)
            if claim["status"] not in {"ratified", "confirmed_canonical"}:
                raise ValueError("Foundational claims must already be ratified or canonical")
            if claim["source"] not in sources:
                raise ValueError("Learning claim cites a source outside its unit")
        contradictions = _string_list(
            raw_unit["contradictions"], label="Learning contradiction", maximum=20
        )
        corrections = _string_list(
            raw_unit["corrections"], label="Learning correction", maximum=20
        )
        assessment = raw_unit["assessment"]
        if (
            not isinstance(assessment, list)
            or not assessment
            or len(assessment) > MAX_CHECKS_PER_UNIT
        ):
            raise ValueError("Learning assessment must contain bounded grounding checks")
        for check in assessment:
            if not isinstance(check, dict) or set(check) != {
                "check_id", "source", "contains"
            }:
                raise ValueError("Learning assessment check schema is invalid")
            _text(check["check_id"], label="Assessment check ID", maximum=64)
            if check["source"] not in sources:
                raise ValueError("Learning assessment cites a source outside its unit")
            _text(check["contains"], label="Assessment evidence", maximum=500)
        if raw_unit["capability_change"] != "none":
            raise ValueError("Foundational learning cannot grant capability")
        normalized_units.append({
            **raw_unit,
            "learning_id": learning_id,
            "track": _text(raw_unit["track"], label="Learning track", maximum=64),
            "title": _text(raw_unit["title"], label="Learning title", maximum=200),
            "objective": _text(raw_unit["objective"], label="Learning objective", maximum=1_000),
            "authority": _text(raw_unit["authority"], label="Learning authority", maximum=500),
            "sources": sources,
            "contradictions": contradictions,
            "corrections": corrections,
        })
    return {
        "schema_version": 1,
        "curriculum_version": version,
        "status": status,
        "requirements": requirements,
        "units": normalized_units,
        "curriculum_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _grounded_unit_record(
    *, project_root: Path, curriculum_version: str, unit: dict[str, object]
) -> dict[str, object]:
    source_text: dict[str, str] = {}
    sources: list[dict[str, object]] = []
    for relative in unit["sources"]:
        path = _source_path(project_root, str(relative))
        raw = path.read_bytes()
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError(f"Learning source exceeds its size limit: {relative}")
        text = raw.decode("utf-8")
        source_text[str(relative)] = text
        sources.append({
            "path": str(relative),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "source_type": "versioned_canonical_document",
        })
    evidence: list[dict[str, object]] = []
    for check in unit["assessment"]:
        passed = str(check["contains"]) in source_text[str(check["source"])]
        evidence.append({
            "check_id": check["check_id"],
            "source": check["source"],
            "method": "exact_source_contains",
            "passed": passed,
        })
    passed = bool(evidence) and all(bool(item["passed"]) for item in evidence)
    assessment = {
        "kind": "deterministic_source_grounding",
        "passed": passed,
        "checks_passed": sum(1 for item in evidence if item["passed"]),
        "checks_total": len(evidence),
        "model_assessment_used": False,
    }
    record_without_digest: dict[str, object] = {
        "learning_id": unit["learning_id"],
        "curriculum_version": curriculum_version,
        "track": unit["track"],
        "title": unit["title"],
        "objective": unit["objective"],
        "status": "complete" if passed else "attention_required",
        "authority": unit["authority"],
        "budgets": unit["budgets"],
        "sources": sources,
        "evidence": evidence,
        "claims": unit["claims"],
        "contradictions": unit["contradictions"],
        "corrections": unit["corrections"],
        "assessment": assessment,
        "capability_change": "none",
    }
    digest = hashlib.sha256(
        json.dumps(record_without_digest, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()
    return {**record_without_digest, "unit_digest": digest}


def sync_foundational_curriculum(
    *, project_root: Path, store: LocalStore
) -> dict[str, object]:
    genesis = build_genesis_status(project_root=project_root)
    if genesis["phase"] != "complete" or genesis["status"] != "complete":
        raise RuntimeError("Foundational learning requires completed, ratified Genesis")
    curriculum = load_foundational_curriculum(project_root)
    results: list[dict[str, object]] = []
    for unit in curriculum["units"]:
        record = _grounded_unit_record(
            project_root=project_root,
            curriculum_version=str(curriculum["curriculum_version"]),
            unit=unit,
        )
        stored = store.upsert_learning_unit(record)
        results.append({
            "learning_id": stored["learning_id"],
            "title": stored["title"],
            "status": stored["status"],
            "changed": stored["changed"],
            "version_added": stored["version_added"],
            "assessment": stored["assessment"],
        })
    summary = store.learning_summary()
    return {
        "status": summary["status"],
        "curriculum_version": curriculum["curriculum_version"],
        "curriculum_sha256": curriculum["curriculum_sha256"],
        "units": results,
        "summary": summary,
        "genesis_required": "complete",
        "capability_change": "none",
        "cloud_activity": False,
        "network_requests": 0,
        "api_spending_cents": 0,
        "actions_queued": 0,
        "actions_executed": 0,
    }


def foundational_learning_status(
    *, project_root: Path, store: LocalStore
) -> dict[str, object]:
    curriculum = load_foundational_curriculum(project_root)
    summary = store.learning_summary()
    stored_units = {
        str(unit["learning_id"]): unit for unit in store.learning_units()
    }
    drifted_units: list[str] = []
    expected_ids: set[str] = set()
    for unit in curriculum["units"]:
        expected = _grounded_unit_record(
            project_root=project_root,
            curriculum_version=str(curriculum["curriculum_version"]),
            unit=unit,
        )
        learning_id = str(expected["learning_id"])
        expected_ids.add(learning_id)
        stored = stored_units.get(learning_id)
        if (
            stored is None
            or stored["unit_digest"] != expected["unit_digest"]
            or stored["status"] != expected["status"]
        ):
            drifted_units.append(learning_id)
    unexpected_units = sorted(set(stored_units) - expected_ids)
    effective_status = (
        "ok"
        if summary["status"] == "ok" and not drifted_units and not unexpected_units
        else "attention_required"
    )
    attention_count = int(summary["units_by_status"]["attention_required"]) + len(
        set(drifted_units + unexpected_units)
    )
    return {
        **summary,
        "status": effective_status,
        "phase": "foundational_learning",
        "curriculum_version": curriculum["curriculum_version"],
        "curriculum_sha256": curriculum["curriculum_sha256"],
        "curriculum_units": len(curriculum["units"]),
        "drifted_or_missing_units": sorted(drifted_units),
        "unexpected_units": unexpected_units,
        "source_drift_detected": bool(drifted_units or unexpected_units),
        "attention_count": attention_count,
        "in_sync": attention_count == 0,
        "genesis_phase": build_genesis_status(project_root=project_root)["phase"],
        "read_only": True,
    }


def foundational_learning_unit(*, store: LocalStore, learning_id: str) -> dict[str, object]:
    record = store.learning_unit(learning_id)
    return {
        **record,
        "read_only": True,
        "external_activity": False,
        "actions_queued": 0,
        "actions_executed": 0,
    }
