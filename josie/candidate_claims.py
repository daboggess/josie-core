"""Memory Vault Phase 3B: Candidate Claims, Extraction Boundary & Adjudication Gate.

Epistemic Architecture:
    Historical Raw Evidence (history_messages)
    -> Bounded Candidate Claim Proposals (CandidateClaimProposal)
    -> Fail-Closed Validation & Staging (memory_claims status='candidate', canonical_effect=0)
    -> Human Adjudication Gate (Dustin explicit approval / rejection / supersession)
    -> ONLY THEN Canonical Knowledge (memory_claims status='active', canonical_effect=1)
    -> Deterministic Priming Assembly (PrimingManifest -> PrimingBundle)
    -> Worker Execution (Prompt Contract v1)

Core Epistemic Rules:
    - A model may PROPOSE a claim.
    - A model may NOT APPROVE a claim.
    - Historical evidence may SUPPORT or CONTRADICT a candidate.
    - Historical evidence may NOT become canonical merely because it exists.
    - Candidate claims, rejected claims, and needs_review claims have zero canonical priming authority.
    - Required separation:
        RAW EVIDENCE != CANDIDATE CLAIM != APPROVED / CANONICAL CLAIM != PRIMED WORKER CONTEXT

Persistence Architecture:
    Reuses existing SQLite schema:
    - memory_claims (status='candidate', canonical_effect=0, approved_by=NULL, reviewed_at=NULL)
    - claim_evidence (linking history_messages to claims with provenance and relation_type)
    - entities (subject_entity_id reference)
    - canonical_adjudications (audit log of human adjudications)
    - claim_conflicts / conflict_claims (conflict and supersession tracking)
    - candidate_extractions (durable extraction metadata, extractor ID, version, timestamp, raw proposal)
    - audit (event logging)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Protocol, Sequence
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from josie.storage import LocalStore


CANDIDATE_SCHEMA_VERSION = "1.0"
SUPPORTED_CANDIDATE_SCHEMA_VERSIONS = frozenset({"1.0"})

_ID = re.compile(r"[a-z0-9][a-z0-9:._-]{2,127}")
_PREDICATE = re.compile(r"[a-z][a-z0-9_]{1,63}")

ALLOWED_RELATION_TYPES = frozenset({
    "supports",
    "contradicts",
    "derived_from",
    "related_to",
    "supersedes",
    "refines",
})

ALLOWED_ATTRIBUTIONS = frozenset({
    "direct_user_assertion",
    "assistant_assertion",
    "quoted_or_pasted_content",
    "ambiguous_source",
})

ALLOWED_MEMORY_LAYERS = frozenset({
    "identity",
    "semantic",
    "episodic",
    "procedural",
    "relational",
})

ALLOWED_STATUSES = frozenset({
    "candidate",
    "active",
    "disputed",
    "superseded",
    "rejected",
})

# Minimum taxonomy categories per Phase 3B specification
ALLOWED_CLAIM_CATEGORIES = frozenset({
    "profile",
    "preference",
    "project_state",
    "decision",
    "procedure",
    "lesson",
    "relationship_context",
    "recurring_task",
    "constraint",
    "identity",
    "architecture",
    "hardware",
    "general",
})

# Allowed temporal durabilities per Phase 3B.3 specification
ALLOWED_DURABILITIES = frozenset({
    "durable",
    "current_state",
    "preference",
    "transient",
})


def infer_durability(
    subject_entity_id: str = "",
    predicate: str = "",
    value_text: str = "",
    claim_category: str = "general",
) -> str:
    """Infer candidate claim durability based on semantic predicate, category, and content.

    Returns one of:
      - 'durable': Permanent/long-lived identity, credentials, background.
      - 'current_state': Point-in-time state (hardware inventory, lack of hardware, current config).
      - 'preference': Evolving goals, preferences, hardware strategies, budgets.
      - 'transient': Ephemeral session state, temporary availability.
    """
    pred = (predicate or "").lower().strip()
    cat = (claim_category or "").lower().strip()
    val = (value_text or "").lower().strip()

    # 1. Check transient markers first
    if any(k in pred for k in ("transient", "temporary", "temp_", "session", "short_lived", "availability")):
        return "transient"
    if cat in ("transient", "context"):
        return "transient"

    # 2. Check durable profile/identity markers (certifications, experience, identity)
    if any(k in pred for k in ("certif", "qualification", "credential", "experience", "degree", "license")):
        return "durable"
    if cat == "profile" or pred in ("has_background", "identity"):
        return "durable"

    # 3. Check preferences and evolving goals/strategies
    if any(k in pred for k in ("seek", "prefer", "goal", "strategy", "want", "desire", "budget", "target")):
        return "preference"
    if cat == "preference":
        return "preference"

    # 4. Check current-state markers (hardware ownership, lack of hardware, inventory)
    if any(k in pred for k in ("own", "lack", "inventory", "hardware", "device", "part", "config", "setup", "using", "work_on", "works_on", "run_on", "runs_on")):
        return "current_state"
    if cat == "hardware":
        return "current_state"

    # Default to current_state if stateful, otherwise durable for architectural rules
    if cat in ("architecture", "procedure", "constraint"):
        return "durable"
    return "current_state"


# Deterministic mapping from claim category to underlying SQLite memory layer
CATEGORY_TO_MEMORY_LAYER = {
    "profile": "identity",
    "identity": "identity",
    "preference": "relational",
    "relationship_context": "relational",
    "decision": "semantic",
    "project_state": "semantic",
    "hardware": "semantic",
    "general": "semantic",
    "procedure": "procedural",
    "recurring_task": "procedural",
    "constraint": "procedural",
    "architecture": "procedural",
    "lesson": "episodic",
}

# Lifecycle terminology mapping: recommended terms <-> SQLite stored terms
STATUS_ALIAS_MAP = {
    "pending": "candidate",
    "candidate": "candidate",
    "approved": "active",
    "active": "active",
    "rejected": "rejected",
    "superseded": "superseded",
    "needs_review": "disputed",
    "disputed": "disputed",
}

ALLOWED_EVIDENCE_CLASSES = frozenset({
    "VERIFIED",
    "CANONICAL",
    "RETRIEVED",
    "INFERRED",
    "UNKNOWN",
})

DISALLOWED_REVIEWERS = frozenset({
    "model",
    "worker",
    "extractor",
    "assistant",
    "system",
    "llm",
    "ai",
    "ollama",
    "local_model",
    "automated",
    "agent",
    "opencode",
    "goose",
    "subagent",
})

ALLOWED_HUMAN_REVIEWERS = frozenset({
    "dustin",
    "dustin boggess",
})

APPROVAL_CONFIRMATION = "EXPLICIT HUMAN APPROVAL"

# Safe Bounded Processing limits
DEFAULT_MAX_BUNDLE_MESSAGES = 50
DEFAULT_MAX_BUNDLE_CHARS = 100000
DEFAULT_MAX_MESSAGE_CHARS = 10000


@dataclass(frozen=True)
class BoundedEvidenceBundle:
    """Validated, bounded bundle of historical evidence messages."""

    messages: tuple[dict[str, Any], ...]
    total_chars: int
    message_count: int
    window_message_ids: frozenset[int]


def validate_evidence_bundle(
    messages: Sequence[dict[str, Any]],
    *,
    max_messages: int = DEFAULT_MAX_BUNDLE_MESSAGES,
    max_chars: int = DEFAULT_MAX_BUNDLE_CHARS,
    max_message_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
) -> BoundedEvidenceBundle:
    """Validate that an evidence bundle obeys strict boundedness constraints.
    
    Fails closed if message count, total characters, or single-message characters
    exceed safe bounds.
    """
    if not messages:
        return BoundedEvidenceBundle(messages=(), total_chars=0, message_count=0, window_message_ids=frozenset())

    if len(messages) > max_messages:
        raise ValueError(
            f"Evidence bundle message count ({len(messages)}) exceeds allowed limit of {max_messages}. "
            "Use split_evidence_bundle for bounded batch processing."
        )

    total_chars = 0
    clean_messages: list[dict[str, Any]] = []
    window_ids: set[int] = set()

    for idx, m in enumerate(messages):
        text = str(m.get("raw_text") or "")
        if len(text) > max_message_chars:
            raise ValueError(
                f"Message at index {idx} (message_id={m.get('message_id')}) length ({len(text)} chars) "
                f"exceeds maximum allowed per-message limit ({max_message_chars} chars)."
            )
        total_chars += len(text)
        mid = m.get("message_id")
        if mid is not None:
            try:
                window_ids.add(int(mid))
            except (ValueError, TypeError):
                pass
        clean_messages.append(dict(m))

    if total_chars > max_chars:
        raise ValueError(
            f"Evidence bundle total character count ({total_chars}) exceeds allowed limit of {max_chars}. "
            "Use split_evidence_bundle for bounded batch processing."
        )

    return BoundedEvidenceBundle(
        messages=tuple(clean_messages),
        total_chars=total_chars,
        message_count=len(clean_messages),
        window_message_ids=frozenset(window_ids),
    )


def split_evidence_bundle(
    messages: Sequence[dict[str, Any]],
    *,
    max_messages: int = DEFAULT_MAX_BUNDLE_MESSAGES,
    max_chars: int = DEFAULT_MAX_BUNDLE_CHARS,
) -> list[list[dict[str, Any]]]:
    """Deterministically split an evidence bundle into bounded batches that obey safe limits."""
    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    current_chars = 0

    for m in messages:
        text = str(m.get("raw_text") or "")
        m_len = len(text)
        if current_batch and (len(current_batch) >= max_messages or current_chars + m_len > max_chars):
            batches.append(current_batch)
            current_batch = [dict(m)]
            current_chars = m_len
        else:
            current_batch.append(dict(m))
            current_chars += m_len

    if current_batch:
        batches.append(current_batch)
    return batches


def normalize_claim_value(value: str) -> str:
    """Normalize proposition value for stable candidate deduplication.
    
    Applies Unicode NFKC, lowercasing, and whitespace collapsing.
    """
    normalized = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    return " ".join(re.findall(r"\S+", normalized))


def compute_candidate_claim_id(
    subject_entity_id: str,
    predicate: str,
    value_text: str,
) -> str:
    """Derive deterministic stable candidate claim ID from semantic proposition.
    
    Format: claim:candidate:{clean_subject}:{clean_predicate}:{normalized_value_hash}
    Guarantees:
    - Same proposition across N messages -> exactly 1 candidate claim ID.
    - Different propositions on same subject/predicate -> distinct candidate claim IDs.
    """
    clean_subj = subject_entity_id.strip().lower()
    clean_pred = predicate.strip().lower()
    norm_val = normalize_claim_value(value_text)
    val_digest = hashlib.sha256(norm_val.encode("utf-8")).hexdigest()[:16]
    candidate_id = f"claim:candidate:{clean_subj}:{clean_pred}:{val_digest}"
    if len(candidate_id) > 128:
        subj_digest = hashlib.sha256(clean_subj.encode("utf-8")).hexdigest()[:12]
        candidate_id = f"claim:cand:{subj_digest}:{clean_pred[:24]}:{val_digest}"
    return candidate_id


@dataclass(frozen=True)
class EvidenceReference:
    """Provenance reference linking a claim to historical evidence."""

    history_message_id: int | None = None
    relation_type: str = "supports"
    excerpt: str = ""
    role: str = ""
    speaker: str = ""
    attribution: str = "ambiguous_source"
    span_start: int | None = None
    span_end: int | None = None
    source_timestamp: str = ""
    source_pointer: str = ""
    evidence_class: str = "RETRIEVED"

    def __post_init__(self) -> None:
        if self.relation_type not in ALLOWED_RELATION_TYPES:
            raise ValueError(
                f"relation_type must be one of {sorted(ALLOWED_RELATION_TYPES)}, got {self.relation_type!r}"
            )
        if self.evidence_class not in ALLOWED_EVIDENCE_CLASSES:
            raise ValueError(
                f"evidence_class must be one of {sorted(ALLOWED_EVIDENCE_CLASSES)}, got {self.evidence_class!r}"
            )
        if self.attribution not in ALLOWED_ATTRIBUTIONS:
            raise ValueError(
                f"attribution must be one of {sorted(ALLOWED_ATTRIBUTIONS)}, got {self.attribution!r}"
            )
        if self.history_message_id is None and not self.source_pointer.strip():
            raise ValueError("EvidenceReference requires history_message_id or source_pointer")
        if self.span_start is not None or self.span_end is not None:
            if self.span_start is None or self.span_end is None:
                raise ValueError("Both span_start and span_end must be specified when offsets are used")
            if not isinstance(self.span_start, int) or not isinstance(self.span_end, int):
                raise ValueError("span_start and span_end must be integers")
            if self.span_start < 0:
                raise ValueError(f"span_start ({self.span_start}) cannot be negative")
            if self.span_end < self.span_start:
                raise ValueError(f"span_end ({self.span_end}) cannot be less than span_start ({self.span_start})")

    def to_dict(self) -> dict[str, Any]:
        return {
            "history_message_id": self.history_message_id,
            "relation_type": self.relation_type,
            "excerpt": self.excerpt,
            "role": self.role,
            "speaker": self.speaker,
            "attribution": self.attribution,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "source_timestamp": self.source_timestamp,
            "source_pointer": self.source_pointer,
            "evidence_class": self.evidence_class,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceReference:
        hid = data.get("history_message_id")
        raw_attr = str(data.get("attribution") or "").strip().lower()
        if raw_attr not in ALLOWED_ATTRIBUTIONS:
            raw_attr = "ambiguous_source"
        raw_start = data.get("span_start")
        raw_end = data.get("span_end")
        start_val: int | None = None
        end_val: int | None = None
        if raw_start is not None:
            try:
                start_val = int(raw_start)
            except (ValueError, TypeError):
                start_val = -1
        if raw_end is not None:
            try:
                end_val = int(raw_end)
            except (ValueError, TypeError):
                end_val = -1
        return cls(
            history_message_id=int(hid) if hid is not None else None,
            relation_type=str(data.get("relation_type") or "supports").strip().lower(),
            excerpt=str(data.get("excerpt") or "").strip()[:500],
            role=str(data.get("role") or "").strip().lower(),
            speaker=str(data.get("speaker") or "").strip(),
            attribution=raw_attr,
            span_start=start_val,
            span_end=end_val,
            source_timestamp=str(data.get("source_timestamp") or "").strip(),
            source_pointer=str(data.get("source_pointer") or "").strip(),
            evidence_class=str(data.get("evidence_class") or "RETRIEVED").strip().upper(),
        )


@dataclass(frozen=True)
class CandidateClaimProposal:
    """Strict structured proposal output from a claim extractor before validation and staging."""

    subject_entity_id: str
    predicate: str
    value_text: str
    memory_layer: str = "semantic"
    claim_category: str = "general"
    confidence: float = 0.8
    confidence_basis: str = ""
    extractor_id: str = ""
    evidence_references: tuple[EvidenceReference, ...] = ()
    durability: str = "current_state"
    valid_from: str | None = None
    valid_until: str | None = None
    valid_to: str | None = None
    supersedes_claim_id: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.subject_entity_id, str) or not self.subject_entity_id.strip():
            raise ValueError("CandidateClaimProposal.subject_entity_id must be a non-empty string")
        if not isinstance(self.predicate, str) or not self.predicate.strip():
            raise ValueError("CandidateClaimProposal.predicate must be a non-empty string")
        if not isinstance(self.value_text, str) or not self.value_text.strip():
            raise ValueError("CandidateClaimProposal.value_text must be a non-empty string")
        clean_cat = self.claim_category.strip().lower()
        if clean_cat not in ALLOWED_CLAIM_CATEGORIES:
            raise ValueError(
                f"CandidateClaimProposal.claim_category must be one of {sorted(ALLOWED_CLAIM_CATEGORIES)}, got {self.claim_category!r}"
            )
        if self.memory_layer not in ALLOWED_MEMORY_LAYERS:
            layer = CATEGORY_TO_MEMORY_LAYER.get(clean_cat, "semantic")
            object.__setattr__(self, "memory_layer", layer)
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(f"CandidateClaimProposal.confidence must be between 0.0 and 1.0, got {self.confidence!r}")

        clean_dur = str(self.durability or "").strip().lower()
        if clean_dur not in ALLOWED_DURABILITIES:
            raise ValueError(
                f"CandidateClaimProposal.durability must be one of {sorted(ALLOWED_DURABILITIES)}, got {self.durability!r}"
            )
        object.__setattr__(self, "durability", clean_dur)

        v_until = self.valid_until
        v_to = self.valid_to
        if v_until is not None and v_to is None:
            object.__setattr__(self, "valid_to", v_until)
        elif v_to is not None and v_until is None:
            object.__setattr__(self, "valid_until", v_to)

        if self.valid_from is None and self.evidence_references:
            for ref in self.evidence_references:
                if ref.source_timestamp:
                    object.__setattr__(self, "valid_from", ref.source_timestamp)
                    break

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_entity_id": self.subject_entity_id,
            "predicate": self.predicate,
            "value_text": self.value_text,
            "memory_layer": self.memory_layer,
            "claim_category": self.claim_category,
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "extractor_id": self.extractor_id,
            "evidence_references": [ref.to_dict() for ref in self.evidence_references],
            "durability": self.durability,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "valid_to": self.valid_to,
            "supersedes_claim_id": self.supersedes_claim_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateClaimProposal:
        raw_refs = data.get("evidence_references") or []
        refs = tuple(EvidenceReference.from_dict(r) for r in raw_refs if isinstance(r, dict))
        conf_raw = data.get("confidence", 0.8)
        try:
            conf_val = float(conf_raw)
            if conf_val > 1.0 and conf_val <= 100.0:
                conf_val = round(conf_val / 100.0, 3)
            conf_val = max(0.0, min(1.0, conf_val))
        except (ValueError, TypeError):
            conf_val = 0.5

        raw_cat = str(data.get("claim_category") or "general").strip().lower()
        if raw_cat not in ALLOWED_CLAIM_CATEGORIES:
            raw_cat = "general"

        raw_layer = str(data.get("memory_layer") or CATEGORY_TO_MEMORY_LAYER.get(raw_cat, "semantic")).strip().lower()
        if raw_layer not in ALLOWED_MEMORY_LAYERS:
            raw_layer = "semantic"

        raw_dur = data.get("durability")
        if raw_dur is not None:
            clean_dur = str(raw_dur).strip().lower()
            if clean_dur not in ALLOWED_DURABILITIES:
                raise ValueError(
                    f"CandidateClaimProposal.durability must be one of {sorted(ALLOWED_DURABILITIES)}, got {raw_dur!r}"
                )
        else:
            clean_dur = infer_durability(
                subject_entity_id=str(data.get("subject_entity_id") or ""),
                predicate=str(data.get("predicate") or ""),
                value_text=str(data.get("value_text") or ""),
                claim_category=raw_cat,
            )

        v_from = str(data.get("valid_from")).strip() if data.get("valid_from") else None
        if not v_from and refs:
            for r in refs:
                if r.source_timestamp:
                    v_from = r.source_timestamp
                    break

        v_until = str(data.get("valid_until")).strip() if data.get("valid_until") else None
        v_to = str(data.get("valid_to")).strip() if data.get("valid_to") else None
        if v_until and not v_to:
            v_to = v_until
        elif v_to and not v_until:
            v_until = v_to

        return cls(
            subject_entity_id=str(data.get("subject_entity_id") or "").strip(),
            predicate=str(data.get("predicate") or "").strip(),
            value_text=str(data.get("value_text") or "").strip(),
            memory_layer=raw_layer,
            claim_category=raw_cat,
            confidence=conf_val,
            confidence_basis=str(data.get("confidence_basis") or "").strip(),
            extractor_id=str(data.get("extractor_id") or "").strip(),
            evidence_references=refs,
            durability=clean_dur,
            valid_from=v_from,
            valid_until=v_until,
            valid_to=v_to,
            supersedes_claim_id=str(data.get("supersedes_claim_id")).strip() if data.get("supersedes_claim_id") else None,
            notes=str(data.get("notes") or "").strip(),
        )


@dataclass(frozen=True)
class CandidateClaimRecord:
    """Representation of a persisted or staged candidate claim."""

    claim_id: str
    subject_entity_id: str
    predicate: str
    value_text: str
    memory_layer: str
    status: str = "candidate"
    evidence_class: str = "RETRIEVED"
    authority_scope: str = ""
    confidence: float = 0.8
    confidence_basis: str = ""
    durability: str = "durable"
    valid_from: str | None = None
    valid_until: str | None = None
    valid_to: str | None = None
    created_at: str = ""
    updated_at: str = ""
    approved_by: str | None = None
    reviewed_at: str | None = None
    canonical_effect: int = 0
    superseded_by_claim_id: str | None = None
    supersedes_claim_id: str | None = None
    version: int = 1
    evidence_references: tuple[EvidenceReference, ...] = ()
    extractor_id: str = ""
    claim_category: str = "general"
    notes: str = ""

    def __post_init__(self) -> None:
        v_until = self.valid_until
        v_to = self.valid_to
        if v_until is not None and v_to is None:
            object.__setattr__(self, "valid_to", v_until)
        elif v_to is not None and v_until is None:
            object.__setattr__(self, "valid_until", v_to)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "subject_entity_id": self.subject_entity_id,
            "predicate": self.predicate,
            "value_text": self.value_text,
            "memory_layer": self.memory_layer,
            "status": self.status,
            "evidence_class": self.evidence_class,
            "authority_scope": self.authority_scope,
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "durability": self.durability,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "valid_to": self.valid_to,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approved_by": self.approved_by,
            "reviewed_at": self.reviewed_at,
            "canonical_effect": self.canonical_effect,
            "superseded_by_claim_id": self.superseded_by_claim_id,
            "supersedes_claim_id": self.supersedes_claim_id,
            "version": self.version,
            "evidence_references": [ref.to_dict() for ref in self.evidence_references],
            "extractor_id": self.extractor_id,
            "claim_category": self.claim_category,
            "notes": self.notes,
        }


def get_pasted_regions(raw_text: str) -> list[tuple[int, int]]:
    """Return a list of [start, end) character spans within raw_text that are pasted/external content."""
    if not raw_text:
        return []

    regions: list[tuple[int, int]] = []

    # 1. Blockquotes (lines starting with '>')
    offset = 0
    for line in raw_text.splitlines(keepends=True):
        line_len = len(line)
        if line.strip().startswith(">"):
            regions.append((offset, offset + line_len))
        offset += line_len

    # 2. Fenced code or quote blocks (```...```)
    for m in re.finditer(r"```[\s\S]*?```", raw_text):
        regions.append((m.start(), m.end()))

    # 3. AI Persona / Greeting openings (e.g. "Alright Soph, here’s the real truth...")
    ai_openings = (
        r"(?im)\b(?:alright\s+soph|sophie\s*\(me\b|sophie's\s+official\s+pick|"
        r"i\s+will\s+generate\s+for\s+you|pick,\s+and\s+i['’]ll\s+build|"
        r"where\s+gemini\s+is\s+right|where\s+gemini\s+is\s+wrong|"
        r"here['’]s\s+the\s+real\s+truth|here\s+is\s+the\s+real\s+truth)\b"
    )
    m_open = re.search(ai_openings, raw_text)
    if m_open:
        user_after = re.search(r"(?im)^\s*(?:user|dustin|me|my\s+take)\s*:", raw_text[m_open.end():])
        end_idx = m_open.end() + user_after.start() if user_after else len(raw_text)
        regions.append((m_open.start(), end_idx))

    # 4. Section headers like ChatGPT:, Claude:, Gemini:, Assistant:
    header_re = re.compile(r"(?im)^\s*(?:chatgpt|claude|gemini|assistant)\s*:", re.MULTILINE)
    for hm in header_re.finditer(raw_text):
        user_after = re.search(r"(?im)^\s*(?:user|dustin|me|my\s+take)\s*:", raw_text[hm.end():])
        end_idx = hm.end() + user_after.start() if user_after else len(raw_text)
        regions.append((hm.start(), end_idx))

    # 5. Marker headers like "Gpt response", "ChatGPT response", "from gpt"
    marker_re = re.compile(r"(?im)^\s*(?:gpt\s+response|chatgpt\s+response|chapgpt\s+response|from\s+gpt)\b", re.MULTILINE)
    for mm in marker_re.finditer(raw_text):
        if m_open and mm.start() < m_open.start():
            # If an AI opening follows, the marker line itself is a header (non-user)
            regions.append((mm.start(), mm.end()))
        else:
            user_after = re.search(r"(?im)^\s*(?:user|dustin|me|my\s+take|btw)\s*:", raw_text[mm.end():])
            end_idx = mm.end() + user_after.start() if user_after else len(raw_text)
            regions.append((mm.start(), end_idx))

    if not regions:
        return []

    regions.sort(key=lambda r: (r[0], r[1]))
    merged: list[tuple[int, int]] = [regions[0]]
    for cur_start, cur_end in regions[1:]:
        prev_start, prev_end = merged[-1]
        if cur_start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, cur_end))
        else:
            merged.append((cur_start, cur_end))

    return merged


def classify_evidence_span(
    *,
    raw_text: str = "",
    excerpt: str = "",
    role: str = "",
    speaker: str = "",
    span_start: int | None = None,
    span_end: int | None = None,
    proposed_attribution: str | None = None,
) -> tuple[str, int | None, int | None]:
    """Classify provenance attribution of a specific supporting evidence span within a historical message.

    Returns:
      (attribution, resolved_span_start, resolved_span_end)

    Attribution is one of:
      - 'direct_user_assertion': statement spoken directly by Dustin within user span.
      - 'assistant_assertion': assertion by conversational assistant (Gemini, Claude, etc.).
      - 'quoted_or_pasted_content': third-party AI or external content pasted/quoted inside a turn.
      - 'ambiguous_source': unclear speaker or unattributed context.

    Guarantees:
      - Assistant envelopes NEVER receive 'direct_user_assertion'.
      - Pasted AI text inside a user envelope is demoted to 'quoted_or_pasted_content'.
      - Direct user text outside pasted regions in a mixed message retains 'direct_user_assertion'.
      - Ambiguous boundaries default conservatively to 'ambiguous_source'.
      - Malformed or out-of-bounds offsets fail closed.
    """
    text = (raw_text or "").strip()
    r = (role or "").lower().strip()
    spk = (speaker or "").lower().strip()
    ex = (excerpt or "").strip()

    # Offset validation if specified
    if span_start is not None or span_end is not None:
        if span_start is None or span_end is None:
            raise ValueError("Both span_start and span_end must be specified when offsets are used")
        if not isinstance(span_start, int) or not isinstance(span_end, int):
            raise ValueError("span_start and span_end must be integers")
        if span_start < 0:
            raise ValueError(f"span_start ({span_start}) cannot be negative")
        if span_end < span_start:
            raise ValueError(f"span_end ({span_end}) cannot be less than span_start ({span_start})")
        if raw_text and span_end > len(raw_text):
            raise ValueError(f"span_end ({span_end}) exceeds raw_text length ({len(raw_text)})")

    # If offsets not provided, attempt to locate excerpt in raw_text
    if span_start is None and span_end is None and ex and raw_text:
        idx = raw_text.find(ex)
        if idx == -1:
            idx_cf = raw_text.casefold().find(ex.casefold())
            if idx_cf != -1:
                idx = idx_cf
                ex = raw_text[idx : idx + len(ex)]
        if idx != -1:
            span_start = idx
            span_end = idx + len(ex)

    span_text = (
        raw_text[span_start:span_end].strip()
        if (span_start is not None and span_end is not None and raw_text)
        else ex
    )

    # Rule 1: Assistant / Model turns cannot be direct user assertions.
    if r in ("assistant", "model") or spk in (
        "gemini apps", "gemini", "assistant", "model", "bernie", "sophie", "chatgpt"
    ):
        if proposed_attribution in ("assistant_assertion", "quoted_or_pasted_content"):
            return proposed_attribution, span_start, span_end
        return "assistant_assertion", span_start, span_end

    # Rule 2: User turns (Dustin / google_account_owner)
    if r == "user" or spk in ("dustin", "user", "google_account_owner"):
        lower_span = span_text.lower()

        # Indicators of quoted / pasted AI responses
        ai_indicators = (
            "gpt response", "chatgpt response", "chapgpt response",
            "chatgpt:", "gpt:", "claude:", "gemini:",
            "working on woth chatgpt", "working on with chatgpt",
            "alright soph", "sophie (me", "sophie's official pick",
            "where gemini is right", "where gemini is wrong",
            "here's my take on gemini", "here’s my take on gemini",
            "i will generate for you", "i’m going to show you", "i'm going to show you",
            "pick, and i’ll build", "pick, and i'll build",
            "forwarded message",
        )

        # If the span itself starts with blockquote '>'
        if any(line.strip().startswith(">") for line in span_text.splitlines() if line.strip()):
            return "quoted_or_pasted_content", span_start, span_end

        # If the span itself contains an AI indicator
        if any(ind in lower_span for ind in ai_indicators):
            return "quoted_or_pasted_content", span_start, span_end

        # Check if the overall message has indicators of mixed / pasted AI content
        pasted_regions = get_pasted_regions(raw_text)

        if not pasted_regions:
            # Pure user message
            if proposed_attribution in ("quoted_or_pasted_content", "ambiguous_source"):
                return proposed_attribution, span_start, span_end
            return "direct_user_assertion", span_start, span_end

        # Message has mixed content! Check if this span is inside any pasted region
        is_pasted = False
        if span_start is not None and span_end is not None:
            for p_start, p_end in pasted_regions:
                if max(span_start, p_start) < min(span_end, p_end):
                    is_pasted = True
                    break
        else:
            for p_start, p_end in pasted_regions:
                if ex and ex in raw_text[p_start:p_end]:
                    is_pasted = True
                    break

        if is_pasted:
            return "quoted_or_pasted_content", span_start, span_end

        # Outside all pasted regions: check for direct user voice
        user_voice_indicators = (
            "i am", "i'm", "i have", "i don't", "i dont", "my", "me", "btw", "i love",
            "i prefer", "we need", "i think", "i believe", "certified", "years of experience",
            "i run", "i want", "i use", "i need", "i tested", "i verified",
        )
        if any(ind in lower_span for ind in user_voice_indicators):
            if proposed_attribution in ("quoted_or_pasted_content", "ambiguous_source"):
                return proposed_attribution, span_start, span_end
            return "direct_user_assertion", span_start, span_end

        if proposed_attribution == "direct_user_assertion":
            return "direct_user_assertion", span_start, span_end

        if proposed_attribution in ALLOWED_ATTRIBUTIONS:
            return proposed_attribution, span_start, span_end

        return "ambiguous_source", span_start, span_end

    # Rule 3: Other envelopes
    if proposed_attribution in ALLOWED_ATTRIBUTIONS and proposed_attribution != "direct_user_assertion":
        return proposed_attribution, span_start, span_end

    return "ambiguous_source", span_start, span_end


def classify_evidence_attribution(
    *,
    role: str = "",
    speaker: str = "",
    raw_text: str = "",
    excerpt: str = "",
    span_start: int | None = None,
    span_end: int | None = None,
    proposed_attribution: str | None = None,
) -> str:
    """Classify provenance attribution of historical evidence or evidence span."""
    attr, _, _ = classify_evidence_span(
        raw_text=raw_text,
        excerpt=excerpt,
        role=role,
        speaker=speaker,
        span_start=span_start,
        span_end=span_end,
        proposed_attribution=proposed_attribution,
    )
    return attr


def validate_proposal(
    proposal: CandidateClaimProposal | dict[str, Any],
    *,
    window_message_ids: set[int] | frozenset[int] | None = None,
    messages_lookup: dict[int, dict[str, Any]] | None = None,
    store: LocalStore | None = None,
) -> tuple[bool, str]:
    """Fail-closed validation layer between model/extractor output and candidate persistence.
    
    Checks:
    - Non-empty subject, predicate, and value.
    - Valid subject entity format and predicate regex.
    - Valid memory layer and taxonomy category.
    - Valid confidence range [0.0, 1.0].
    - Non-empty evidence references.
    - All referenced history_message_ids exist in provided window.
    - Model/extractor cannot set canonical_effect=1 or claim self-approval.
    - Offsets if provided must be non-negative, start <= end, and within message bounds.
    - Supporting excerpt must actually exist in the referenced message text.
    - Model proposed attribution cannot elevate authority beyond deterministic validation.
    """
    if isinstance(proposal, dict):
        raw_status = str(proposal.get("status", "candidate")).lower()
        if raw_status in {"active", "approved", "canonical"}:
            return False, "Model proposal attempted to set active/approved/canonical status"
        if proposal.get("canonical_effect") and int(proposal.get("canonical_effect")) != 0:
            return False, "Model proposal attempted to set canonical_effect=1"
        if proposal.get("approved_by") or proposal.get("reviewed_at"):
            return False, "Model proposal attempted to assign reviewer/approver"
        if "claim_category" in proposal:
            raw_cat = str(proposal.get("claim_category") or "").strip().lower()
            if raw_cat not in ALLOWED_CLAIM_CATEGORIES:
                return False, f"Unsupported claim_category: {proposal.get('claim_category')!r}"
        try:
            prop = CandidateClaimProposal.from_dict(proposal)
        except Exception as exc:
            return False, f"Malformed proposal structure: {exc}"
    elif isinstance(proposal, CandidateClaimProposal):
        prop = proposal
    else:
        return False, f"Expected CandidateClaimProposal or dict, got {type(proposal).__name__}"

    subj = prop.subject_entity_id.strip()
    if not subj or _ID.fullmatch(subj) is None:
        return False, f"Invalid subject_entity_id: {subj!r}"

    pred = prop.predicate.strip().lower()
    if not pred or _PREDICATE.fullmatch(pred) is None:
        return False, f"Invalid predicate: {pred!r}"

    val = prop.value_text.strip()
    if not val:
        return False, "Proposed value_text cannot be empty"
    if len(val) > 1500:
        return False, f"Proposed value_text exceeds 1500 character limit ({len(val)} chars)"

    if prop.memory_layer not in ALLOWED_MEMORY_LAYERS:
        return False, f"Unsupported memory_layer: {prop.memory_layer!r}"

    clean_cat = prop.claim_category.strip().lower()
    if clean_cat not in ALLOWED_CLAIM_CATEGORIES:
        return False, f"Unsupported claim_category: {prop.claim_category!r}"

    if prop.durability not in ALLOWED_DURABILITIES:
        return False, f"Unsupported durability: {prop.durability!r}; must be one of {sorted(ALLOWED_DURABILITIES)}"

    if not prop.evidence_references:
        return False, "Candidate claim proposal must include at least one evidence reference"

    # Prepare lookup if store provided
    lookup = dict(messages_lookup or {})
    if store is not None and not lookup:
        needed_mids = [r.history_message_id for r in prop.evidence_references if r.history_message_id is not None]
        if needed_mids:
            with store._connect() as conn:
                placeholders = ",".join("?" for _ in needed_mids)
                rows = conn.execute(
                    f"SELECT message_id, role, speaker, timestamp, raw_text FROM history_messages WHERE message_id IN ({placeholders})",
                    tuple(needed_mids),
                ).fetchall()
                for row in rows:
                    lookup[row["message_id"]] = dict(row)

    for ref in prop.evidence_references:
        if ref.relation_type not in ALLOWED_RELATION_TYPES:
            return False, f"Unsupported relation_type: {ref.relation_type!r}"
        if window_message_ids is not None:
            if ref.history_message_id is None:
                return False, "Evidence reference missing history_message_id for windowed extraction"
            if ref.history_message_id not in window_message_ids:
                return (
                    False,
                    f"Evidence references history_message_id {ref.history_message_id} outside extraction window",
                )

        # Validate offsets internal validity
        if ref.span_start is not None or ref.span_end is not None:
            if ref.span_start is None or ref.span_end is None:
                return False, "Malformed span offsets: both span_start and span_end must be provided"
            if not isinstance(ref.span_start, int) or not isinstance(ref.span_end, int):
                return False, "Malformed span offsets: span_start and span_end must be integers"
            if ref.span_start < 0:
                return False, f"Malformed span offsets: span_start ({ref.span_start}) cannot be negative"
            if ref.span_end < ref.span_start:
                return False, f"Malformed span offsets: span_end ({ref.span_end}) cannot be less than span_start ({ref.span_start})"

        # If message data is available, validate against message raw_text
        if ref.history_message_id is not None and ref.history_message_id in lookup:
            m_info = lookup[ref.history_message_id]
            m_text = str(m_info.get("raw_text") or "")

            if ref.span_start is not None and ref.span_end is not None:
                if ref.span_end > len(m_text):
                    return (
                        False,
                        f"Span offsets [{ref.span_start}:{ref.span_end}] out of bounds for message {ref.history_message_id} (length {len(m_text)})",
                    )
                if ref.excerpt and ref.excerpt.strip():
                    span_slice = m_text[ref.span_start:ref.span_end]
                    clean_ex = ref.excerpt.strip()
                    if clean_ex not in span_slice and span_slice.strip() not in clean_ex:
                        return (
                            False,
                            f"Span text [{ref.span_start}:{ref.span_end}] does not match excerpt {ref.excerpt!r}",
                        )

            if ref.excerpt and ref.excerpt.strip():
                if ref.excerpt.strip() not in m_text:
                    if ref.excerpt.strip().casefold() not in m_text.casefold():
                        return (
                            False,
                            f"Supporting excerpt does not exist in historical message {ref.history_message_id}: {ref.excerpt!r}",
                        )

            # Check proposed attribution cannot elevate authority beyond deterministic validation
            val_attr, _, _ = classify_evidence_span(
                raw_text=m_text,
                excerpt=ref.excerpt,
                role=str(m_info.get("role") or ""),
                speaker=str(m_info.get("speaker") or ""),
                span_start=ref.span_start,
                span_end=ref.span_end,
                proposed_attribution=ref.attribution,
            )
            if ref.attribution == "direct_user_assertion" and val_attr != "direct_user_assertion":
                return (
                    False,
                    f"Proposed attribution 'direct_user_assertion' not permitted by deterministic validation (classified as '{val_attr}')",
                )

    return True, ""


def evaluate_evidence_weight(
    refs: Sequence[EvidenceReference],
    base_confidence: float = 0.8,
) -> tuple[float, str, str]:
    """Calculate attribution-weighted confidence and evidentiary basis.

    A direct user assertion carries primary authority (>= 0.85, RETRIEVED).
    Quoted/pasted content and assistant assertions carry secondary authority (capped at <= 0.60, INFERRED).
    Ambiguous sources carry lower confidence (capped at <= 0.50, INFERRED).
    Envelope role == 'user' alone is NOT sufficient for direct user authority.
    """
    has_direct_user = any(ref.attribution == "direct_user_assertion" for ref in refs)
    has_quoted_or_pasted = any(ref.attribution == "quoted_or_pasted_content" for ref in refs)
    has_assistant = any(ref.attribution == "assistant_assertion" for ref in refs)

    if has_direct_user:
        conf = min(1.0, max(base_confidence, 0.85))
        basis = "Direct user statement in historical conversation (primary evidence)"
        e_class = "RETRIEVED"
    elif has_quoted_or_pasted:
        conf = min(0.60, base_confidence)
        basis = "Quoted or pasted external content in historical conversation (secondary evidence; unconfirmed by user)"
        e_class = "INFERRED"
    elif has_assistant:
        conf = min(0.60, base_confidence)
        basis = "Assistant assertion in historical conversation (secondary evidence; unconfirmed by user)"
        e_class = "INFERRED"
    else:
        conf = min(0.50, base_confidence)
        basis = "Historical conversation context (ambiguous source)"
        e_class = "INFERRED"

    return round(conf, 3), basis, e_class


class CandidateClaimExtractor(Protocol):
    """Provider-neutral interface for candidate claim extraction."""

    def extract_claims(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        provenance: dict[str, Any] | None = None,
    ) -> list[CandidateClaimProposal]:
        """Extract candidate claim proposals from historical message records."""
        ...


class StubClaimExtractor:
    """Deterministic stub extractor for testing without model calls."""

    def __init__(
        self,
        proposals: Sequence[CandidateClaimProposal] | None = None,
        rule_based: bool = False,
    ) -> None:
        self._proposals = list(proposals or [])
        self.rule_based = rule_based

    def extract_claims(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        provenance: dict[str, Any] | None = None,
    ) -> list[CandidateClaimProposal]:
        if not self.rule_based:
            return list(self._proposals)

        extracted: list[CandidateClaimProposal] = []
        for msg in messages:
            mid = int(msg.get("message_id", 0))
            text = str(msg.get("raw_text") or "")
            role = str(msg.get("role") or "").lower()
            speaker = str(msg.get("speaker") or "")
            ts = str(msg.get("timestamp") or "")

            if "rtx 3060" in text.lower():
                extracted.append(
                    CandidateClaimProposal(
                        subject_entity_id="system:josie",
                        predicate="hardware_gpu",
                        value_text="Josie host system is equipped with an NVIDIA RTX 3060 GPU.",
                        memory_layer="semantic",
                        claim_category="hardware",
                        confidence=0.9 if role == "user" else 0.6,
                        confidence_basis="Rule extractor matched RTX 3060 mention",
                        extractor_id="stub_extractor:rule_v1",
                        durability="current_state",
                        valid_from=ts or None,
                        evidence_references=(
                            EvidenceReference(
                                history_message_id=mid,
                                relation_type="supports",
                                excerpt=text[:200],
                                role=role,
                                speaker=speaker,
                                source_timestamp=ts,
                            ),
                        ),
                    )
                )
            elif "no nvidia gpu" in text.lower() or "no gpu" in text.lower():
                extracted.append(
                    CandidateClaimProposal(
                        subject_entity_id="system:josie",
                        predicate="hardware_gpu",
                        value_text="Josie host system has no dedicated NVIDIA GPU.",
                        memory_layer="semantic",
                        claim_category="hardware",
                        confidence=0.85 if role == "user" else 0.5,
                        confidence_basis="Rule extractor matched no GPU mention",
                        extractor_id="stub_extractor:rule_v1",
                        durability="current_state",
                        valid_from=ts or None,
                        evidence_references=(
                            EvidenceReference(
                                history_message_id=mid,
                                relation_type="supports",
                                excerpt=text[:200],
                                role=role,
                                speaker=speaker,
                                source_timestamp=ts,
                            ),
                        ),
                    )
                )
            elif "westworld" in text.lower() and "bernard" in text.lower():
                extracted.append(
                    CandidateClaimProposal(
                        subject_entity_id="assistant:bernie",
                        predicate="naming_origin",
                        value_text="Bernie was named after Bernard from Westworld.",
                        memory_layer="identity",
                        claim_category="identity",
                        confidence=0.95 if role == "user" else 0.6,
                        confidence_basis="Rule extractor matched Westworld/Bernard naming statement",
                        extractor_id="stub_extractor:rule_v1",
                        durability="durable",
                        valid_from=ts or None,
                        evidence_references=(
                            EvidenceReference(
                                history_message_id=mid,
                                relation_type="supports",
                                excerpt=text[:200],
                                role=role,
                                speaker=speaker,
                                source_timestamp=ts,
                            ),
                        ),
                    )
                )
            elif "opencode" in text.lower() and ("primary" in text.lower() or "coding worker" in text.lower()) and "fallback" not in text.lower():
                extracted.append(
                    CandidateClaimProposal(
                        subject_entity_id="system:josie",
                        predicate="primary_coding_worker",
                        value_text="OpenCode is the primary coding worker.",
                        memory_layer="procedural",
                        claim_category="architecture",
                        confidence=0.9 if role == "user" else 0.6,
                        confidence_basis="Rule extractor matched OpenCode primary coding worker statement",
                        extractor_id="stub_extractor:rule_v1",
                        durability="current_state",
                        valid_from=ts or None,
                        evidence_references=(
                            EvidenceReference(
                                history_message_id=mid,
                                relation_type="supports",
                                excerpt=text[:200],
                                role=role,
                                speaker=speaker,
                                source_timestamp=ts,
                            ),
                        ),
                    )
                )
            elif "goose" in text.lower() and "primary" in text.lower():
                extracted.append(
                    CandidateClaimProposal(
                        subject_entity_id="system:josie",
                        predicate="primary_coding_worker",
                        value_text="Goose is primary; OpenCode is fallback.",
                        memory_layer="procedural",
                        claim_category="architecture",
                        confidence=0.95 if role == "user" else 0.6,
                        confidence_basis="Rule extractor matched Goose primary/fallback statement",
                        extractor_id="stub_extractor:rule_v1",
                        durability="current_state",
                        valid_from=ts or None,
                        evidence_references=(
                            EvidenceReference(
                                history_message_id=mid,
                                relation_type="supports",
                                excerpt=text[:200],
                                role=role,
                                speaker=speaker,
                                source_timestamp=ts,
                            ),
                        ),
                    )
                )
            elif ("not_run" in text.lower() or "not run" in text.lower()) and "gate" in text.lower():
                extracted.append(
                    CandidateClaimProposal(
                        subject_entity_id="system:josie",
                        predicate="result_gate_rule",
                        value_text="Do not let NOT_RUN win a result gate.",
                        memory_layer="procedural",
                        claim_category="procedure",
                        confidence=0.95 if role == "user" else 0.6,
                        confidence_basis="Rule extractor matched NOT_RUN gate policy",
                        extractor_id="stub_extractor:rule_v1",
                        durability="durable",
                        valid_from=ts or None,
                        evidence_references=(
                            EvidenceReference(
                                history_message_id=mid,
                                relation_type="supports",
                                excerpt=text[:200],
                                role=role,
                                speaker=speaker,
                                source_timestamp=ts,
                            ),
                        ),
                    )
                )

        return extracted


class LocalModelClaimExtractor:
    """Local Ollama-backed candidate claim extractor using strict structured schema."""

    def __init__(
        self,
        *,
        ollama_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:14b",
        timeout: int = 180,
        max_messages: int = 50,
        max_message_chars: int = 400,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_messages = max_messages
        self.max_message_chars = max_message_chars

    @staticmethod
    def _schema() -> dict[str, object]:
        return {
            "type": "object",
            "required": ["proposals"],
            "additionalProperties": False,
            "properties": {
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "subject_entity_id",
                            "predicate",
                            "value_text",
                            "claim_category",
                            "confidence",
                            "confidence_basis",
                            "durability",
                            "evidence_references",
                        ],
                        "additionalProperties": False,
                        "properties": {
                            "subject_entity_id": {"type": "string"},
                            "predicate": {"type": "string"},
                            "value_text": {"type": "string"},
                            "claim_category": {
                                "type": "string",
                                "enum": sorted(list(ALLOWED_CLAIM_CATEGORIES)),
                            },
                            "confidence": {"type": "number"},
                            "confidence_basis": {"type": "string"},
                            "durability": {
                                "type": "string",
                                "enum": sorted(list(ALLOWED_DURABILITIES)),
                            },
                            "evidence_references": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["history_message_id", "relation_type", "excerpt", "attribution"],
                                    "additionalProperties": False,
                                    "properties": {
                                        "history_message_id": {"type": "integer"},
                                        "relation_type": {
                                            "type": "string",
                                            "enum": ["supports", "contradicts", "derived_from", "related_to", "supersedes", "refines"],
                                        },
                                        "excerpt": {"type": "string"},
                                        "attribution": {
                                            "type": "string",
                                            "enum": sorted(list(ALLOWED_ATTRIBUTIONS)),
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }

    def _extract_batch(
        self,
        batch_messages: Sequence[dict[str, Any]],
    ) -> list[CandidateClaimProposal]:
        if not batch_messages:
            return []

        formatted_messages: list[str] = []
        msg_lookup: dict[int, dict[str, Any]] = {}
        for m in batch_messages:
            mid = m.get("message_id")
            if mid is not None:
                try:
                    msg_lookup[int(mid)] = m
                except (ValueError, TypeError):
                    pass
            speaker = m.get("speaker") or "unknown"
            role = m.get("role") or "unknown"
            ts = m.get("timestamp") or ""
            raw = (m.get("raw_text") or "")[: self.max_message_chars]
            formatted_messages.append(
                f"[Message ID {mid} | Speaker: {speaker} | Role: {role} | Time: {ts}]\n{raw}"
            )

        user_content = (
            "Extract structured candidate claims from the following historical messages. "
            "Propose ONLY statements directly supported by evidence. "
            "Distinguish direct user statements from assistant assertions and quoted/pasted text. "
            "Use subject_entity_id 'person:dustin' for Dustin's direct facts, preferences, and background, "
            "'assistant:gemini' for Gemini Apps, 'assistant:chatgpt' for ChatGPT, and 'system:josie' ONLY for Josie architecture. "
            "Classify durability into exactly one of: "
            "- 'durable': professional certification, long-term experience/background, permanent identity (e.g. A+ certified with commercial server experience). "
            "- 'current_state': hardware inventory, point-in-time hardware ownership, current parts on hand, or lack of hardware (e.g. owns 4TB NVMes and 24TB HDDs, does not own RTX 3090). Do NOT classify hardware ownership or lack of hardware as durable. "
            "- 'preference': preferences, goals, strategies, or desired outcomes that may evolve (e.g. seeks cheapest hardware setups to achieve AI goals). "
            "- 'transient': situational, temporary task state, or short-lived intent. "
            "For each evidence reference, provide the exact verbatim excerpt/span supporting the claim: "
            "- 'direct_user_assertion': Dustin speaking directly in first-person (e.g. 'Btw i am a+ certified...', 'Btw i dont own a 3090'). "
            "- 'quoted_or_pasted_content': pasted AI output such as ChatGPT recommendations inside a user turn. "
            "- 'assistant_assertion': conversational assistant output from Gemini Apps. "
            "- 'ambiguous_source': unclear or unattributed source. "
            "Return 0 proposals if evidence is insufficient or purely conversational filler.\n\n"
            + "\n\n---\n\n".join(formatted_messages)
        )

        system_prompt = (
            "You are Josie's Candidate Claim Extractor. "
            "You propose structured candidate claims from historical conversation evidence. "
            "You CANNOT approve or promote claims; every claim starts as an unverified candidate. "
            "Do not infer beyond the evidence. "
            "Entity naming: use 'person:dustin' for Dustin's direct facts, preferences, background, and hardware; "
            "use 'assistant:gemini' for assertions made by Gemini Apps; "
            "use 'assistant:chatgpt' for assertions made by or quoted from ChatGPT; "
            "use 'system:josie' ONLY for specifications of the Josie architecture. "
            "CRITICAL TEMPORAL / DURABILITY RULES: "
            "Distinguish durable credentials/identity ('durable') from point-in-time hardware states ('current_state') and evolving goals/strategies ('preference'). "
            "Hardware ownership or lack of hardware (e.g. does not own RTX 3090) MUST be classified as 'current_state', NEVER as 'durable'. "
            "CRITICAL ATTRIBUTION RULES: Historical messages may contain mixed sources (e.g. Dustin introducing his background before pasted ChatGPT output). "
            "Excerpts within pasted AI blocks MUST be classified as 'quoted_or_pasted_content' and MUST NOT be attributed as direct Dustin assertions. "
            "Excerpts spoken directly by Dustin outside pasted blocks are 'direct_user_assertion'. "
            "For evidence_references, history_message_id MUST be the integer Message ID and excerpt MUST be verbatim text from that message. "
            "Return an empty proposals list if the evidence does not state clear persistent facts."
        )

        payload = {
            "model": self.model,
            "stream": False,
            "format": self._schema(),
            "options": {"temperature": 0.1, "num_ctx": 4096},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }

        req = Request(
            f"{self.ollama_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Local model HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Local model unavailable at {self.ollama_url}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Local model returned invalid JSON response") from exc

        content = body.get("message", {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError("Local model response lacked message content")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Failed to parse structured model output: {exc}") from exc

        proposals: list[CandidateClaimProposal] = []
        for raw_prop in parsed.get("proposals", []):
            if isinstance(raw_prop, dict):
                raw_prop["extractor_id"] = f"local_model:{self.model}"

                # Normalize subject entity ID
                subj = str(raw_prop.get("subject_entity_id") or "").strip().lower()
                refs_data = raw_prop.get("evidence_references") or []
                is_gemini = any(
                    isinstance(r, dict) and (
                        str(r.get("speaker", "")).lower() in {"gemini apps", "gemini"}
                        or "gemini" in str(r.get("excerpt", "")).lower()
                    )
                    for r in refs_data
                )
                is_chatgpt = any(
                    isinstance(r, dict) and (
                        "chatgpt" in str(r.get("excerpt", "")).lower()
                        or "gpt response" in str(r.get("excerpt", "")).lower()
                    )
                    for r in refs_data
                )

                if subj in {"google_account_owner", "user", "dustin", "me"}:
                    raw_prop["subject_entity_id"] = "person:dustin"
                elif subj in {"gemini", "gemini apps", "gemini_apps"}:
                    raw_prop["subject_entity_id"] = "assistant:gemini"
                elif subj in {"chatgpt", "gpt", "chat_gpt"}:
                    raw_prop["subject_entity_id"] = "assistant:chatgpt"
                elif subj in {"josie", "system"}:
                    if is_gemini:
                        raw_prop["subject_entity_id"] = "assistant:gemini"
                    elif is_chatgpt:
                        raw_prop["subject_entity_id"] = "assistant:chatgpt"
                    else:
                        raw_prop["subject_entity_id"] = "system:josie"

                # Normalize predicate format (alphanumeric + underscores only)
                pred = str(raw_prop.get("predicate") or "").strip().lower()
                pred = re.sub(r"[^a-z0-9_]+", "_", pred).strip("_")
                if pred:
                    raw_prop["predicate"] = pred

                # Enrich, validate and classify evidence references with actual metadata from inspected messages
                refs = raw_prop.get("evidence_references") or []
                valid_refs: list[dict[str, Any]] = []
                if isinstance(refs, list):
                    for r in refs:
                        if isinstance(r, dict):
                            mid = r.get("history_message_id")
                            src_m = msg_lookup.get(mid, {})
                            if not src_m:
                                continue
                            r_role = r.get("role") or src_m.get("role") or ""
                            r_speaker = r.get("speaker") or src_m.get("speaker") or ""
                            r_ts = r.get("source_timestamp") or src_m.get("timestamp") or ""
                            r_text = src_m.get("raw_text") or ""
                            r_excerpt = str(r.get("excerpt") or "").strip()
                            if r_excerpt and r_excerpt not in r_text:
                                clean_ex = r_excerpt.strip("\"' \t\r\n")
                                if clean_ex and clean_ex in r_text:
                                    r_excerpt = clean_ex
                                else:
                                    # Fabricated excerpt fails closed
                                    continue
                            attr, start_idx, end_idx = classify_evidence_span(
                                raw_text=r_text,
                                excerpt=r_excerpt,
                                role=r_role,
                                speaker=r_speaker,
                                span_start=r.get("span_start"),
                                span_end=r.get("span_end"),
                                proposed_attribution=r.get("attribution"),
                            )
                            r["role"] = r_role
                            r["speaker"] = r_speaker
                            r["source_timestamp"] = r_ts
                            r["excerpt"] = r_excerpt
                            r["attribution"] = attr
                            r["span_start"] = start_idx
                            r["span_end"] = end_idx
                            valid_refs.append(r)

                raw_prop["evidence_references"] = valid_refs
                if not valid_refs:
                    continue

                prop_dur = str(raw_prop.get("durability") or "").strip().lower()
                if prop_dur not in ALLOWED_DURABILITIES:
                    prop_dur = infer_durability(
                        subject_entity_id=str(raw_prop.get("subject_entity_id") or ""),
                        predicate=str(raw_prop.get("predicate") or ""),
                        value_text=str(raw_prop.get("value_text") or ""),
                        claim_category=str(raw_prop.get("claim_category") or "general"),
                    )
                # Hardware state is never durable - enforce current_state for hardware/gpu/inventory mentions
                if prop_dur == "durable":
                    pred_str = str(raw_prop.get("predicate") or "").lower()
                    cat_str = str(raw_prop.get("claim_category") or "").lower()
                    val_str = str(raw_prop.get("value_text") or "").lower()
                    if cat_str == "hardware" or any(k in pred_str for k in ("hardware", "gpu", "inventory", "own", "part", "hdd", "ssd", "nvme", "3090", "4090")):
                        prop_dur = "current_state"
                    elif any(k in val_str for k in ("own", "rtx", "gpu", "drive", "hdd", "nvme", "ram", "server part", "parts on hand")):
                        if not any(k in val_str for k in ("certified", "experience", "degree")):
                            prop_dur = "current_state"
                raw_prop["durability"] = prop_dur

                if not raw_prop.get("valid_from") and valid_refs:
                    for vr in valid_refs:
                        if vr.get("source_timestamp"):
                            raw_prop["valid_from"] = vr["source_timestamp"]
                            break

                try:
                    p = CandidateClaimProposal.from_dict(raw_prop)
                    proposals.append(p)
                except Exception:
                    continue

        return proposals

    def extract_claims(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        provenance: dict[str, Any] | None = None,
    ) -> list[CandidateClaimProposal]:
        if not messages:
            return []

        bounded = list(messages)[: self.max_messages]
        batch_size = 15
        if len(bounded) <= batch_size:
            return self._extract_batch(bounded)

        all_props: list[CandidateClaimProposal] = []
        for i in range(0, len(bounded), batch_size):
            chunk = bounded[i : i + batch_size]
            all_props.extend(self._extract_batch(chunk))
        return all_props


def stage_candidate_claims(
    store: LocalStore,
    proposals: Sequence[CandidateClaimProposal | dict[str, Any]],
    *,
    dry_run: bool = False,
    window_message_ids: set[int] | frozenset[int] | None = None,
) -> dict[str, Any]:
    """Validate, deduplicate, and stage candidate claims into SQLite memory_claims + claim_evidence.
    
    Guarantees:
    - Zero mutation when dry_run=True.
    - Proposals are validated fail-closed.
    - Identical propositions across messages deduplicate to ONE candidate claim.
    - Distinct propositions on the same subject/predicate are preserved separately.
    - All evidence references are attached to claim_evidence without overwriting.
    - Newly created claims default strictly to status='candidate', canonical_effect=0.
    """
    needed_mids: set[int] = set()
    for item in proposals:
        refs = (
            item.evidence_references
            if hasattr(item, "evidence_references")
            else (item.get("evidence_references") or [])
        )
        for r in refs:
            mid = (
                r.history_message_id
                if hasattr(r, "history_message_id")
                else (r.get("history_message_id") if isinstance(r, dict) else None)
            )
            if mid is not None:
                try:
                    needed_mids.add(int(mid))
                except (ValueError, TypeError):
                    pass

    messages_lookup: dict[int, dict[str, Any]] = {}
    if needed_mids:
        with store._connect() as conn:
            placeholders = ",".join("?" for _ in needed_mids)
            rows = conn.execute(
                f"SELECT message_id, stable_id, source_platform, source_conversation_id, "
                f"timestamp, speaker, role, raw_text, source_pointer FROM history_messages "
                f"WHERE message_id IN ({placeholders})",
                tuple(needed_mids),
            ).fetchall()
            for r in rows:
                messages_lookup[r["message_id"]] = dict(r)

    valid_proposals: list[CandidateClaimProposal] = []
    invalid_proposals: list[dict[str, Any]] = []

    for item in proposals:
        is_valid, reason = validate_proposal(
            item,
            window_message_ids=window_message_ids,
            messages_lookup=messages_lookup,
        )
        if is_valid:
            if isinstance(item, dict):
                valid_proposals.append(CandidateClaimProposal.from_dict(item))
            else:
                valid_proposals.append(item)
        else:
            invalid_proposals.append({
                "proposal": item.to_dict() if hasattr(item, "to_dict") else dict(item),
                "reason": reason,
            })

    grouped_claims: dict[str, dict[str, Any]] = {}
    for p in valid_proposals:
        cid = compute_candidate_claim_id(p.subject_entity_id, p.predicate, p.value_text)
        if cid not in grouped_claims:
            grouped_claims[cid] = {
                "claim_id": cid,
                "subject_entity_id": p.subject_entity_id.strip().lower(),
                "predicate": p.predicate.strip().lower(),
                "value_text": p.value_text.strip(),
                "memory_layer": p.memory_layer,
                "claim_category": p.claim_category,
                "base_confidence": p.confidence,
                "durability": p.durability,
                "evidence_references": list(p.evidence_references),
                "extractor_ids": {p.extractor_id} if p.extractor_id else set(),
                "valid_from": p.valid_from,
                "valid_until": p.valid_until or p.valid_to,
                "valid_to": p.valid_to,
                "notes": p.notes,
                "supersedes_claim_id": p.supersedes_claim_id,
            }
        else:
            grouped_claims[cid]["evidence_references"].extend(p.evidence_references)
            if p.extractor_id:
                grouped_claims[cid]["extractor_ids"].add(p.extractor_id)
            if p.supersedes_claim_id and not grouped_claims[cid]["supersedes_claim_id"]:
                grouped_claims[cid]["supersedes_claim_id"] = p.supersedes_claim_id
            if p.valid_from and not grouped_claims[cid]["valid_from"]:
                grouped_claims[cid]["valid_from"] = p.valid_from

    staged_claims: list[CandidateClaimRecord] = []
    evidence_rows_to_insert: list[dict[str, Any]] = []
    now = store._now()

    with store._connect() as conn:
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidate_extractions (
                    extraction_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    extractor_id TEXT NOT NULL,
                    extractor_version TEXT,
                    extracted_at TEXT NOT NULL,
                    claim_category TEXT NOT NULL,
                    temporal_hint TEXT,
                    notes TEXT,
                    raw_proposal_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(claim_id) REFERENCES memory_claims(claim_id)
                )
                """
            )

            for cid, data in grouped_claims.items():
                enriched_refs = []
                for ref in data["evidence_references"]:
                    h_info = (
                        messages_lookup.get(ref.history_message_id)
                        if (ref.history_message_id is not None and messages_lookup)
                        else None
                    )
                    if h_info is None and ref.history_message_id is not None:
                        h_row = conn.execute(
                            "SELECT message_id, stable_id, source_platform, source_conversation_id, "
                            "role, speaker, timestamp, raw_text, source_pointer "
                            "FROM history_messages WHERE message_id = ?",
                            (ref.history_message_id,),
                        ).fetchone()
                        if h_row:
                            h_info = dict(h_row)
                            messages_lookup[ref.history_message_id] = h_info

                    role_val = ref.role or (h_info["role"] if h_info else "")
                    speaker_val = ref.speaker or (h_info["speaker"] if h_info else "")
                    raw_text_val = h_info["raw_text"] if h_info else ""
                    excerpt_val = ref.excerpt or (raw_text_val[:300] if raw_text_val else "")
                    ts_val = ref.source_timestamp or (h_info["timestamp"] if h_info else "")

                    classified_attr, start_idx, end_idx = classify_evidence_span(
                        raw_text=raw_text_val,
                        excerpt=excerpt_val,
                        role=role_val,
                        speaker=speaker_val,
                        span_start=ref.span_start,
                        span_end=ref.span_end,
                        proposed_attribution=ref.attribution if ref.attribution != "ambiguous_source" else None,
                    )

                    ref = EvidenceReference(
                        history_message_id=ref.history_message_id,
                        relation_type=ref.relation_type,
                        excerpt=excerpt_val,
                        role=role_val,
                        speaker=speaker_val,
                        attribution=classified_attr,
                        span_start=start_idx,
                        span_end=end_idx,
                        source_timestamp=ts_val,
                        source_pointer=ref.source_pointer,
                        evidence_class=ref.evidence_class,
                    )
                    enriched_refs.append(ref)
                data["evidence_references"] = enriched_refs

                conf, conf_basis, evidence_class = evaluate_evidence_weight(
                    data["evidence_references"],
                    base_confidence=data["base_confidence"],
                )

                extractor_str = ", ".join(sorted(data["extractor_ids"])) if data["extractor_ids"] else "unknown"
                v_from = data.get("valid_from")
                if not v_from and data["evidence_references"]:
                    for ref in data["evidence_references"]:
                        if ref.source_timestamp:
                            v_from = ref.source_timestamp
                            break
                v_until = data.get("valid_until") or data.get("valid_to")

                record = CandidateClaimRecord(
                    claim_id=cid,
                    subject_entity_id=data["subject_entity_id"],
                    predicate=data["predicate"],
                    value_text=data["value_text"],
                    memory_layer=data["memory_layer"],
                    status="candidate",
                    evidence_class=evidence_class,
                    authority_scope=f"candidate:{data['claim_category']}",
                    confidence=conf,
                    confidence_basis=conf_basis,
                    durability=data.get("durability", "durable"),
                    valid_from=v_from,
                    valid_until=v_until,
                    valid_to=data.get("valid_to") or v_until,
                    created_at=now,
                    updated_at=now,
                    approved_by=None,
                    reviewed_at=None,
                    canonical_effect=0,
                    superseded_by_claim_id=None,
                    supersedes_claim_id=data.get("supersedes_claim_id"),
                    version=1,
                    evidence_references=tuple(data["evidence_references"]),
                    extractor_id=extractor_str,
                    claim_category=data["claim_category"],
                    notes=data["notes"],
                )
                staged_claims.append(record)

                for ref in data["evidence_references"]:
                    if ref.history_message_id is not None:
                        h_row = conn.execute(
                            "SELECT stable_id, source_platform, source_conversation_id, "
                            "timestamp, role, speaker, source_pointer, raw_text "
                            "FROM history_messages WHERE message_id = ?",
                            (ref.history_message_id,),
                        ).fetchone()
                        if h_row is None:
                            raise ValueError(
                                f"Historical evidence message_id {ref.history_message_id} does not exist in history_messages"
                            )
                        if ref.span_start is not None and ref.span_end is not None:
                            ev_id = f"history:{h_row['stable_id']}:{ref.span_start}:{ref.span_end}"
                        else:
                            ev_id = f"history:{h_row['stable_id']}"
                        src_type = "imported_history_message"
                        src_platform = h_row["source_platform"]
                        conv_id = str(h_row["source_conversation_id"] or "")
                        src_msg_id = h_row["stable_id"]
                        src_ts = h_row["timestamp"]
                        ev_role = ref.role or h_row["role"]
                        ev_speaker = ref.speaker or h_row["speaker"]
                        src_pointer = h_row["source_pointer"]
                        excerpt = ref.excerpt or h_row["raw_text"][:300]
                        excerpt_sha = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
                    else:
                        ev_id = f"ref:{hashlib.sha256(ref.source_pointer.encode('utf-8')).hexdigest()[:16]}"
                        src_type = "external_reference"
                        src_platform = None
                        conv_id = None
                        src_msg_id = None
                        src_ts = ref.source_timestamp or now
                        ev_role = ref.role
                        ev_speaker = ref.speaker
                        src_pointer = ref.source_pointer
                        excerpt = ref.excerpt
                        excerpt_sha = hashlib.sha256(excerpt.encode("utf-8")).hexdigest() if excerpt else None

                    evidence_rows_to_insert.append({
                        "claim_id": cid,
                        "evidence_id": ev_id,
                        "relation_type": ref.relation_type,
                        "source_type": src_type,
                        "source_platform": src_platform,
                        "conversation_id": conv_id,
                        "history_message_id": ref.history_message_id,
                        "source_message_id": src_msg_id,
                        "source_timestamp": src_ts,
                        "role": ev_role,
                        "speaker": ev_speaker,
                        "attribution": ref.attribution,
                        "span_start": ref.span_start,
                        "span_end": ref.span_end,
                        "source_pointer": src_pointer,
                        "evidence_class": ref.evidence_class,
                        "excerpt_sha256": excerpt_sha,
                        "created_at": now,
                    })

            if not dry_run:
                for rec in staged_claims:
                    subj = rec.subject_entity_id
                    ent_exists = conn.execute(
                        "SELECT 1 FROM entities WHERE entity_id = ?",
                        (subj,),
                    ).fetchone()
                    if not ent_exists:
                        cname = subj.split(":")[-1].replace("_", " ").title()
                        conn.execute(
                            "INSERT INTO entities("
                            "entity_id, canonical_name, normalized_name, entity_type, description, status, created_at, updated_at"
                            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                subj,
                                cname,
                                normalize_claim_value(cname),
                                subj.split(":")[0] if ":" in subj else "concept",
                                f"Entity {cname} referenced by candidate claims",
                                "active",
                                now,
                                now,
                            ),
                        )

                    existing_claim = conn.execute(
                        "SELECT claim_id FROM memory_claims WHERE claim_id = ?",
                        (rec.claim_id,),
                    ).fetchone()
                    if not existing_claim:
                        conn.execute(
                            "INSERT INTO memory_claims("
                            "claim_id, subject_entity_id, predicate, value_text, memory_layer, "
                            "status, evidence_class, authority_scope, confidence, confidence_basis, "
                            "valid_from, valid_to, created_at, updated_at, approved_by, reviewed_at, "
                            "canonical_effect, superseded_by_claim_id, version, durability"
                            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 1, ?)",
                            (
                                rec.claim_id,
                                rec.subject_entity_id,
                                rec.predicate,
                                rec.value_text,
                                rec.memory_layer,
                                rec.status,
                                rec.evidence_class,
                                rec.authority_scope,
                                rec.confidence,
                                rec.confidence_basis,
                                rec.valid_from,
                                rec.valid_to,
                                rec.created_at,
                                rec.updated_at,
                                None,
                                None,
                                None,
                                rec.durability,
                            ),
                        )
                    else:
                        conn.execute(
                            "UPDATE memory_claims SET "
                            "confidence = ?, confidence_basis = ?, evidence_class = ?, updated_at = ?, "
                            "durability = ?, valid_from = COALESCE(?, valid_from), valid_to = COALESCE(?, valid_to) "
                            "WHERE claim_id = ? AND status = 'candidate' AND canonical_effect = 0",
                            (
                                rec.confidence,
                                rec.confidence_basis,
                                rec.evidence_class,
                                now,
                                rec.durability,
                                rec.valid_from,
                                rec.valid_to,
                                rec.claim_id,
                            ),
                        )

                    ext_id = f"ext:{rec.claim_id}:{hashlib.sha256(now.encode('utf-8')).hexdigest()[:8]}"
                    conn.execute(
                        "INSERT OR REPLACE INTO candidate_extractions("
                        "extraction_id, claim_id, extractor_id, extractor_version, extracted_at, "
                        "claim_category, temporal_hint, notes, raw_proposal_json, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            ext_id,
                            rec.claim_id,
                            rec.extractor_id or "unknown",
                            CANDIDATE_SCHEMA_VERSION,
                            now,
                            rec.claim_category,
                            rec.valid_from or rec.valid_to,
                            rec.notes,
                            json.dumps(rec.to_dict(), default=str),
                            now,
                        ),
                    )

                for ev in evidence_rows_to_insert:
                    conn.execute(
                        "INSERT INTO claim_evidence("
                        "claim_id, evidence_id, relation_type, source_type, source_platform, "
                        "conversation_id, history_message_id, source_message_id, source_timestamp, "
                        "role, speaker, attribution, span_start, span_end, source_pointer, evidence_class, excerpt_sha256, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(claim_id, evidence_id, relation_type) DO UPDATE SET "
                        "attribution = excluded.attribution, "
                        "span_start = excluded.span_start, "
                        "span_end = excluded.span_end",
                        (
                            ev["claim_id"],
                            ev["evidence_id"],
                            ev["relation_type"],
                            ev["source_type"],
                            ev["source_platform"],
                            ev["conversation_id"],
                            ev["history_message_id"],
                            ev["source_message_id"],
                            ev["source_timestamp"],
                            ev["role"],
                            ev["speaker"],
                            ev["attribution"],
                            ev["span_start"],
                            ev["span_end"],
                            ev["source_pointer"],
                            ev["evidence_class"],
                            ev["excerpt_sha256"],
                            ev["created_at"],
                        ),
                    )

                conn.execute(
                    "INSERT INTO audit(created_at, event, detail) VALUES (?, ?, ?)",
                    (
                        now,
                        "candidate_claims_staged",
                        f"Staged {len(staged_claims)} candidate claims with {len(evidence_rows_to_insert)} evidence links",
                    ),
                )
        except Exception:
            conn.rollback()
            raise

    return {
        "status": "staged" if not dry_run else "dry_run",
        "dry_run": dry_run,
        "valid_proposals_count": len(valid_proposals),
        "invalid_proposals_count": len(invalid_proposals),
        "invalid_proposals": invalid_proposals,
        "unique_candidate_claims_count": len(staged_claims),
        "staged_claims": [r.to_dict() for r in staged_claims],
        "evidence_links_count": len(evidence_rows_to_insert),
    }


