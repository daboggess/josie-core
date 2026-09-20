from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

PRIMING_SCHEMA_VERSION = "1.0"
DEFAULT_PRIMING_SCHEMA_VERSION = PRIMING_SCHEMA_VERSION
SUPPORTED_PRIMING_SCHEMA_VERSIONS = frozenset({PRIMING_SCHEMA_VERSION})

DEFAULT_MAX_ITEMS = 5
DEFAULT_MAX_CHARACTERS = 4000
DEFAULT_MAX_ITEM_CHARACTERS = 1200

HEX_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def is_sha256_hex(val: Any) -> bool:
    return bool(isinstance(val, str) and HEX_SHA256_PATTERN.match(val))


def _sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class PrimingItem:
    item_id: str
    excerpt: str
    category: str = "general"
    source_kind: str = "canonical_versioned"
    source_reference: str = ""
    confidence: str = "high"

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise ValueError("PrimingItem.item_id must be a nonempty string")
        if not isinstance(self.excerpt, str):
            raise ValueError("PrimingItem.excerpt must be a string")

    @property
    def item_hash(self) -> str:
        payload = {
            "item_id": self.item_id.strip(),
            "category": self.category.strip().lower(),
            "excerpt": self.excerpt.strip(),
            "source_kind": self.source_kind.strip().lower(),
            "source_reference": self.source_reference.strip(),
            "confidence": self.confidence.strip().lower(),
        }
        return _sha256(_canonical_json(payload))

    def to_dict(self) -> dict[str, str]:
        return {
            "item_id": self.item_id.strip(),
            "category": self.category.strip().lower(),
            "excerpt": self.excerpt.strip(),
            "source_kind": self.source_kind.strip().lower(),
            "source_reference": self.source_reference.strip(),
            "confidence": self.confidence.strip().lower(),
            "item_hash": self.item_hash,
        }

    def to_retrieved_evidence(self) -> dict[str, str]:
        return {
            "evidence_id": self.item_id.strip(),
            "excerpt": self.excerpt.strip(),
            "source_kind": self.source_kind.strip().lower(),
            "source_reference": self.source_reference.strip(),
        }


@dataclass(frozen=True)
class PrimingManifest:
    task_id: str
    knowledge_categories: tuple[str, ...] = ()
    source_references: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    max_items: int = DEFAULT_MAX_ITEMS
    max_characters: int = DEFAULT_MAX_CHARACTERS
    max_item_characters: int = DEFAULT_MAX_ITEM_CHARACTERS
    schema_version: str = PRIMING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValueError("PrimingManifest.task_id must be a nonempty string")
        if self.schema_version not in SUPPORTED_PRIMING_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported priming schema_version: {self.schema_version!r}")
        if self.max_items <= 0:
            raise ValueError("max_items must be positive")
        if self.max_characters <= 0:
            raise ValueError("max_characters must be positive")
        if self.max_item_characters <= 0:
            raise ValueError("max_item_characters must be positive")

    @property
    def manifest_hash(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "task_id": self.task_id.strip(),
            "knowledge_categories": sorted(c.strip().lower() for c in self.knowledge_categories),
            "source_references": sorted(s.strip() for s in self.source_references),
            "exclusions": sorted(e.strip().lower() for e in self.exclusions),
            "max_items": self.max_items,
            "max_characters": self.max_characters,
            "max_item_characters": self.max_item_characters,
        }
        return _sha256(_canonical_json(payload))


@dataclass(frozen=True)
class PrimingBundle:
    schema_version: str
    manifest_hash: str
    items: tuple[PrimingItem, ...] = ()
    bundle_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_PRIMING_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported priming schema_version: {self.schema_version!r}")
        if not is_sha256_hex(self.manifest_hash):
            raise ValueError(f"manifest_hash must be a valid SHA-256 hex string: {self.manifest_hash!r}")
        expected_hash = self.compute_bundle_hash(self.manifest_hash, self.items)
        if self.bundle_hash and self.bundle_hash != expected_hash:
            raise ValueError(f"bundle_hash mismatch: expected {expected_hash}, got {self.bundle_hash}")
        if not self.bundle_hash:
            object.__setattr__(self, "bundle_hash", expected_hash)

    @classmethod
    def compute_bundle_hash(cls, manifest_hash: str, items: Sequence[PrimingItem]) -> str:
        payload = {
            "manifest_hash": manifest_hash,
            "items": [item.item_hash for item in items],
        }
        return _sha256(_canonical_json(payload))

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(item.item_id for item in self.items)

    def to_retrieved_evidence(self) -> list[dict[str, str]]:
        return [item.to_retrieved_evidence() for item in self.items]

    def to_provenance_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_hash": self.bundle_hash,
            "manifest_hash": self.manifest_hash,
            "is_empty": self.is_empty,
            "item_count": len(self.items),
            "source_ids": list(self.source_ids),
            "sources": [
                {
                    "item_id": item.item_id,
                    "category": item.category,
                    "source_kind": item.source_kind,
                    "source_reference": item.source_reference,
                    "confidence": item.confidence,
                    "item_hash": item.item_hash,
                }
                for item in self.items
            ],
        }


