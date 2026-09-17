"""Phase 2B entity resolution and explicit canonical adjudication.

Ordinary conversation may read these records but cannot write them. Canonical
claims are created only through :func:`apply_adjudication`, which requires an
exact local confirmation and an explicit Dustin-authored statement.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unicodedata

from .storage import LocalStore


SCHEMA_VERSION = 1
ADJUDICATION_CONFIRMATION = "EXPLICIT CANONICAL ADJUDICATION"
_ID = re.compile(r"[a-z0-9][a-z0-9:._-]{2,127}")
_PREDICATE = re.compile(r"[a-z][a-z0-9_]{1,63}")
_EVIDENCE_CLASSES = {"VERIFIED", "CANONICAL", "RETRIEVED", "INFERRED", "UNKNOWN"}
_CLAIM_STATUSES = {"candidate", "active", "disputed", "superseded", "rejected"}
_RELATIONS = {
    "supports", "contradicts", "derived_from", "execution_receipt",
    "supersedes", "refines", "caused_by", "related_to",
}


def normalize_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def _text(value: object, *, label: str, maximum: int = 1_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{label} is invalid")
    return value.strip()


def _identifier(value: object, *, label: str) -> str:
    clean = _text(value, label=label, maximum=128)
    if _ID.fullmatch(clean) is None:
        raise ValueError(f"{label} is invalid")
    return clean


def load_continuity_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Continuity input schema is invalid")
    return payload


def sync_entity_seed(*, store: LocalStore, payload: dict[str, object]) -> dict[str, object]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Entity seed schema is invalid")
    source_pointer = _text(payload.get("source_pointer"), label="Seed source pointer", maximum=300)
    entities = payload.get("entities")
    if not isinstance(entities, list) or not 1 <= len(entities) <= 25:
        raise ValueError("Entity seed must contain between 1 and 25 entities")
    now = store._now()
    entity_ids: list[str] = []
    alias_ids: list[str] = []
    with store._connect() as connection:
        for item in entities:
            if not isinstance(item, dict):
                raise ValueError("Entity seed entry is invalid")
            entity_id = _identifier(item.get("entity_id"), label="Entity ID")
            canonical_name = _text(item.get("canonical_name"), label="Canonical name", maximum=120)
            entity_type = _text(item.get("entity_type"), label="Entity type", maximum=40)
            description = str(item.get("description") or "").strip()
            if len(description) > 500:
                raise ValueError("Entity description is invalid")
            status = str(item.get("status") or "active")
            if status not in {"active", "inactive", "merged"}:
                raise ValueError("Entity status is invalid")
            connection.execute(
                "INSERT INTO entities(entity_id,canonical_name,normalized_name,entity_type,"
                "description,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(entity_id) DO UPDATE SET canonical_name=excluded.canonical_name,"
                "normalized_name=excluded.normalized_name,entity_type=excluded.entity_type,"
                "description=excluded.description,status=excluded.status,updated_at=excluded.updated_at",
                (entity_id, canonical_name, normalize_alias(canonical_name), entity_type,
                 description, status, now, now),
            )
            entity_ids.append(entity_id)
            aliases = item.get("aliases") or []
            if not isinstance(aliases, list) or len(aliases) > 20:
                raise ValueError("Entity aliases are invalid")
            for alias in aliases:
                if not isinstance(alias, dict):
                    raise ValueError("Entity alias entry is invalid")
                alias_text = _text(alias.get("text"), label="Alias", maximum=120)
                normalized = normalize_alias(alias_text)
                alias_id = str(alias.get("alias_id") or (
                    "alias:" + hashlib.sha256(
                        f"{entity_id}\0{normalized}".encode("utf-8")
                    ).hexdigest()[:24]
                ))
                _identifier(alias_id, label="Alias ID")
                alias_type = str(alias.get("alias_type") or "shorthand")
                if alias_type not in {"nickname", "acronym", "former_name", "speech_variant", "shorthand"}:
                    raise ValueError("Alias type is invalid")
                evidence_class = str(alias.get("evidence_class") or "CANONICAL")
                if evidence_class not in _EVIDENCE_CLASSES:
                    raise ValueError("Alias evidence class is invalid")
                confidence = float(alias.get("confidence", 1.0))
                if not 0 <= confidence <= 1:
                    raise ValueError("Alias confidence is invalid")
                ambiguity = str(alias.get("ambiguity_state") or "unambiguous")
                if ambiguity not in {"unambiguous", "context_required", "ambiguous"}:
                    raise ValueError("Alias ambiguity state is invalid")
                alias_status = str(alias.get("status") or "active")
                if alias_status not in {"active", "superseded", "rejected"}:
                    raise ValueError("Alias status is invalid")
                connection.execute(
                    "INSERT INTO entity_aliases(alias_id,entity_id,alias_text,normalized_alias,"
                    "alias_type,evidence_class,confidence,source_pointer,valid_from,valid_to,"
                    "context_entity_id,ambiguity_state,status,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(alias_id) DO UPDATE SET "
                    "alias_text=excluded.alias_text,normalized_alias=excluded.normalized_alias,"
                    "alias_type=excluded.alias_type,evidence_class=excluded.evidence_class,"
                    "confidence=excluded.confidence,source_pointer=excluded.source_pointer,"
                    "valid_from=excluded.valid_from,valid_to=excluded.valid_to,"
                    "context_entity_id=excluded.context_entity_id,"
                    "ambiguity_state=excluded.ambiguity_state,status=excluded.status,"
                    "updated_at=excluded.updated_at",
                    (alias_id, entity_id, alias_text, normalized, alias_type, evidence_class,
                     confidence, str(alias.get("source_pointer") or source_pointer),
                     alias.get("valid_from"), alias.get("valid_to"),
                     alias.get("context_entity_id"), ambiguity, alias_status, now, now),
                )
                alias_ids.append(alias_id)
    store.audit("continuity_entity_seed_synced", f"{len(entity_ids)} entities; {len(alias_ids)} aliases")
    return {
        "status": "synced", "entity_ids": entity_ids, "alias_ids": alias_ids,
        "canonical_claims_created": 0, "actions_executed": 0,
    }


def resolve_entities(
    *, store: LocalStore, text: str, context_entity_ids: list[str] | None = None
) -> dict[str, object]:
    query = normalize_alias(text)
    context = set(context_entity_ids or [])
    with store._connect() as connection:
        rows = connection.execute(
            "SELECT e.entity_id,e.canonical_name,e.entity_type,e.normalized_name,"
            "a.alias_id,a.alias_text,a.normalized_alias,a.alias_type,a.confidence,"
            "a.context_entity_id,a.ambiguity_state FROM entities e LEFT JOIN entity_aliases a "
            "ON a.entity_id=e.entity_id AND a.status='active' WHERE e.status='active'"
        ).fetchall()
    candidates: dict[tuple[str, str], dict[str, object]] = {}
    padded = f" {query} "
    for row in rows:
        variants = [(str(row["normalized_name"]), "canonical_name", None)]
        if row["normalized_alias"]:
            variants.append((str(row["normalized_alias"]), "alias", row))
        for normalized, match_type, alias in variants:
            if not normalized or not (query == normalized or f" {normalized} " in padded):
                continue
            score = 1.0 if match_type == "canonical_name" else float(alias["confidence"])
            if alias is not None and alias["context_entity_id"] in context:
                score += 0.2
            key = (normalized, str(row["entity_id"]))
            candidates[key] = {
                "mention": normalized,
                "entity_id": row["entity_id"],
                "canonical_name": row["canonical_name"],
                "entity_type": row["entity_type"],
                "match_type": match_type,
                "alias_id": alias["alias_id"] if alias is not None else None,
                "alias_type": alias["alias_type"] if alias is not None else None,
                "score": round(score, 3),
                "ambiguity_state": (
                    alias["ambiguity_state"] if alias is not None else "unambiguous"
                ),
            }
    grouped: dict[str, list[dict[str, object]]] = {}
    for candidate in candidates.values():
        grouped.setdefault(str(candidate["mention"]), []).append(candidate)
    matches: list[dict[str, object]] = []
    ambiguities: list[dict[str, object]] = []
    resolved: list[str] = []
    for mention, items in grouped.items():
        ranked = sorted(items, key=lambda item: (-float(item["score"]), str(item["entity_id"])))
        ambiguous = len({item["entity_id"] for item in ranked}) > 1 or any(
            item["ambiguity_state"] != "unambiguous" for item in ranked
        )
        if ambiguous:
            ambiguities.append({"mention": mention, "candidates": ranked})
        else:
            winner = ranked[0]
            matches.append(winner)
            if winner["entity_id"] not in resolved:
                resolved.append(str(winner["entity_id"]))
    return {
        "resolved_entity_ids": resolved,
        "alias_matches": matches,
        "candidate_ambiguity": ambiguities,
    }


def claim_context(
    *, store: LocalStore, entity_ids: list[str], predicate: str | None
) -> dict[str, object]:
    if not entity_ids:
        return {"canonical_claims": [], "unresolved_conflicts": []}
    placeholders = ",".join("?" for _ in entity_ids)
    params: list[object] = [*entity_ids]
    predicate_sql = ""
    if predicate:
        predicate_sql = " AND c.predicate=?"
        params.append(predicate)
    with store._connect() as connection:
        claims = connection.execute(
            f"SELECT c.* FROM memory_claims c WHERE c.subject_entity_id IN ({placeholders})"
            f"{predicate_sql} AND c.status='active' AND c.canonical_effect=1 "
            "ORDER BY c.reviewed_at DESC,c.claim_id",
            params,
        ).fetchall()
        conflicts = connection.execute(
            f"SELECT DISTINCT cf.* FROM claim_conflicts cf JOIN conflict_claims cc "
            "ON cc.conflict_id=cf.conflict_id JOIN memory_claims c ON c.claim_id=cc.claim_id "
            f"WHERE c.subject_entity_id IN ({placeholders}) AND cf.status='unresolved'"
            + (" AND c.predicate=?" if predicate else ""),
            params,
        ).fetchall()
        rendered_claims = []
        for row in claims:
            evidence = connection.execute(
                "SELECT evidence_id,relation_type,source_type,source_platform,conversation_id,"
                "history_message_id,source_timestamp,role,speaker,source_pointer,evidence_class "
                "FROM claim_evidence WHERE claim_id=? ORDER BY evidence_id",
                (row["claim_id"],),
            ).fetchall()
            rendered_claims.append({**dict(row), "evidence_links": [dict(item) for item in evidence]})
    return {
        "canonical_claims": rendered_claims,
        "unresolved_conflicts": [dict(row) for row in conflicts],
    }


def apply_adjudication(
    *, store: LocalStore, payload: dict[str, object], authorized_by: str,
    confirmation: str,
) -> dict[str, object]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Adjudication schema is invalid")
    if authorized_by != "Dustin" or confirmation != ADJUDICATION_CONFIRMATION:
        raise PermissionError("Explicit Dustin canonical adjudication confirmation is required")
    adjudication_id = _identifier(payload.get("adjudication_id"), label="Adjudication ID")
    statement = _text(payload.get("explicit_statement"), label="Explicit statement", maximum=2_000)
    if payload.get("authorized_by") != authorized_by:
        raise PermissionError("Adjudication actor does not match the authorized user")
    authority_scope = _text(payload.get("authority_scope"), label="Authority scope", maximum=120)
    source_pointer = _text(payload.get("source_pointer"), label="Source pointer", maximum=300)
    if not source_pointer.startswith("user_request:"):
        raise ValueError("Canonical adjudication must point to an explicit user request")
    claims = payload.get("claims")
    conflict = payload.get("conflict")
    if not isinstance(claims, list) or not 2 <= len(claims) <= 12 or not isinstance(conflict, dict):
        raise ValueError("Adjudication claims or conflict are invalid")
    canonical_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    statement_hash = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    now = store._now()
    with store._connect() as connection:
        existing = connection.execute(
            "SELECT payload_sha256,status FROM canonical_adjudications WHERE adjudication_id=?",
            (adjudication_id,),
        ).fetchone()
        if existing:
            if existing["payload_sha256"] != payload_hash or existing["status"] != "applied":
                raise ValueError("Adjudication ID conflicts with an existing record")
            return {
                "status": "already_applied", "adjudication_id": adjudication_id,
                "actions_executed": 0,
            }
        for item in claims:
            if not isinstance(item, dict):
                raise ValueError("Adjudication claim is invalid")
            claim_id = _identifier(item.get("claim_id"), label="Claim ID")
            subject = _identifier(item.get("subject_entity_id"), label="Claim subject")
            if connection.execute("SELECT 1 FROM entities WHERE entity_id=?", (subject,)).fetchone() is None:
                raise ValueError(f"Claim subject entity does not exist: {subject}")
            predicate = _text(item.get("predicate"), label="Claim predicate", maximum=64)
            if _PREDICATE.fullmatch(predicate) is None:
                raise ValueError("Claim predicate is invalid")
            value = _text(item.get("value_text"), label="Claim value", maximum=1_500)
            status = str(item.get("status"))
            evidence_class = str(item.get("evidence_class"))
            canonical = bool(item.get("canonical_effect"))
            if status not in _CLAIM_STATUSES or evidence_class not in _EVIDENCE_CLASSES:
                raise ValueError("Claim status or evidence class is invalid")
            if canonical and not (status == "active" and evidence_class == "CANONICAL"):
                raise ValueError("Canonical claims must be active and CANONICAL")
            approved_by = authorized_by if canonical else item.get("approved_by")
            reviewed_at = now if canonical else item.get("reviewed_at")
            connection.execute(
                "INSERT INTO memory_claims(claim_id,subject_entity_id,predicate,value_text,"
                "memory_layer,status,evidence_class,authority_scope,confidence,confidence_basis,"
                "valid_from,valid_to,created_at,updated_at,approved_by,reviewed_at,canonical_effect,"
                "superseded_by_claim_id,version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (claim_id, subject, predicate, value, item.get("memory_layer", "semantic"),
                 status, evidence_class, authority_scope, float(item.get("confidence", 1.0)),
                 _text(item.get("confidence_basis"), label="Confidence basis", maximum=500),
                 item.get("valid_from"), item.get("valid_to"), now, now, approved_by,
                 reviewed_at, int(canonical), item.get("superseded_by_claim_id"),
                 int(item.get("version", 1))),
            )
            links = item.get("evidence") or []
            if not isinstance(links, list) or len(links) > 20:
                raise ValueError("Claim evidence links are invalid")
            for link in links:
                if not isinstance(link, dict) or link.get("relation_type") not in _RELATIONS:
                    raise ValueError("Claim evidence relation is invalid")
                message_id = link.get("history_message_id")
                if message_id is not None:
                    source = connection.execute(
                        "SELECT hm.*,hc.source_conversation_id imported_conversation_id "
                        "FROM history_messages hm LEFT JOIN history_conversations hc "
                        "ON hc.conversation_id=hm.conversation_id WHERE hm.message_id=?",
                        (int(message_id),),
                    ).fetchone()
                    if source is None:
                        raise ValueError(f"Historical evidence does not exist: {message_id}")
                    evidence_id = f"history:{source['stable_id']}"
                    values = (
                        "imported_history_message", source["source_platform"],
                        source["imported_conversation_id"], source["source_message_id"],
                        source["timestamp"], source["role"], source["speaker"],
                        source["source_pointer"], "RETRIEVED",
                        hashlib.sha256(source["raw_text"].encode("utf-8")).hexdigest(),
                    )
                else:
                    evidence_id = f"adjudication:{adjudication_id}"
                    values = (
                        "explicit_user_adjudication", None, None, None, now, "user",
                        authorized_by, source_pointer, "CANONICAL", statement_hash,
                    )
                connection.execute(
                    "INSERT INTO claim_evidence(claim_id,evidence_id,relation_type,source_type,"
                    "source_platform,conversation_id,history_message_id,source_message_id,"
                    "source_timestamp,role,speaker,source_pointer,evidence_class,excerpt_sha256,"
                    "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (claim_id, evidence_id, link["relation_type"], values[0], values[1],
                     values[2], message_id, values[3], values[4], values[5], values[6],
                     values[7], values[8], values[9], now),
                )
        conflict_id = _identifier(conflict.get("conflict_id"), label="Conflict ID")
        resolution_claim_id = _identifier(
            conflict.get("resolution_claim_id"), label="Resolution claim ID"
        )
        reason = _text(conflict.get("resolution_reason"), label="Resolution reason", maximum=1_000)
        connection.execute(
            "INSERT INTO claim_conflicts(conflict_id,claim_scope,domain,status,resolver,"
            "resolution_timestamp,resolution_reason,resolution_claim_id,created_at,updated_at) "
            "VALUES (?,?,?,'resolved',?,?,?,?,?,?)",
            (conflict_id, authority_scope, conflict.get("domain", "historical_claim"),
             authorized_by, now, reason, resolution_claim_id, now, now),
        )
        outcomes = conflict.get("claim_outcomes")
        if not isinstance(outcomes, dict) or resolution_claim_id not in outcomes:
            raise ValueError("Conflict claim outcomes are invalid")
        for claim_id, outcome in outcomes.items():
            _identifier(claim_id, label="Conflict claim ID")
            if outcome not in {"competing", "prevailing", "superseded", "rejected", "context"}:
                raise ValueError("Conflict outcome is invalid")
            connection.execute(
                "INSERT INTO conflict_claims(conflict_id,claim_id,outcome) VALUES (?,?,?)",
                (conflict_id, claim_id, outcome),
            )
        connection.execute(
            "INSERT INTO canonical_adjudications(adjudication_id,created_at,authorized_by,"
            "authority_scope,explicit_statement,statement_sha256,source_pointer,payload_sha256,"
            "conflict_id,status,actions_executed) VALUES (?,?,?,?,?,?,?,?,?,'applied',0)",
            (adjudication_id, now, authorized_by, authority_scope, statement, statement_hash,
             source_pointer, payload_hash, conflict_id),
        )
    store.audit("canonical_adjudication_applied", f"{adjudication_id}: {authorized_by}; {conflict_id}")
    return {
        "status": "applied", "adjudication_id": adjudication_id,
        "conflict_id": conflict_id,
        "canonical_claim_ids": [
            item["claim_id"] for item in claims if item.get("canonical_effect") is True
        ],
        "source_records_modified": 0, "actions_executed": 0,
    }


def continuity_status(store: LocalStore) -> dict[str, object]:
    with store._connect() as connection:
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "entities", "entity_aliases", "entity_relationships", "memory_claims",
                "claim_evidence", "claim_conflicts", "canonical_adjudications",
            )
        }
    return {"status": "ok", "schema_version": SCHEMA_VERSION, **counts, "actions_executed": 0}