def clear_unadjudicated_candidate_claims(store: LocalStore) -> int:
    """Safely clear unadjudicated candidate claims (canonical_effect=0, status='candidate').

    Guarantees:
      - Does NOT touch canonical claims (canonical_effect=1).
      - Does NOT touch rejected or active claims.
      - Removes candidate extractions and associated evidence for cleared claims.
    """
    with store._connect() as conn:
        cand_ids = [
            r[0]
            for r in conn.execute(
                "SELECT claim_id FROM memory_claims WHERE status = 'candidate' AND canonical_effect = 0"
            ).fetchall()
        ]
        if not cand_ids:
            return 0
        placeholders = ",".join("?" for _ in cand_ids)
        conn.execute(f"DELETE FROM candidate_extractions WHERE claim_id IN ({placeholders})", cand_ids)
        conn.execute(f"DELETE FROM claim_evidence WHERE claim_id IN ({placeholders})", cand_ids)
        conn.execute(f"DELETE FROM memory_claims WHERE claim_id IN ({placeholders})", cand_ids)
        return len(cand_ids)


def adjudicate_candidate_claim(
    store: LocalStore,
    *,
    claim_id: str,
    action: str,
    reviewer: str,
    reason: str = "",
    supersedes_claim_id: str | None = None,
    confirmation: str | None = None,
) -> dict[str, Any]:
    """Controlled promotion/adjudication gate for candidate claims.
    
    Actions:
    - approve: Promotes candidate to active CANONICAL claim with canonical_effect=1.
      Requires explicit human reviewer and confirmation.
      Verifies candidate exists, has valid evidence links, and is in reviewable state.
      If supersedes_claim_id is supplied, atomically marks the prior claim as superseded.
    - reject: Marks candidate as rejected with canonical_effect=0, preserving provenance.
    - dispute / needs_review: Marks candidate as disputed / needs_review with canonical_effect=0.
    - supersede: Marks claim as superseded by another claim with canonical_effect=0.
    - defer: Leaves candidate in review queue with recorded audit reason.
    """
    clean_action = action.strip().lower()
    valid_actions = {"approve", "reject", "dispute", "needs_review", "mark_needs_review", "supersede", "defer"}
    if clean_action not in valid_actions:
        raise ValueError(f"Unsupported adjudication action: {action!r}. Must be one of {sorted(valid_actions)}")

    clean_reviewer = reviewer.strip()
    if not clean_reviewer:
        raise PermissionError("Reviewer identity must be explicitly provided")
    if clean_reviewer.lower() in DISALLOWED_REVIEWERS:
        raise PermissionError(f"A model or worker ({clean_reviewer}) cannot adjudicate or approve claims")
    if clean_reviewer.lower() not in ALLOWED_HUMAN_REVIEWERS:
        raise PermissionError(
            f"Reviewer '{clean_reviewer}' is not an authorized human authority. "
            "Claim adjudication requires authorization by Dustin."
        )

    now = store._now()

    with store._connect() as conn:
        try:
            existing = conn.execute(
                "SELECT claim_id, subject_entity_id, predicate, value_text, status, "
                "evidence_class, authority_scope, canonical_effect, superseded_by_claim_id "
                "FROM memory_claims WHERE claim_id = ?",
                (claim_id,),
            ).fetchone()

            if existing is None:
                raise ValueError(f"Candidate claim does not exist: {claim_id}")

            curr_status = str(existing["status"])

            if clean_action == "approve":
                if curr_status in {"rejected", "superseded"}:
                    raise ValueError(f"Cannot approve claim in {curr_status!r} state")

                if not confirmation or confirmation.strip() != APPROVAL_CONFIRMATION:
                    raise PermissionError(
                        f"Approval requires explicit human confirmation token ({APPROVAL_CONFIRMATION!r}). "
                        "A caller-controlled reviewer string alone does not constitute proof of human authority."
                    )

                evidence_count = conn.execute(
                    "SELECT COUNT(*) FROM claim_evidence WHERE claim_id = ?",
                    (claim_id,),
                ).fetchone()[0]
                if evidence_count == 0:
                    raise ValueError(f"Cannot approve candidate claim {claim_id} with zero evidence references")

                superseded_record: dict[str, Any] | None = None
                if supersedes_claim_id:
                    target_sup = conn.execute(
                        "SELECT claim_id, status FROM memory_claims WHERE claim_id = ?",
                        (supersedes_claim_id,),
                    ).fetchone()
                    if target_sup is None:
                        raise ValueError(f"Target claim to supersede does not exist: {supersedes_claim_id}")

                    conn.execute(
                        "UPDATE memory_claims SET "
                        "status = 'superseded', "
                        "canonical_effect = 0, "
                        "superseded_by_claim_id = ?, "
                        "updated_at = ? "
                        "WHERE claim_id = ?",
                        (claim_id, now, supersedes_claim_id),
                    )
                    conn.execute(
                        "INSERT INTO audit(created_at, event, detail) VALUES (?, ?, ?)",
                        (
                            now,
                            "claim_superseded",
                            f"Claim {supersedes_claim_id} superseded by approved claim {claim_id}; reviewer: {clean_reviewer}; reason: {reason}",
                        ),
                    )
                    superseded_record = {
                        "claim_id": supersedes_claim_id,
                        "superseded_by": claim_id,
                        "prior_status": str(target_sup["status"]),
                    }

                old_auth = str(existing["authority_scope"] or "")
                new_auth = (
                    f"canonical:{old_auth.split(':', 1)[1]}"
                    if old_auth.startswith("candidate:")
                    else (old_auth or "canonical:general")
                )

                conn.execute(
                    "UPDATE memory_claims SET "
                    "status = 'active', "
                    "evidence_class = 'CANONICAL', "
                    "authority_scope = ?, "
                    "canonical_effect = 1, "
                    "approved_by = ?, "
                    "reviewed_at = ?, "
                    "updated_at = ? "
                    "WHERE claim_id = ?",
                    (new_auth, clean_reviewer, now, now, claim_id),
                )

                adj_id = f"adj:{claim_id}:{hashlib.sha256((now + clean_reviewer).encode('utf-8')).hexdigest()[:12]}"
                stmt = reason or f"Approved claim {claim_id}"
                stmt_sha = hashlib.sha256(stmt.encode("utf-8")).hexdigest()
                payload_sha = hashlib.sha256(f"{claim_id}:{clean_reviewer}:{now}".encode("utf-8")).hexdigest()
                conn.execute(
                    "INSERT OR REPLACE INTO canonical_adjudications("
                    "adjudication_id, created_at, authorized_by, authority_scope, explicit_statement, "
                    "statement_sha256, source_pointer, payload_sha256, conflict_id, status, actions_executed"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'applied', 0)",
                    (adj_id, now, clean_reviewer, new_auth, stmt, stmt_sha, f"claim:{claim_id}", payload_sha, supersedes_claim_id),
                )

                conn.execute(
                    "INSERT INTO audit(created_at, event, detail) VALUES (?, ?, ?)",
                    (
                        now,
                        "candidate_claim_approved",
                        f"Candidate {claim_id} promoted to CANONICAL by {clean_reviewer}; reason: {reason}",
                    ),
                )
                return {
                    "status": "approved",
                    "claim_id": claim_id,
                    "prior_status": curr_status,
                    "resulting_status": "active",
                    "canonical_effect": 1,
                    "approved_by": clean_reviewer,
                    "reviewed_at": now,
                    "reason": reason,
                    "evidence_count": evidence_count,
                    "superseded_claim": superseded_record,
                }

            elif clean_action == "reject":
                conn.execute(
                    "UPDATE memory_claims SET "
                    "status = 'rejected', "
                    "canonical_effect = 0, "
                    "approved_by = ?, "
                    "reviewed_at = ?, "
                    "updated_at = ? "
                    "WHERE claim_id = ?",
                    (clean_reviewer, now, now, claim_id),
                )
                conn.execute(
                    "INSERT INTO audit(created_at, event, detail) VALUES (?, ?, ?)",
                    (
                        now,
                        "candidate_claim_rejected",
                        f"Candidate {claim_id} rejected by {clean_reviewer}; reason: {reason}",
                    ),
                )
                return {
                    "status": "rejected",
                    "claim_id": claim_id,
                    "prior_status": curr_status,
                    "resulting_status": "rejected",
                    "canonical_effect": 0,
                    "approved_by": clean_reviewer,
                    "reviewed_at": now,
                    "reason": reason,
                }

            elif clean_action in ("dispute", "needs_review", "mark_needs_review"):
                conn.execute(
                    "UPDATE memory_claims SET "
                    "status = 'disputed', "
                    "canonical_effect = 0, "
                    "updated_at = ? "
                    "WHERE claim_id = ?",
                    (now, claim_id),
                )
                conn.execute(
                    "INSERT INTO audit(created_at, event, detail) VALUES (?, ?, ?)",
                    (
                        now,
                        "candidate_claim_disputed",
                        f"Claim {claim_id} marked needs_review/disputed by {clean_reviewer}; reason: {reason}",
                    ),
                )
                return {
                    "status": "disputed",
                    "claim_id": claim_id,
                    "prior_status": curr_status,
                    "resulting_status": "disputed",
                    "canonical_effect": 0,
                    "reviewed_by": clean_reviewer,
                    "reviewed_at": now,
                    "reason": reason,
                }

            elif clean_action == "supersede":
                if not supersedes_claim_id:
                    raise ValueError("Supersede action requires supersedes_claim_id")
                target_claim = conn.execute(
                    "SELECT claim_id FROM memory_claims WHERE claim_id = ?",
                    (supersedes_claim_id,),
                ).fetchone()
                if target_claim is None:
                    raise ValueError(f"Target supersession claim does not exist: {supersedes_claim_id}")

                conn.execute(
                    "UPDATE memory_claims SET "
                    "status = 'superseded', "
                    "canonical_effect = 0, "
                    "superseded_by_claim_id = ?, "
                    "updated_at = ? "
                    "WHERE claim_id = ?",
                    (claim_id, now, supersedes_claim_id),
                )
                conn.execute(
                    "INSERT INTO audit(created_at, event, detail) VALUES (?, ?, ?)",
                    (
                        now,
                        "claim_superseded",
                        f"Claim {supersedes_claim_id} superseded by {claim_id}; reviewer: {clean_reviewer}; reason: {reason}",
                    ),
                )
                return {
                    "status": "superseded",
                    "claim_id": supersedes_claim_id,
                    "superseded_by": claim_id,
                    "reviewer": clean_reviewer,
                    "reviewed_at": now,
                    "reason": reason,
                }

            else:  # defer
                conn.execute(
                    "INSERT INTO audit(created_at, event, detail) VALUES (?, ?, ?)",
                    (
                        now,
                        "candidate_claim_deferred",
                        f"Candidate {claim_id} review deferred by {clean_reviewer}; reason: {reason}",
                    ),
                )
                return {
                    "status": "deferred",
                    "claim_id": claim_id,
                    "current_status": curr_status,
                    "reviewer": clean_reviewer,
                    "reviewed_at": now,
                    "reason": reason,
                }
        except Exception:
            conn.rollback()
            raise


