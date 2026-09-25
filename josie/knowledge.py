"""Josie Canonical Knowledge Layer.

Connects Josie's persistent memory and canonical documents to deterministic
task-specific priming (supervisor/priming.py) and Prompt Contracts.

Epistemic Architecture:
    The Python definitions here are SEED SPECIFICATIONS / BOOTSTRAP SNAPSHOTS,
    not an independent source of truth. Authoritative truth derives from
    Dustin's explicit intent, ratified constitutional documents, versioned
    governance records, and persistent human adjudications.

    Architecture (adapted Jarvis / AI Memory Vault pattern):
    raw evidence (files, documents, history)
    -> provenance-aware claims (memory_claims, claim_evidence)
    -> organized canonical knowledge (KnowledgeRecord, KnowledgeQuery)
    -> task-specific priming (PrimingManifest, PrimingBundle)
    -> Prompt Contract / Work Order
    -> worker
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Sequence

from supervisor.priming import (
    PrimingBundle,
    PrimingItem,
    PrimingManifest,
    assemble_priming_bundle,
)
from josie.storage import LocalStore


KNOWLEDGE_SCHEMA_VERSION = "1.0"
SUPPORTED_KNOWLEDGE_SCHEMA_VERSIONS = frozenset({"1.0"})

ALLOWED_STATUSES = frozenset({
    "active",
    "confirmed",
    "candidate",
    "disputed",
    "superseded",
    "rejected",
})

ALLOWED_CONFIDENCES = frozenset({"high", "medium", "low"})

ALLOWED_EVIDENCE_CLASSES = frozenset({
    "CANONICAL",
    "VERIFIED",
    "RETRIEVED",
    "INFERRED",
    "UNKNOWN",
})

# Status ranking: active/confirmed first; candidate/disputed lower; superseded/rejected last
STATUS_ORDER = {
    "confirmed": 0,
    "active": 1,
    "candidate": 2,
    "disputed": 3,
    "superseded": 4,
    "rejected": 5,
}

# Generic evidence semantics: CANONICAL / VERIFIED > RETRIEVED > INFERRED > UNKNOWN
EVIDENCE_CLASS_ORDER = {
    "CANONICAL": 0,
    "VERIFIED": 0,
    "RETRIEVED": 1,
    "INFERRED": 2,
    "UNKNOWN": 3,
}

CONFIDENCE_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


@dataclass(frozen=True)
class KnowledgeRecord:
    """Structured knowledge claim with strict provenance and supersession tracking."""

    record_id: str
    category: str
    content: str
    source_kind: str
    source_reference: str
    timestamp: str
    confidence: str = "high"
    status: str = "active"
    evidence_class: str = "CANONICAL"
    superseded_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not self.record_id.strip():
            raise ValueError("KnowledgeRecord.record_id must be a nonempty string")
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValueError("KnowledgeRecord.category must be a nonempty string")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("KnowledgeRecord.content must be a nonempty string")
        if not isinstance(self.source_kind, str) or not self.source_kind.strip():
            raise ValueError("KnowledgeRecord.source_kind must be a nonempty string")
        if not isinstance(self.source_reference, str) or not self.source_reference.strip():
            raise ValueError("KnowledgeRecord.source_reference must be a nonempty string")
        if not isinstance(self.timestamp, str) or not self.timestamp.strip():
            raise ValueError("KnowledgeRecord.timestamp must be a nonempty string")
        if not isinstance(self.confidence, str) or self.confidence.strip().lower() not in ALLOWED_CONFIDENCES:
            raise ValueError(
                f"KnowledgeRecord.confidence must be one of {sorted(ALLOWED_CONFIDENCES)}, got {self.confidence!r}"
            )
        if not isinstance(self.status, str) or self.status.strip().lower() not in ALLOWED_STATUSES:
            raise ValueError(
                f"KnowledgeRecord.status must be one of {sorted(ALLOWED_STATUSES)}, got {self.status!r}"
            )
        if (
            not isinstance(self.evidence_class, str)
            or self.evidence_class.strip().upper() not in ALLOWED_EVIDENCE_CLASSES
        ):
            raise ValueError(
                f"KnowledgeRecord.evidence_class must be one of {sorted(ALLOWED_EVIDENCE_CLASSES)}, got {self.evidence_class!r}"
            )
        if self.superseded_by is not None:
            if not isinstance(self.superseded_by, str) or not self.superseded_by.strip():
                raise ValueError("KnowledgeRecord.superseded_by must be a nonempty string if provided")

    @property
    def record_hash(self) -> str:
        payload = {
            "record_id": self.record_id.strip(),
            "category": self.category.strip().lower(),
            "content": self.content.strip(),
            "source_kind": self.source_kind.strip().lower(),
            "source_reference": self.source_reference.strip(),
            "timestamp": self.timestamp.strip(),
            "confidence": self.confidence.strip().lower(),
            "status": self.status.strip().lower(),
            "evidence_class": self.evidence_class.strip().upper(),
            "superseded_by": self.superseded_by.strip() if self.superseded_by else None,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def is_current(self) -> bool:
        """True if the record is active/confirmed and not superseded."""
        return self.status.strip().lower() in ("active", "confirmed") and not self.superseded_by

    def is_superseded(self) -> bool:
        """True if marked superseded or superseded_by is populated."""
        return self.status.strip().lower() == "superseded" or self.superseded_by is not None

    def is_rejected(self) -> bool:
        """True if explicitly marked rejected."""
        return self.status.strip().lower() == "rejected"

    def to_priming_item(self) -> PrimingItem:
        """Convert this knowledge record into a deterministic PrimingItem."""
        return PrimingItem(
            item_id=self.record_id.strip(),
            excerpt=self.content.strip(),
            category=self.category.strip().lower(),
            source_kind=self.source_kind.strip().lower(),
            source_reference=self.source_reference.strip(),
            confidence=self.confidence.strip().lower(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "category": self.category,
            "content": self.content,
            "source_kind": self.source_kind,
            "source_reference": self.source_reference,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "status": self.status,
            "evidence_class": self.evidence_class,
            "superseded_by": self.superseded_by,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeRecord:
        if not isinstance(data, dict):
            raise ValueError("KnowledgeRecord input data must be a dict")
        record_id = str(data.get("record_id") or data.get("claim_id") or data.get("item_id") or "").strip()
        category = str(data.get("category") or data.get("memory_layer") or "general").strip()
        content = str(
            data.get("content")
            or data.get("value_text")
            or data.get("excerpt")
            or data.get("claim")
            or ""
        ).strip()
        source_kind = str(
            data.get("source_kind") or data.get("source_type") or data.get("evidence_class") or "canonical_versioned"
        ).strip()
        source_reference = str(
            data.get("source_reference") or data.get("source_pointer") or data.get("locator") or ""
        ).strip()
        timestamp = str(
            data.get("timestamp") or data.get("created_at") or data.get("reviewed_at") or "2026-08-09"
        ).strip()

        conf_raw = data.get("confidence", "high")
        if isinstance(conf_raw, (int, float)):
            if conf_raw >= 0.8:
                confidence = "high"
            elif conf_raw >= 0.5:
                confidence = "medium"
            else:
                confidence = "low"
        else:
            confidence = str(conf_raw).strip().lower()

        status = str(data.get("status") or "active").strip().lower()
        evidence_class = str(
            data.get("evidence_class")
            or ("CANONICAL" if source_kind in ("constitution", "canonical_versioned") else "RETRIEVED")
        ).strip().upper()

        superseded_by = data.get("superseded_by") or data.get("superseded_by_claim_id")
        if superseded_by:
            superseded_by = str(superseded_by).strip()
        else:
            superseded_by = None

        metadata = data.get("metadata")
        clean_metadata = dict(metadata) if isinstance(metadata, dict) else {}

        return cls(
            record_id=record_id,
            category=category,
            content=content,
            source_kind=source_kind,
            source_reference=source_reference,
            timestamp=timestamp,
            confidence=confidence,
            status=status,
            evidence_class=evidence_class,
            superseded_by=superseded_by,
            metadata=clean_metadata,
        )


@dataclass(frozen=True)
class KnowledgeQuery:
    """Deterministic filter criteria for structured knowledge records."""

    categories: tuple[str, ...] = ()
    source_kinds: tuple[str, ...] = ()
    source_references: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ("active", "confirmed")
    include_superseded: bool = False
    include_rejected: bool = False
    exclusions: tuple[str, ...] = ()
    max_records: int | None = None
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_KNOWLEDGE_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported knowledge schema_version: {self.schema_version!r}")
        if self.max_records is not None and self.max_records <= 0:
            raise ValueError("max_records must be positive if specified")

    def matches(self, record: KnowledgeRecord) -> bool:
        """Check whether a knowledge record matches query constraints."""
        # Exclusions filter
        if self.exclusions:
            exclusion_set = {e.strip().lower() for e in self.exclusions if e.strip()}
            if record.record_id.lower() in exclusion_set:
                return False
            if record.category.lower() in exclusion_set:
                return False
            if record.source_reference.lower() in exclusion_set:
                return False

        # Status filter
        if record.is_superseded() and not self.include_superseded:
            return False
        if record.is_rejected() and not self.include_rejected:
            return False

        if self.statuses:
            status_set = {s.strip().lower() for s in self.statuses if s.strip()}
            if self.include_superseded:
                status_set.add("superseded")
            if self.include_rejected:
                status_set.add("rejected")
            if record.status.lower() not in status_set:
                return False

        # Category filter
        if self.categories:
            category_set = {c.strip().lower() for c in self.categories if c.strip()}
            if record.category.lower() not in category_set:
                return False

        # Source kind filter
        if self.source_kinds:
            kind_set = {k.strip().lower() for k in self.source_kinds if k.strip()}
            if record.source_kind.lower() not in kind_set:
                return False

        # Source reference filter
        if self.source_references:
            ref_set = {r.strip() for r in self.source_references if r.strip()}
            if record.source_reference not in ref_set:
                return False

        return True


# Durable Initial Proof Seeds:
# These specifications are bootstrap snapshots of durable constitutional,
# architectural, procedural, and witness records. They are explicitly NOT
# a standalone source of truth and exclude volatile or unverified hardware states.
BOOTSTRAP_KNOWLEDGE_SEEDS: tuple[KnowledgeRecord, ...] = (
    KnowledgeRecord(
        record_id="identity:dustin-authority",
        category="identity",
        content="Dustin is final human authority for his intentions, delegated permissions, consequential outward actions, and constitutional amendments. Josie must not impersonate Dustin, manufacture approval, or treat silence as consent.",
        source_kind="constitution",
        source_reference="docs/constitution/JOSIE_CONSTITUTION.md#human-authority",
        timestamp="2026-08-09",
        confidence="high",
        status="active",
        evidence_class="CANONICAL",
        metadata={
            "predicate": "human_authority",
            "subject_entity_id": "person:dustin",
            "canonical_effect": 1,
            "approved_by": "Dustin",
            "source_excerpt_sha256": hashlib.sha256(
                "Dustin is final human authority for his intentions, delegated permissions, consequential outward actions, and constitutional amendments. Josie must not impersonate Dustin, manufacture approval, or treat silence as consent.".encode("utf-8")
            ).hexdigest(),
        },
    ),
    KnowledgeRecord(
        record_id="arch:supervisor-worker-separation",
        category="architecture",
        content="Josie enforces strict Supervisor and worker separation: the deterministic supervisor compiles immutable Prompt Contracts with bounded evidence; workers have no authority over protected memory or self-certification.",
        source_kind="canonical_versioned",
        source_reference="supervisor/README.md#prompt-contract-v10",
        timestamp="2026-09-09",
        confidence="high",
        status="active",
        evidence_class="CANONICAL",
        metadata={
            "predicate": "supervisor_worker_boundary",
            "subject_entity_id": "system:josie",
            "canonical_effect": 1,
            "approved_by": "Dustin",
            "source_excerpt_sha256": hashlib.sha256(
                "Josie enforces strict Supervisor and worker separation: the deterministic supervisor compiles immutable Prompt Contracts with bounded evidence; workers have no authority over protected memory or self-certification.".encode("utf-8")
            ).hexdigest(),
        },
    ),
    KnowledgeRecord(
        record_id="arch:identity-above-models",
        category="architecture",
        content="Josie's identity, memory, Constitution, and authority remain above replaceable local or cloud model weights.",
        source_kind="canonical_versioned",
        source_reference="docs/identity/genesis/CLAIM_LEDGER.yaml#GEN-CLM-009",
        timestamp="2026-08-09",
        confidence="high",
        status="active",
        evidence_class="CANONICAL",
        metadata={
            "predicate": "identity_above_models",
            "subject_entity_id": "system:josie",
            "canonical_effect": 1,
            "approved_by": "Dustin",
            "source_excerpt_sha256": hashlib.sha256(
                "Josie's identity, memory, Constitution, and authority remain above replaceable local or cloud model weights.".encode("utf-8")
            ).hexdigest(),
        },
    ),
    KnowledgeRecord(
        record_id="procedure:destructive-action-gate",
        category="procedure",
        content="Capability is not authority; permission scales with consequence. Irreversible, outward, privileged, financial, identity, and safety-sensitive actions require explicit Dustin approval and fail closed.",
        source_kind="constitution",
        source_reference="docs/constitution/JOSIE_CONSTITUTION.md#governing-principles",
        timestamp="2026-08-09",
        confidence="high",
        status="active",
        evidence_class="CANONICAL",
        metadata={
            "predicate": "consequential_action_boundary",
            "subject_entity_id": "system:josie",
            "canonical_effect": 1,
            "approved_by": "Dustin",
            "source_excerpt_sha256": hashlib.sha256(
                "Capability is not authority; permission scales with consequence. Irreversible, outward, privileged, financial, identity, and safety-sensitive actions require explicit Dustin approval and fail closed.".encode("utf-8")
            ).hexdigest(),
        },
    ),
    KnowledgeRecord(
        record_id="witness:genesis-clm-012-bernie-values",
        category="identity",
        content="Faith, family, and debt freedom were Bernie-specific context resolved by Dustin as not being Josie constitutional values.",
        source_kind="witness_adjudication",
        source_reference="docs/identity/genesis/CLAIM_LEDGER.yaml#GEN-CLM-012",
        timestamp="2026-08-09",
        confidence="high",
        status="rejected",
        evidence_class="RETRIEVED",
        metadata={
            "predicate": "constitutional_values",
            "subject_entity_id": "assistant:bernie",
            "canonical_effect": 0,
            "resolution": "RESOLVED_BERNIE_SPECIFIC_NOT_JOSIE",
            "source_excerpt_sha256": hashlib.sha256(
                "Faith, family, and debt freedom were Bernie-specific context resolved by Dustin as not being Josie constitutional values.".encode("utf-8")
            ).hexdigest(),
        },
    ),
)

# Backwards compatibility alias
CANONICAL_KNOWLEDGE_RECORDS = BOOTSTRAP_KNOWLEDGE_SEEDS


def sort_knowledge_records(records: Iterable[KnowledgeRecord]) -> list[KnowledgeRecord]:
    """Sort knowledge records deterministically.

    Ranking priority:
    1. Status order (active/confirmed first; candidate/disputed lower; superseded/rejected last)
    2. Evidence class order (CANONICAL / VERIFIED first; RETRIEVED next; INFERRED next; UNKNOWN last)
    3. Confidence order (high -> medium -> low)
    4. Category (alphabetical)
    5. Record ID (alphabetical tie-breaker)
    6. Source reference (alphabetical tie-breaker)
    """
    return sorted(
        records,
        key=lambda r: (
            STATUS_ORDER.get(r.status.lower(), 99),
            EVIDENCE_CLASS_ORDER.get(r.evidence_class.upper(), 99),
            CONFIDENCE_ORDER.get(r.confidence.lower(), 99),
            r.category.lower(),
            r.record_id,
            r.source_reference,
        ),
    )


@dataclass(frozen=True)
class SeedResult:
    """Explicit result of a bootstrap knowledge seed operation."""

    entities_seeded: int
    inserted: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    conflicts: tuple[dict[str, Any], ...] = ()
    dry_run: bool = False

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0

    @property
    def claims_seeded(self) -> int:
        return len(self.inserted)

    @property
    def evidence_seeded(self) -> int:
        return len(self.inserted)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities_seeded": self.entities_seeded,
            "claims_seeded": self.claims_seeded,
            "evidence_seeded": self.evidence_seeded,
            "inserted": list(self.inserted),
            "unchanged": list(self.unchanged),
            "conflicts": list(self.conflicts),
            "has_conflicts": self.has_conflicts,
            "dry_run": self.dry_run,
        }


def seed_canonical_knowledge(
    store: LocalStore,
    seeds: Sequence[KnowledgeRecord] | None = None,
    dry_run: bool = False,
) -> SeedResult:
    """Seed bootstrap knowledge records into Josie's SQLite store with overwrite protection.

    Human-adjudication overwrite protection rules:
    - NEW CLAIM ID: Insert bootstrap record (or report as would-insert if dry_run).
    - EXISTING CLAIM ID + materially identical canonical record: Leave unchanged.
    - EXISTING CLAIM ID + different content/status/provenance: DO NOT overwrite.
      Preserve previous persisted claim and record deterministic conflict/drift.
    - When dry_run=True: absolutely no database mutations are performed.
    """
    target_seeds = BOOTSTRAP_KNOWLEDGE_SEEDS if seeds is None else tuple(seeds)
    now = store._now()
    entities = [
        ("person:dustin", "Dustin", "dustin", "person", "Primary human authority and system creator.", "active"),
        ("system:josie", "Josie", "josie", "system", "Persistent local-first AI orchestration system.", "active"),
        (
            "assistant:bernie",
            "Bernie",
            "bernie",
            "prior_assistant_project",
            "Prior assistant project represented in imported history.",
            "active",
        ),
    ]

    entities_seeded = 0
    inserted: list[str] = []
    unchanged: list[str] = []
    conflicts: list[dict[str, Any]] = []

    with store._connect() as conn:
        for eid, cname, nname, etype, desc, stat in entities:
            if not dry_run:
                conn.execute(
                    "INSERT INTO entities(entity_id, canonical_name, normalized_name, entity_type, description, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(entity_id) DO UPDATE SET "
                    "canonical_name=excluded.canonical_name, normalized_name=excluded.normalized_name, "
                    "entity_type=excluded.entity_type, description=excluded.description, status=excluded.status, updated_at=excluded.updated_at",
                    (eid, cname, nname, etype, desc, stat, now, now),
                )
            entities_seeded += 1

        for r in target_seeds:
            existing = conn.execute(
                "SELECT claim_id, value_text, status, evidence_class, authority_scope, confidence, "
                "superseded_by_claim_id, canonical_effect, approved_by, reviewed_at "
                "FROM memory_claims WHERE claim_id = ?",
                (r.record_id,),
            ).fetchone()

            if existing is None:
                # NEW CLAIM: Insert bootstrap record
                if not dry_run:
                    meta = r.metadata
                    subject_id = meta.get("subject_entity_id", "system:josie")
                    predicate = meta.get("predicate", "statement")
                    canonical_effect = 1 if (r.status == "active" and r.evidence_class == "CANONICAL" and meta.get("approved_by")) else 0
                    approved_by = meta.get("approved_by") if canonical_effect == 1 else None
                    reviewed_at = (r.timestamp + "T00:00:00Z") if canonical_effect == 1 else None

                    layer_map = {
                        "identity": "identity",
                        "architecture": "procedural",
                        "procedure": "procedural",
                        "hardware": "semantic",
                        "project_state": "semantic",
                    }
                    memory_layer = layer_map.get(r.category, "semantic")
                    conf_val = 1.0 if r.confidence == "high" else (0.7 if r.confidence == "medium" else 0.3)

                    conn.execute(
                        "INSERT INTO memory_claims("
                        "claim_id, subject_entity_id, predicate, value_text, memory_layer, status, evidence_class, "
                        "authority_scope, confidence, confidence_basis, created_at, updated_at, approved_by, reviewed_at, "
                        "canonical_effect, superseded_by_claim_id, version"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                        (
                            r.record_id,
                            subject_id,
                            predicate,
                            r.content,
                            memory_layer,
                            r.status,
                            r.evidence_class,
                            f"{r.source_kind}:{r.category}",
                            conf_val,
                            f"Canonical record from {r.source_reference}",
                            now,
                            now,
                            approved_by,
                            reviewed_at,
                            canonical_effect,
                            r.superseded_by,
                        ),
                    )

                    evidence_id = f"ev:{r.record_id}"
                    relation_type = "supersedes" if r.superseded_by else "supports"
                    excerpt_sha = hashlib.sha256(r.content.encode("utf-8")).hexdigest()
                    conn.execute(
                        "INSERT INTO claim_evidence("
                        "claim_id, evidence_id, relation_type, source_type, source_pointer, evidence_class, excerpt_sha256, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            r.record_id,
                            evidence_id,
                            relation_type,
                            r.source_kind,
                            r.source_reference,
                            r.evidence_class,
                            excerpt_sha,
                            now,
                        ),
                    )
                inserted.append(r.record_id)
            else:
                # EXISTING CLAIM: Check for material drift/conflict
                persisted_text = str(existing["value_text"] or "")
                persisted_status = str(existing["status"] or "")
                persisted_class = str(existing["evidence_class"] or "")
                persisted_sup = existing["superseded_by_claim_id"]

                existing_evidence = conn.execute(
                    "SELECT excerpt_sha256 FROM claim_evidence WHERE claim_id = ?",
                    (r.record_id,),
                ).fetchall()
                persisted_shas = {str(row["excerpt_sha256"]) for row in existing_evidence if row["excerpt_sha256"]}
                seed_sha = hashlib.sha256(r.content.strip().encode("utf-8")).hexdigest()

                differences: list[str] = []
                if persisted_text.strip() != r.content.strip():
                    differences.append(f"content mismatch (persisted={persisted_text[:40]!r}..., seed={r.content[:40]!r}...)")
                if persisted_status.strip().lower() != r.status.strip().lower():
                    differences.append(f"status mismatch (persisted={persisted_status!r}, seed={r.status!r})")
                if persisted_class.strip().upper() != r.evidence_class.strip().upper():
                    differences.append(f"evidence_class mismatch (persisted={persisted_class!r}, seed={r.evidence_class!r})")
                if (persisted_sup or None) != (r.superseded_by or None):
                    differences.append(f"superseded_by mismatch (persisted={persisted_sup!r}, seed={r.superseded_by!r})")
                if persisted_shas and seed_sha not in persisted_shas:
                    differences.append("excerpt_sha256 drift")

                if differences:
                    # CONFLICT / DRIFT: DO NOT overwrite persisted human/adjudicated knowledge
                    conflicts.append({
                        "claim_id": r.record_id,
                        "differences": differences,
                        "persisted": {
                            "value_text": persisted_text,
                            "status": persisted_status,
                            "evidence_class": persisted_class,
                            "superseded_by": persisted_sup,
                        },
                        "seed": {
                            "value_text": r.content,
                            "status": r.status,
                            "evidence_class": r.evidence_class,
                            "superseded_by": r.superseded_by,
                        },
                    })
                else:
                    unchanged.append(r.record_id)

    return SeedResult(
        entities_seeded=entities_seeded,
        inserted=tuple(inserted),
        unchanged=tuple(unchanged),
        conflicts=tuple(conflicts),
        dry_run=dry_run,
    )


def bootstrap_canonical_knowledge(
    store: LocalStore,
    seeds: Sequence[KnowledgeRecord] | None = None,
    *,
    dry_run: bool = False,
    backup: bool = True,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    """Safe canonical-knowledge bootstrap entrypoint supporting dry-run and backup.

    Requirements:
    - Dry-run mode inspects target database without mutation.
    - Rollback and abort on unexpected conflict/drift.
    - Creates a pre-mutation SQLite checkpoint backup using native LocalStore.create_checkpoint_backup.
    - Reports target database path, counts, inserted/would_insert, unchanged, conflicts, and backup path.
    """
    target_db = str(store.path.resolve())

    # 1. Always inspect first (dry run)
    inspection = seed_canonical_knowledge(store, seeds=seeds, dry_run=True)

    if dry_run:
        return {
            "status": "dry_run",
            "dry_run": True,
            "target_db": target_db,
            "would_insert": list(inspection.inserted),
            "unchanged": list(inspection.unchanged),
            "conflicts": list(inspection.conflicts),
            "has_conflicts": inspection.has_conflicts,
            "entities_seeded": inspection.entities_seeded,
            "claims_seeded": inspection.claims_seeded,
            "evidence_seeded": inspection.evidence_seeded,
            "backup_path": None,
        }

    # 2. Live execution: check for conflict/drift
    if inspection.has_conflicts:
        return {
            "status": "conflict_stopped",
            "dry_run": False,
            "target_db": target_db,
            "would_insert": list(inspection.inserted),
            "unchanged": list(inspection.unchanged),
            "conflicts": list(inspection.conflicts),
            "has_conflicts": True,
            "error": "Unexpected conflict/drift detected before bootstrap mutation; stopped without writing.",
            "backup_path": None,
            "entities_seeded": 0,
            "claims_seeded": 0,
            "evidence_seeded": 0,
        }

    # 3. No-op check: if all seeds are already unchanged, return success without backup or write transaction
    if len(inspection.inserted) == 0:
        return {
            "status": "success",
            "dry_run": False,
            "target_db": target_db,
            "inserted": [],
            "unchanged": list(inspection.unchanged),
            "conflicts": [],
            "has_conflicts": False,
            "entities_seeded": inspection.entities_seeded,
            "claims_seeded": 0,
            "evidence_seeded": 0,
            "backup_path": None,
        }

    # 4. Mutation required: create pre-mutation backup using existing project mechanism
    backup_path: str | None = None
    if backup and store.path.exists():
        bdir = backup_dir or (store.path.parent / "backups")
        backup_file = store.create_checkpoint_backup(bdir, label="canonical-bootstrap")
        backup_path = str(backup_file.resolve())

    # 5. Perform live mutation inside SQLite transaction
    live_result = seed_canonical_knowledge(store, seeds=seeds, dry_run=False)

    if live_result.has_conflicts:
        return {
            "status": "conflict_observed",
            "dry_run": False,
            "target_db": target_db,
            "inserted": list(live_result.inserted),
            "unchanged": list(live_result.unchanged),
            "conflicts": list(live_result.conflicts),
            "has_conflicts": True,
            "error": "Conflict observed during live bootstrap; preserved existing persisted claims.",
            "backup_path": backup_path,
            "entities_seeded": live_result.entities_seeded,
            "claims_seeded": live_result.claims_seeded,
            "evidence_seeded": live_result.evidence_seeded,
        }

    return {
        "status": "success",
        "dry_run": False,
        "target_db": target_db,
        "inserted": list(live_result.inserted),
        "unchanged": list(live_result.unchanged),
        "conflicts": list(live_result.conflicts),
        "has_conflicts": False,
        "entities_seeded": live_result.entities_seeded,
        "claims_seeded": live_result.claims_seeded,
        "evidence_seeded": live_result.evidence_seeded,
        "backup_path": backup_path,
    }


def load_knowledge_from_store(store: LocalStore) -> list[KnowledgeRecord]:
    """Load KnowledgeRecord instances from SQLite memory_claims + claim_evidence.

    Guarantees 1:1 mapping between memory_claims and KnowledgeRecord (the claim is
    the semantic unit of priming). Preserves all associated evidence rows in metadata.
    """
    records: list[KnowledgeRecord] = []
    with store._connect() as conn:
        claims = conn.execute(
            "SELECT claim_id, subject_entity_id, predicate, value_text, memory_layer, "
            "status, evidence_class, authority_scope, confidence, created_at, "
            "superseded_by_claim_id, supersedes_claim_id, approved_by, reviewed_at, canonical_effect, "
            "durability, valid_from, valid_until, valid_to "
            "FROM memory_claims "
            "ORDER BY claim_id"
        ).fetchall()

        if not claims:
            return []

        all_evidence = conn.execute(
            "SELECT claim_id, evidence_id, relation_type, source_type, source_pointer, "
            "evidence_class, excerpt_sha256, created_at "
            "FROM claim_evidence "
            "ORDER BY claim_id, relation_type, evidence_id"
        ).fetchall()

        evidence_by_claim: dict[str, list[dict[str, Any]]] = {}
        for ev in all_evidence:
            cid = str(ev["claim_id"])
            evidence_by_claim.setdefault(cid, []).append({
                "evidence_id": str(ev["evidence_id"]),
                "relation_type": str(ev["relation_type"]),
                "source_kind": str(ev["source_type"]),
                "source_reference": str(ev["source_pointer"]),
                "evidence_class": str(ev["evidence_class"]),
                "excerpt_sha256": str(ev["excerpt_sha256"] or ""),
                "created_at": str(ev["created_at"]),
            })

        for row in claims:
            cid = str(row["claim_id"])
            evidence_list = evidence_by_claim.get(cid, [])

            primary_evidence: dict[str, Any] | None = None
            if evidence_list:
                sorted_ev = sorted(
                    evidence_list,
                    key=lambda e: (0 if e["relation_type"] == "supports" else 1, e["evidence_id"]),
                )
                primary_evidence = sorted_ev[0]

            source_kind = (
                primary_evidence["source_kind"]
                if primary_evidence
                else str(row["evidence_class"] or "canonical_versioned")
            )
            source_reference = (
                primary_evidence["source_reference"]
                if primary_evidence
                else f"claims/{cid}"
            )

            auth_scope = str(row["authority_scope"] or "")
            if ":" in auth_scope:
                category = auth_scope.split(":", 1)[1]
            else:
                category = str(row["memory_layer"])

            content = str(row["value_text"] or "")
            timestamp = str(row["created_at"] or "")
            if "T" in timestamp:
                timestamp = timestamp.split("T")[0]

            conf_num = float(row["confidence"] or 1.0)
            confidence = "high" if conf_num >= 0.8 else ("medium" if conf_num >= 0.5 else "low")
            status = str(row["status"] or "active")
            evidence_class = str(row["evidence_class"] or "CANONICAL")
            superseded_by = str(row["superseded_by_claim_id"]) if row["superseded_by_claim_id"] else None

            metadata = {
                "subject_entity_id": str(row["subject_entity_id"]),
                "predicate": str(row["predicate"]),
                "canonical_effect": int(row["canonical_effect"] or 0),
                "approved_by": row["approved_by"],
                "reviewed_at": row["reviewed_at"],
                "durability": row["durability"] if "durability" in row.keys() else "durable",
                "valid_from": row["valid_from"] if "valid_from" in row.keys() else None,
                "valid_until": row["valid_until"] if "valid_until" in row.keys() else (row["valid_to"] if "valid_to" in row.keys() else None),
                "valid_to": row["valid_to"] if "valid_to" in row.keys() else None,
                "supersedes_claim_id": row["supersedes_claim_id"] if "supersedes_claim_id" in row.keys() else None,
                "evidence_references": evidence_list,
            }

            records.append(
                KnowledgeRecord(
                    record_id=cid,
                    category=category,
                    content=content,
                    source_kind=source_kind,
                    source_reference=source_reference,
                    timestamp=timestamp,
                    confidence=confidence,
                    status=status,
                    evidence_class=evidence_class,
                    superseded_by=superseded_by,
                    metadata=metadata,
                )
            )

    return records


def query_knowledge(
    query: KnowledgeQuery,
    store: LocalStore | None = None,
    records: Sequence[KnowledgeRecord] | None = None,
) -> list[KnowledgeRecord]:
    """Query knowledge records with deterministic filtering and sorting.

    If records are explicitly provided, queries those records.
    Else if store is provided, queries knowledge from the store.
    Else queries BOOTSTRAP_KNOWLEDGE_SEEDS.
    """
    if records is not None:
        source = records
    elif store is not None:
        source = load_knowledge_from_store(store)
    else:
        source = BOOTSTRAP_KNOWLEDGE_SEEDS

    matched = [r for r in source if query.matches(r)]
    sorted_records = sort_knowledge_records(matched)
    if query.max_records is not None:
        sorted_records = sorted_records[: query.max_records]
    return sorted_records


def query_knowledge_for_priming(
    manifest: PrimingManifest,
    store: LocalStore | None = None,
    records: Sequence[KnowledgeRecord] | None = None,
    include_superseded: bool = False,
    include_rejected: bool = False,
) -> list[KnowledgeRecord]:
    """Translate a PrimingManifest into a KnowledgeQuery, filter and sort deterministically."""
    query = KnowledgeQuery(
        categories=manifest.knowledge_categories,
        source_references=manifest.source_references,
        exclusions=manifest.exclusions,
        include_superseded=include_superseded,
        include_rejected=include_rejected,
    )
    return query_knowledge(query, store=store, records=records)


def assemble_priming_from_knowledge(
    manifest: PrimingManifest,
    store: LocalStore | None = None,
    records: Sequence[KnowledgeRecord] | None = None,
    include_superseded: bool = False,
    include_rejected: bool = False,
) -> PrimingBundle:
    """Retrieve matching knowledge records and assemble an immutable PrimingBundle."""
    selected_records = query_knowledge_for_priming(
        manifest=manifest,
        store=store,
        records=records,
        include_superseded=include_superseded,
        include_rejected=include_rejected,
    )
    return assemble_priming_bundle(manifest, selected_records)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Josie Canonical Knowledge Bootstrap Entrypoint")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without mutating the database")
    parser.add_argument("--live", "--execute", action="store_true", dest="live", help="Perform live bootstrap mutation")
    parser.add_argument("--db", type=str, default="data/josie.db", help="Path to SQLite database")
    parser.add_argument("--no-backup", action="store_true", help="Skip pre-mutation checkpoint backup")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    store = LocalStore(db_path)
    dry_run_mode = not args.live or args.dry_run

    result = bootstrap_canonical_knowledge(
        store,
        dry_run=dry_run_mode,
        backup=not args.no_backup,
    )
    print(json.dumps(result, indent=2))
    if result.get("has_conflicts"):
        sys.exit(2)