def _normalize_record(record: Any) -> PrimingItem:
    if isinstance(record, PrimingItem):
        return record
    if hasattr(record, "to_priming_item") and callable(record.to_priming_item):
        return record.to_priming_item()
    if not isinstance(record, dict):
        raise ValueError("source record must be a dict, PrimingItem, or provide to_priming_item()")
    item_id = str(record.get("item_id") or record.get("evidence_id") or record.get("claim_id") or record.get("record_id") or "").strip()
    if not item_id:
        raise ValueError("source record missing item_id/evidence_id/claim_id")
    excerpt = str(record.get("excerpt") or record.get("text") or record.get("claim") or record.get("content") or record.get("value_text") or "")
    category = str(record.get("category") or "general").strip()
    source_kind = str(record.get("source_kind") or "canonical_versioned").strip()
    source_reference = str(record.get("source_reference") or record.get("locator") or record.get("source_pointer") or "").strip()
    confidence = str(record.get("confidence") or "high").strip()
    return PrimingItem(
        item_id=item_id,
        excerpt=excerpt,
        category=category,
        source_kind=source_kind,
        source_reference=source_reference,
        confidence=confidence,
    )


def assemble_priming_bundle(
    manifest: PrimingManifest,
    source_records: Iterable[Any],
) -> PrimingBundle:
    """Deterministically filter, bound, and assemble a PrimingBundle."""
    normalized_items: list[PrimingItem] = []
    for r in source_records:
        normalized_items.append(_normalize_record(r))

    # Sort deterministically by item_id, category, source_reference to guarantee reproducibility
    normalized_items.sort(key=lambda x: (x.item_id, x.category, x.source_reference))

    categories_filter = {c.strip().lower() for c in manifest.knowledge_categories}
    sources_filter = {s.strip() for s in manifest.source_references}
    exclusions_filter = {e.strip().lower() for e in manifest.exclusions}

    selected: list[PrimingItem] = []
    current_chars = 0

    for item in normalized_items:
        # Exclusions check
        if item.item_id.lower() in exclusions_filter:
            continue
        if item.category.lower() in exclusions_filter:
            continue
        if item.source_reference.lower() in exclusions_filter:
            continue

        # Categories filter
        if categories_filter and item.category.lower() not in categories_filter:
            continue

        # Source reference filter
        if sources_filter and item.source_reference not in sources_filter and item.item_id not in sources_filter:
            continue

        # Bound excerpt length by both max_item_characters and remaining aggregate budget
        remaining_budget = manifest.max_characters - current_chars
        if remaining_budget <= 0:
            break

        excerpt = item.excerpt.strip()
        allowed_chars = min(manifest.max_item_characters, remaining_budget)
        if allowed_chars <= 0:
            break

        if len(excerpt) > allowed_chars:
            excerpt = excerpt[:allowed_chars]

        if not excerpt:
            continue

        current_chars += len(excerpt)
        selected.append(
            PrimingItem(
                item_id=item.item_id,
                excerpt=excerpt,
                category=item.category,
                source_kind=item.source_kind,
                source_reference=item.source_reference,
                confidence=item.confidence,
            )
        )

        if len(selected) >= manifest.max_items or current_chars >= manifest.max_characters:
            break

    manifest_hash = manifest.manifest_hash
    bundle_hash = PrimingBundle.compute_bundle_hash(manifest_hash, selected)
    return PrimingBundle(
        schema_version=manifest.schema_version,
        manifest_hash=manifest_hash,
        items=tuple(selected),
        bundle_hash=bundle_hash,
    )


def apply_priming_to_work_order(
    order_data: dict[str, Any],
    bundle: PrimingBundle,
    replace_evidence: bool = False,
) -> dict[str, Any]:
    """Attach priming provenance metadata and compact evidence to a WorkOrder data dict."""
    order_data["priming_context"] = bundle.to_provenance_record()
    order_data["priming_bundle_hash"] = bundle.bundle_hash

    priming_evidence = bundle.to_retrieved_evidence()
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # Priming evidence takes first priority within the bounded worker-context budget
    for pe in priming_evidence:
        eid = pe.get("evidence_id")
        if eid and eid not in seen_ids:
            seen_ids.add(eid)
            merged.append(pe)
        elif not eid:
            merged.append(pe)
        if len(merged) >= DEFAULT_MAX_ITEMS:
            break

    # Supplement remaining slots with non-duplicate existing retrieved evidence
    if not replace_evidence and "retrieved_evidence" in order_data and len(merged) < DEFAULT_MAX_ITEMS:
        existing = list(order_data.get("retrieved_evidence") or [])
        for item in existing:
            if not isinstance(item, dict):
                continue
            eid = item.get("evidence_id")
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                merged.append(item)
            elif not eid:
                merged.append(item)
            if len(merged) >= DEFAULT_MAX_ITEMS:
                break

    order_data["retrieved_evidence"] = merged

    return order_data