def list_candidate_claims(
    store: LocalStore,
    *,
    status: str = "candidate",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List pending candidate claims with evidence counts and existing canonical matches."""
    db_status = STATUS_ALIAS_MAP.get(status.lower().strip(), status.lower().strip())
    with store._connect() as conn:
        claims = conn.execute(
            "SELECT c.claim_id, c.subject_entity_id, c.predicate, c.value_text, "
            "c.memory_layer, c.status, c.confidence, c.confidence_basis, c.authority_scope, c.created_at, "
            "c.durability, c.valid_from, c.valid_to, "
            "COUNT(e.evidence_id) as evidence_count "
            "FROM memory_claims c LEFT JOIN claim_evidence e ON e.claim_id = c.claim_id "
            "WHERE c.status = ? "
            "GROUP BY c.claim_id "
            "ORDER BY c.created_at DESC LIMIT ?",
            (db_status, limit),
        ).fetchall()

        results: list[dict[str, Any]] = []
        for c in claims:
            canon = conn.execute(
                "SELECT claim_id, value_text FROM memory_claims "
                "WHERE subject_entity_id = ? AND predicate = ? AND status = 'active' AND canonical_effect = 1",
                (c["subject_entity_id"], c["predicate"]),
            ).fetchone()

            user_ev = conn.execute(
                "SELECT 1 FROM claim_evidence WHERE claim_id = ? AND attribution = 'direct_user_assertion'",
                (c["claim_id"],),
            ).fetchone()

            auth_scope = str(c["authority_scope"] or "")
            cat = auth_scope.split(":", 1)[1] if ":" in auth_scope else str(c["memory_layer"])

            results.append({
                "claim_id": c["claim_id"],
                "subject_entity_id": c["subject_entity_id"],
                "predicate": c["predicate"],
                "value_text": c["value_text"],
                "memory_layer": c["memory_layer"],
                "claim_category": cat,
                "durability": c["durability"] if "durability" in c.keys() else "durable",
                "valid_from": c["valid_from"] if "valid_from" in c.keys() else None,
                "valid_to": c["valid_to"] if "valid_to" in c.keys() else None,
                "valid_until": c["valid_to"] if "valid_to" in c.keys() else None,
                "status": c["status"],
                "lifecycle_stage": "pending" if c["status"] == "candidate" else ("approved" if c["status"] == "active" else ("needs_review" if c["status"] == "disputed" else c["status"])),
                "confidence": float(c["confidence"]),
                "confidence_basis": c["confidence_basis"],
                "evidence_count": int(c["evidence_count"]),
                "created_at": c["created_at"],
                "has_user_evidence": bool(user_ev),
                "existing_canonical_match": {
                    "claim_id": canon["claim_id"],
                    "value_text": canon["value_text"],
                } if canon else None,
            })

    return results


def get_candidate_claim_details(
    store: LocalStore,
    claim_id: str,
) -> dict[str, Any] | None:
    """Inspect a candidate claim with bounded evidence excerpts, extractor metadata, and provenance."""
    with store._connect() as conn:
        claim = conn.execute(
            "SELECT * FROM memory_claims WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()

        if claim is None:
            return None

        evidence_rows = conn.execute(
            "SELECT evidence_id, relation_type, source_type, source_platform, "
            "conversation_id, history_message_id, source_timestamp, role, speaker, "
            "attribution, span_start, span_end, source_pointer, evidence_class, excerpt_sha256, created_at "
            "FROM claim_evidence WHERE claim_id = ? "
            "ORDER BY source_timestamp ASC, evidence_id ASC",
            (claim_id,),
        ).fetchall()

        evidence_list: list[dict[str, Any]] = []
        for ev in evidence_rows:
            excerpt = ""
            if ev["history_message_id"]:
                h_row = conn.execute(
                    "SELECT raw_text, source_archive, source_pointer FROM history_messages WHERE message_id = ?",
                    (ev["history_message_id"],),
                ).fetchone()
                if h_row:
                    excerpt = (h_row["raw_text"] or "")[:300]
            evidence_list.append({
                "evidence_id": ev["evidence_id"],
                "relation_type": ev["relation_type"],
                "source_type": ev["source_type"],
                "source_platform": ev["source_platform"],
                "conversation_id": ev["conversation_id"],
                "history_message_id": ev["history_message_id"],
                "source_timestamp": ev["source_timestamp"],
                "role": ev["role"],
                "speaker": ev["speaker"],
                "attribution": ev["attribution"],
                "span_start": ev["span_start"] if "span_start" in ev.keys() else None,
                "span_end": ev["span_end"] if "span_end" in ev.keys() else None,
                "source_pointer": ev["source_pointer"],
                "evidence_class": ev["evidence_class"],
                "excerpt": excerpt,
            })

        ext_row = conn.execute(
            "SELECT extractor_id, extractor_version, extracted_at, claim_category, temporal_hint, notes "
            "FROM candidate_extractions WHERE claim_id = ? ORDER BY created_at DESC LIMIT 1",
            (claim_id,),
        ).fetchone() if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_extractions'").fetchone() else None

        auth_scope = str(claim["authority_scope"] or "")
        cat = ext_row["claim_category"] if ext_row else (auth_scope.split(":", 1)[1] if ":" in auth_scope else str(claim["memory_layer"]))

        competing = conn.execute(
            "SELECT claim_id, value_text, status, confidence, approved_by, reviewed_at, created_at, superseded_by_claim_id "
            "FROM memory_claims "
            "WHERE subject_entity_id = ? AND predicate = ? AND claim_id != ? "
            "ORDER BY created_at ASC",
            (claim["subject_entity_id"], claim["predicate"], claim_id),
        ).fetchall()

        superseded_claim = conn.execute(
            "SELECT claim_id FROM memory_claims WHERE superseded_by_claim_id = ? LIMIT 1",
            (claim_id,),
        ).fetchone()

        return {
            "claim_id": claim["claim_id"],
            "subject_entity_id": claim["subject_entity_id"],
            "predicate": claim["predicate"],
            "value_text": claim["value_text"],
            "memory_layer": claim["memory_layer"],
            "claim_category": cat,
            "status": claim["status"],
            "lifecycle_stage": "pending" if claim["status"] == "candidate" else ("approved" if claim["status"] == "active" else ("needs_review" if claim["status"] == "disputed" else claim["status"])),
            "evidence_class": claim["evidence_class"],
            "authority_scope": claim["authority_scope"],
            "confidence": float(claim["confidence"]),
            "confidence_basis": claim["confidence_basis"],
            "durability": claim["durability"] if "durability" in claim.keys() else "durable",
            "valid_from": claim["valid_from"] if "valid_from" in claim.keys() else None,
            "valid_to": claim["valid_to"] if "valid_to" in claim.keys() else None,
            "valid_until": claim["valid_to"] if "valid_to" in claim.keys() else None,
            "created_at": claim["created_at"],
            "updated_at": claim["updated_at"],
            "approved_by": claim["approved_by"],
            "reviewed_at": claim["reviewed_at"],
            "canonical_effect": int(claim["canonical_effect"]),
            "superseded_by_claim_id": claim["superseded_by_claim_id"],
            "supersedes_claim_id": superseded_claim["claim_id"] if superseded_claim else None,
            "extractor_id": ext_row["extractor_id"] if ext_row else "unknown",
            "extractor_version": ext_row["extractor_version"] if ext_row else None,
            "extracted_at": ext_row["extracted_at"] if ext_row else claim["created_at"],
            "temporal_hint": ext_row["temporal_hint"] if ext_row else None,
            "notes": ext_row["notes"] if ext_row else "",
            "evidence_references": evidence_list,
            "competing_claims": [dict(r) for r in competing],
            "related_claims": [dict(r) for r in competing],
        }


def extract_claims_pipeline(
    store: LocalStore,
    *,
    history_message_ids: Sequence[int] | None = None,
    messages: Sequence[dict[str, Any]] | None = None,
    extractor: CandidateClaimExtractor | None = None,
    limit: int = 50,
    max_bundle_messages: int = DEFAULT_MAX_BUNDLE_MESSAGES,
    max_bundle_chars: int = DEFAULT_MAX_BUNDLE_CHARS,
    max_message_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
    stage: bool = False,
) -> dict[str, Any]:
    """Execute candidate claim extraction pipeline from historical evidence messages.

    Modes:
      - stage=False (default): Inspection/dry-run mode. Generates proposals and validates
        them without persisting anything to the database (zero writes).
      - stage=True: Live staging mode. Validates and stages candidates into memory_claims as
        NON-CANONICAL review candidates (status='candidate', canonical_effect=0, approved_by=NULL).
        Never approves claims. Zero priming authority.
    """
    dry_run = not stage
    raw_messages: list[dict[str, Any]] = []

    if messages is not None:
        raw_messages = list(messages)[:limit]
    else:
        with store._connect() as conn:
            if history_message_ids:
                placeholders = ",".join("?" for _ in history_message_ids[:limit])
                rows = conn.execute(
                    f"SELECT message_id, stable_id, source_platform, source_conversation_id, "
                    f"conversation_title, timestamp, speaker, role, raw_text, source_pointer "
                    f"FROM history_messages WHERE message_id IN ({placeholders}) "
                    f"ORDER BY message_id ASC",
                    list(history_message_ids[:limit]),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT message_id, stable_id, source_platform, source_conversation_id, "
                    "conversation_title, timestamp, speaker, role, raw_text, source_pointer "
                    "FROM history_messages ORDER BY message_id ASC LIMIT ?",
                    (limit,),
                ).fetchall()
            raw_messages = [dict(r) for r in rows]

    if not raw_messages:
        return {
            "status": "no_messages",
            "dry_run": dry_run,
            "inspected_messages_count": 0,
            "proposals_generated_count": 0,
            "unique_candidates_staged_count": 0,
            "staged_claims": [],
            "invalid_proposals": [],
            "evidence_links_count": 0,
        }

    bundle = validate_evidence_bundle(
        raw_messages,
        max_messages=max_bundle_messages,
        max_chars=max_bundle_chars,
        max_message_chars=max_message_chars,
    )

    if extractor is None:
        return {
            "status": "no_extractor_configured",
            "dry_run": dry_run,
            "inspected_messages_count": bundle.message_count,
            "proposals_generated_count": 0,
            "unique_candidates_staged_count": 0,
            "staged_claims": [],
            "invalid_proposals": [],
            "evidence_links_count": 0,
            "note": "Extraction requires an explicit extractor instance.",
        }

    proposals = extractor.extract_claims(
        bundle.messages,
        provenance={"inspected_count": bundle.message_count, "window_message_ids": list(bundle.window_message_ids)},
    )

    stage_result = stage_candidate_claims(
        store,
        proposals,
        dry_run=dry_run,
        window_message_ids=bundle.window_message_ids,
    )

    return {
        "status": "staged" if stage else "dry_run_complete",
        "dry_run": dry_run,
        "inspected_messages_count": bundle.message_count,
        "proposals_generated_count": len(proposals),
        "valid_proposals_count": stage_result["valid_proposals_count"],
        "invalid_proposals_count": stage_result["invalid_proposals_count"],
        "invalid_proposals": stage_result["invalid_proposals"],
        "unique_candidates_staged_count": stage_result["unique_candidate_claims_count"],
        "staged_claims": stage_result["staged_claims"],
        "evidence_links_count": stage_result["evidence_links_count"],
    }


def dry_run_extraction(
    store: LocalStore,
    *,
    history_message_ids: Sequence[int] | None = None,
    messages: Sequence[dict[str, Any]] | None = None,
    extractor: CandidateClaimExtractor | None = None,
    limit: int = 50,
    max_bundle_messages: int = DEFAULT_MAX_BUNDLE_MESSAGES,
    max_bundle_chars: int = DEFAULT_MAX_BUNDLE_CHARS,
    max_message_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
) -> dict[str, Any]:
    """Execute candidate claim extraction in DRY-RUN ONLY mode with zero database mutation."""
    return extract_claims_pipeline(
        store,
        history_message_ids=history_message_ids,
        messages=messages,
        extractor=extractor,
        limit=limit,
        max_bundle_messages=max_bundle_messages,
        max_bundle_chars=max_bundle_chars,
        max_message_chars=max_message_chars,
        stage=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI / deterministic service entrypoint for candidate claim extraction and adjudication."""
    parser = argparse.ArgumentParser(description="Josie Candidate Claim Extraction & Adjudication Pipeline")
    parser.add_argument("--db", default="data/josie.db", help="Path to SQLite database")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List candidate claims by status")
    p_list.add_argument("--status", default="candidate", help="Filter by status (pending/candidate, needs_review, active, rejected, superseded)")
    p_list.add_argument("--limit", type=int, default=50, help="Max candidates to list")
    p_list.add_argument("--json", action="store_true", help="Output JSON")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect one candidate claim with supporting evidence")
    p_inspect.add_argument("claim_id", help="Candidate claim ID")
    p_inspect.add_argument("--json", action="store_true", help="Output JSON")

    # extract
    p_extract = subparsers.add_parser("extract", help="Extract candidate claims from historical evidence")
    p_extract.add_argument("--message-ids", help="Comma-separated history_message IDs")
    p_extract.add_argument("--limit", type=int, default=50, help="Max messages to inspect")
    mode_group = p_extract.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--dry-run", action="store_true", help="Perform inspection/extraction dry-run without writing to database")
    mode_group.add_argument("--stage", action="store_true", help="Extract and persist validated NON-CANONICAL review candidates (status='candidate', canonical_effect=0)")
    p_extract.add_argument("--rule-based", action="store_true", default=False, help="Use rule-based stub extractor")
    p_extract.add_argument("--local-model", action="store_true", default=False, help="Use LocalModelClaimExtractor with configured local model")
    p_extract.add_argument("--model", default=None, help="Local model name for LocalModelClaimExtractor (e.g. 'qwen3:14b')")
    p_extract.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Ollama API base URL")
    p_extract.add_argument("--timeout", type=int, default=180, help="Extractor request timeout in seconds")
    p_extract.add_argument("--clear-pending", action="store_true", default=False, help="Clear unadjudicated candidate claims before staging")
    p_extract.add_argument("--json", action="store_true", help="Output JSON")

    # approve
    p_approve = subparsers.add_parser("approve", help="Approve candidate and promote to canonical knowledge")
    p_approve.add_argument("claim_id", help="Candidate claim ID")
    p_approve.add_argument("--reviewer", required=True, help="Reviewer identity (must be Dustin or authorized human)")
    p_approve.add_argument("--reason", default="", help="Adjudication reason/notes")
    p_approve.add_argument("--supersedes", help="Optional claim ID to supersede")
    p_approve.add_argument("--confirmation", required=True, help="Explicit human confirmation token ('EXPLICIT HUMAN APPROVAL')")
    p_approve.add_argument("--json", action="store_true", help="Output JSON")

    # reject
    p_reject = subparsers.add_parser("reject", help="Reject candidate claim")
    p_reject.add_argument("claim_id", help="Candidate claim ID")
    p_reject.add_argument("--reviewer", required=True, help="Reviewer identity (must be Dustin)")
    p_reject.add_argument("--reason", default="", help="Rejection reason")
    p_reject.add_argument("--json", action="store_true", help="Output JSON")

    # needs-review
    p_nr = subparsers.add_parser("needs-review", help="Mark candidate as needs_review / disputed")
    p_nr.add_argument("claim_id", help="Candidate claim ID")
    p_nr.add_argument("--reviewer", required=True, help="Reviewer identity (must be Dustin)")
    p_nr.add_argument("--reason", default="", help="Reason why review is needed")
    p_nr.add_argument("--json", action="store_true", help="Output JSON")

    # supersede
    p_sup = subparsers.add_parser("supersede", help="Mark prior claim as superseded")
    p_sup.add_argument("claim_id", help="Newer / superseding claim ID")
    p_sup.add_argument("--supersedes", required=True, help="Older claim ID being superseded")
    p_sup.add_argument("--reviewer", required=True, help="Reviewer identity (must be Dustin)")
    p_sup.add_argument("--reason", default="", help="Supersession reason")
    p_sup.add_argument("--json", action="store_true", help="Output JSON")

    # show-provenance
    p_prov = subparsers.add_parser("show-provenance", help="Show full provenance back to source history messages")
    p_prov.add_argument("claim_id", help="Claim ID")
    p_prov.add_argument("--json", action="store_true", help="Output JSON")

    # verify-canonical
    p_vc = subparsers.add_parser("verify-canonical", help="Verify approved claim exists in canonical store and is priming eligible")
    p_vc.add_argument("claim_id", help="Claim ID to verify")
    p_vc.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args(argv)
    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"Error: SQLite database does not exist: {db_path}", file=sys.stderr)
        return 1

    store = LocalStore(db_path)

    if args.command == "list":
        results = list_candidate_claims(store, status=args.status, limit=args.limit)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Candidate Claims ({len(results)} records, status={args.status}):")
            for r in results:
                dur_str = f" [{r.get('durability', 'durable')}]"
                print(f" - [{r['lifecycle_stage'].upper()}]{dur_str} {r['claim_id']}: {r['value_text']} ({r['evidence_count']} evidence links)")
        return 0

    elif args.command == "inspect":
        details = get_candidate_claim_details(store, args.claim_id)
        if details is None:
            print(f"Candidate claim not found: {args.claim_id}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(details, indent=2))
        else:
            print(f"Claim ID: {details['claim_id']}")
            print(f"Lifecycle: {details['lifecycle_stage']} (DB status: {details['status']})")
            print(f"Category: {details['claim_category']}")
            print(f"Durability: {details.get('durability', 'durable')}")
            if details.get("valid_from"):
                print(f"Valid From: {details['valid_from']}")
            if details.get("valid_until"):
                print(f"Valid Until: {details['valid_until']}")
            if details.get("supersedes_claim_id"):
                print(f"Supersedes: {details['supersedes_claim_id']}")
            print(f"Value: {details['value_text']}")
            print(f"Confidence: {details['confidence']} ({details['confidence_basis']})")
            print(f"Canonical Effect: {details['canonical_effect']}")
            print(f"Approved By: {details['approved_by']}")
            print(f"Evidence References ({len(details['evidence_references'])}):")
            for ev in details["evidence_references"]:
                span_str = f" span=[{ev['span_start']}..{ev['span_end']}]" if ev.get("span_start") is not None else ""
                print(f"  * [{ev['relation_type']}] Msg {ev['history_message_id']} ({ev['speaker']}/{ev['role']} -> {ev.get('attribution', 'unknown')}{span_str}): {ev['excerpt']}")
            if details["competing_claims"]:
                print(f"Competing/Related Claims ({len(details['competing_claims'])}):")
                for c in details["competing_claims"]:
                    print(f"  * [{c['status']}] {c['claim_id']}: {c['value_text']}")
        return 0

    elif args.command == "extract":
        if args.clear_pending:
            cleared = clear_unadjudicated_candidate_claims(store)
            if not args.json:
                print(f"Cleared {cleared} unadjudicated candidate claims before extraction.")

        model_name = args.model
        if not model_name and args.local_model:
            model_name = "qwen3:14b"

        if model_name:
            extractor = LocalModelClaimExtractor(
                ollama_url=args.ollama_url,
                model=model_name,
                timeout=args.timeout,
            )
        else:
            extractor = StubClaimExtractor(rule_based=args.rule_based)

        mids: list[int] | None = None
        if args.message_ids:
            mids = []
            for part in args.message_ids.split(","):
                part = part.strip()
                if not part:
                    continue
                if ".." in part:
                    s_str, e_str = part.split("..", 1)
                    mids.extend(range(int(s_str.strip()), int(e_str.strip()) + 1))
                else:
                    mids.append(int(part))
        res = extract_claims_pipeline(
            store,
            history_message_ids=mids,
            extractor=extractor,
            limit=args.limit,
            stage=args.stage,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            mode_label = "LIVE STAGING" if args.stage else "DRY RUN"
            print(f"Extraction [{mode_label}]: {res['status']}")
            print(f"Inspected messages: {res['inspected_messages_count']}")
            print(f"Proposals generated: {res['proposals_generated_count']}")
            print(f"Unique candidates staged: {res['unique_candidates_staged_count']}")
            print(f"Evidence links: {res['evidence_links_count']}")
        return 0

    elif args.command == "approve":
        res = adjudicate_candidate_claim(
            store,
            claim_id=args.claim_id,
            action="approve",
            reviewer=args.reviewer,
            reason=args.reason,
            supersedes_claim_id=args.supersedes,
            confirmation=args.confirmation,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Approved candidate {args.claim_id} -> canonical_effect={res['canonical_effect']}")
            if res.get("superseded_claim"):
                print(f"Superseded prior claim: {res['superseded_claim']['claim_id']}")
        return 0

    elif args.command == "reject":
        res = adjudicate_candidate_claim(
            store,
            claim_id=args.claim_id,
            action="reject",
            reviewer=args.reviewer,
            reason=args.reason,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Rejected candidate {args.claim_id}")
        return 0

    elif args.command == "needs-review":
        res = adjudicate_candidate_claim(
            store,
            claim_id=args.claim_id,
            action="needs_review",
            reviewer=args.reviewer,
            reason=args.reason,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Marked candidate {args.claim_id} as needs_review / disputed")
        return 0

    elif args.command == "supersede":
        res = adjudicate_candidate_claim(
            store,
            claim_id=args.claim_id,
            action="supersede",
            reviewer=args.reviewer,
            supersedes_claim_id=args.supersedes,
            reason=args.reason,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Superseded claim {args.supersedes} by {args.claim_id}")
        return 0

    elif args.command == "show-provenance":
        details = get_candidate_claim_details(store, args.claim_id)
        if not details:
            print(f"Claim not found: {args.claim_id}", file=sys.stderr)
            return 1
        prov_data = {
            "claim_id": details["claim_id"],
            "value_text": details["value_text"],
            "status": details["status"],
            "canonical_effect": details["canonical_effect"],
            "extractor_id": details["extractor_id"],
            "extracted_at": details["extracted_at"],
            "evidence_chain": details["evidence_references"],
        }
        if args.json:
            print(json.dumps(prov_data, indent=2))
        else:
            print(f"Provenance for {args.claim_id}:")
            for ev in details["evidence_references"]:
                span_str = f", span=[{ev['span_start']}..{ev['span_end']}]" if ev.get("span_start") is not None else ""
                print(f" -> Msg ID {ev['history_message_id']} ({ev['source_platform']}, {ev['source_timestamp']}, speaker={ev['speaker']}/{ev['role']}, attribution={ev.get('attribution', 'unknown')}{span_str}): {ev['excerpt']}")
        return 0

    elif args.command == "verify-canonical":
        from josie.knowledge import load_knowledge_from_store, assemble_priming_from_knowledge
        from supervisor.priming import PrimingManifest

        records = load_knowledge_from_store(store)
        matching = [r for r in records if r.record_id == args.claim_id]
        if not matching:
            print(f"Claim {args.claim_id} does not exist in store records", file=sys.stderr)
            return 1
        rec = matching[0]
        manifest = PrimingManifest(task_id="verification", knowledge_categories=(rec.category,))
        bundle = assemble_priming_from_knowledge(manifest, store=store)
        primed = any(item.item_id == args.claim_id for item in bundle.items)

        res = {
            "claim_id": rec.record_id,
            "category": rec.category,
            "status": rec.status,
            "evidence_class": rec.evidence_class,
            "is_current": rec.is_current(),
            "eligible_for_priming": primed,
        }
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Canonical Verification for {rec.record_id}:")
            print(f" - Category: {rec.category}")
            print(f" - Status: {rec.status} (is_current={rec.is_current()})")
            print(f" - Priming Eligible: {primed}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
