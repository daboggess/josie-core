"""Memory Vault Phase 3A: Safe, deterministic raw evidence ingestion foundation.

This module provides provider-neutral ingestion of historical conversation
archives (ChatGPT Takeout, Google Gemini Takeout, etc.) into Josie's SQLite
raw evidence store.

CORE PRINCIPLE:
Imported historical conversations are EVIDENCE.
They are NOT:
- current truth
- canonical knowledge
- authority
- active memory claims
- automatic Prompt Contract context

The architectural progression is:
  raw evidence/source history
  -> extracted provenance-aware candidate claims
  -> adjudicated/canonical knowledge
  -> task-specific priming
  -> WorkOrder / Prompt Contract
  -> worker

This module implements only the first arrow:
  raw external conversation archives
  -> normalized, hashed, provenance-aware local evidence records
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Iterator, Sequence
import unicodedata
import zipfile

from .storage import LocalStore

# Source Platforms
SOURCE_PLATFORM_CHATGPT = "openai_chatgpt"
SOURCE_PLATFORM_GEMINI = "google_gemini"

# Source Formats
SOURCE_FORMAT_CHATGPT_ZIP = "openai_chatgpt_takeout_zip"
SOURCE_FORMAT_CHATGPT_JSON = "openai_chatgpt_conversations_json"
SOURCE_FORMAT_GEMINI_HTML = "google_my_activity_html_cards"
SOURCE_FORMAT_GEMINI_ZIP = "google_takeout_zip"

# Allowed SQLite message roles
ALLOWED_ROLES = {"user", "assistant", "system", "tool", "activity"}


@dataclass(frozen=True)
class NormalizedEvidenceRecord:
    """A normalized raw evidence record.

    Duck-type compatible with ParsedHistoryMessage in LocalStore._import_history_records.
    """

    stable_id: str
    dedupe_key: str
    source_platform: str
    source_archive: str
    source_archive_sha256: str
    source_path: str
    source_member_sha256: str
    source_pointer: str
    source_conversation_id: str | None
    conversation_title: str | None
    source_message_id: str | None
    timestamp: str
    source_timestamp: str
    speaker: str
    role: str
    raw_text: str
    raw_checksum: str
    source_record_checksum: str
    source_order: int
    message_order: int
    activity_type: str
    attachment_references: tuple[str, ...] = ()
    historical_only: bool = True
    canonical_effect: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable_id": self.stable_id,
            "dedupe_key": self.dedupe_key,
            "source_platform": self.source_platform,
            "source_archive": self.source_archive,
            "source_archive_sha256": self.source_archive_sha256,
            "source_path": self.source_path,
            "source_member_sha256": self.source_member_sha256,
            "source_pointer": self.source_pointer,
            "source_conversation_id": self.source_conversation_id,
            "conversation_title": self.conversation_title,
            "source_message_id": self.source_message_id,
            "timestamp": self.timestamp,
            "source_timestamp": self.source_timestamp,
            "speaker": self.speaker,
            "role": self.role,
            "raw_text": self.raw_text,
            "raw_checksum": self.raw_checksum,
            "source_record_checksum": self.source_record_checksum,
            "source_order": self.source_order,
            "message_order": self.message_order,
            "activity_type": self.activity_type,
            "attachment_references": list(self.attachment_references),
            "historical_only": self.historical_only,
            "canonical_effect": self.canonical_effect,
        }


@dataclass(frozen=True)
class EvidenceChunk:
    """A deterministic chunk of a raw evidence record for indexing/retrieval.

    Chunks never act as independent claims; they remain tied to their parent evidence ID.
    """

    chunk_id: str
    parent_stable_id: str
    chunk_index: int
    total_chunks: int
    start_char: int
    end_char: int
    text: str
    chunk_sha256: str


@dataclass(frozen=True)
class MalformedRecord:
    """A malformed record encountered during parsing."""

    source_order: int
    source_pointer: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_order": self.source_order,
            "source_pointer": self.source_pointer,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ArchiveManifest:
    """Metadata inventory of an examined raw archive."""

    archive_path: str
    archive_sha256: str
    archive_bytes: int
    provider: str
    source_format: str
    member_count: int
    members: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "archive_bytes": self.archive_bytes,
            "provider": self.provider,
            "source_format": self.source_format,
            "member_count": self.member_count,
            "members": list(self.members),
        }


@dataclass(frozen=True)
class DryRunSummary:
    """Results of a non-mutating dry-run ingestion inspection."""

    status: str
    source_platform: str
    source_format: str
    source_path: str
    source_archive_sha256: str
    source_bytes: int
    conversations_discovered: int
    messages_discovered: int
    messages_would_insert: int
    duplicates: int
    conflicts: int
    malformed_count: int
    malformed_records: tuple[dict[str, Any], ...]
    database_target: str | None
    writes_performed: int = 0
    canonical_changes: int = 0
    historical_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_platform": self.source_platform,
            "source_format": self.source_format,
            "source_path": self.source_path,
            "source_archive_sha256": self.source_archive_sha256,
            "source_bytes": self.source_bytes,
            "conversations_discovered": self.conversations_discovered,
            "messages_discovered": self.messages_discovered,
            "messages_would_insert": self.messages_would_insert,
            "duplicates": self.duplicates,
            "conflicts": self.conflicts,
            "malformed_count": self.malformed_count,
            "malformed_records": list(self.malformed_records),
            "database_target": self.database_target,
            "writes_performed": self.writes_performed,
            "canonical_changes": self.canonical_changes,
            "historical_only": self.historical_only,
        }


@dataclass(frozen=True)
class IngestionSummary:
    """Results of an executed evidence ingestion."""

    status: str
    run_id: str
    source_platform: str
    source_format: str
    source_path: str
    source_archive_sha256: str
    source_bytes: int
    conversations_seen: int
    requested_messages: int
    inserted_messages: int
    deduplicated_messages: int
    malformed_count: int
    backup_path: str | None
    idempotent_replay: bool
    canonical_records_changed: int = 0
    historical_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "source_platform": self.source_platform,
            "source_format": self.source_format,
            "source_path": self.source_path,
            "source_archive_sha256": self.source_archive_sha256,
            "source_bytes": self.source_bytes,
            "conversations_seen": self.conversations_seen,
            "requested_messages": self.requested_messages,
            "inserted_messages": self.inserted_messages,
            "deduplicated_messages": self.deduplicated_messages,
            "malformed_count": self.malformed_count,
            "backup_path": self.backup_path,
            "idempotent_replay": self.idempotent_replay,
            "canonical_records_changed": self.canonical_records_changed,
            "historical_only": self.historical_only,
        }


# =====================================================================
# Normalization Utilities
# =====================================================================


def normalize_for_search(text: str) -> str:
    """Deterministic, conservative normalization of message text for SEARCH/INDEXING ONLY.

    NOTE: This is NOT stored as authoritative raw evidence text.
    history_messages.raw_text stores the verbatim extracted text from the provider record.

    Rules:
    - Standardize line endings (\r\n and \r -> \n)
    - Unicode normalization (NFKC)
    - Never summarize, paraphrase, clean up meaning, or alter words
    """
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFKC", normalized)


# Backwards-compatible alias for search/comparison helper
normalize_raw_text = normalize_for_search


def parse_unix_timestamp(ts: float | int | str | None) -> tuple[str, str]:
    """Convert a provider timestamp to (ISO_8601_UTC, original_source_str)."""
    if ts is None:
        return "1970-01-01T00:00:00Z", "none"
    if isinstance(ts, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), str(ts)
        except (ValueError, OSError):
            return "1970-01-01T00:00:00Z", str(ts)
    if isinstance(ts, str):
        clean = ts.strip()
        try:
            val = float(clean)
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), clean
        except ValueError:
            pass
        if "T" in clean:
            return clean if clean.endswith("Z") else clean + "Z", clean
        return clean, clean
    return "1970-01-01T00:00:00Z", str(ts)


def chunk_evidence_record(
    record: NormalizedEvidenceRecord,
    max_chars: int = 2000,
    overlap_chars: int = 200,
) -> list[EvidenceChunk]:
    """Deterministically chunk a raw evidence record for later retrieval without promoting claims."""
    text = record.raw_text
    total_len = len(text)
    if total_len <= max_chars or max_chars <= 0:
        chunk_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return [
            EvidenceChunk(
                chunk_id=f"{record.stable_id}:chunk:0",
                parent_stable_id=record.stable_id,
                chunk_index=0,
                total_chunks=1,
                start_char=0,
                end_char=total_len,
                text=text,
                chunk_sha256=chunk_sha,
            )
        ]

    chunks: list[EvidenceChunk] = []
    step = max(1, max_chars - overlap_chars)
    start = 0
    raw_slices: list[tuple[int, int, str]] = []

    while start < total_len:
        end = min(start + max_chars, total_len)
        chunk_str = text[start:end]
        raw_slices.append((start, end, chunk_str))
        if end >= total_len:
            break
        start += step

    total = len(raw_slices)
    for idx, (s, e, ctext) in enumerate(raw_slices):
        csha = hashlib.sha256(ctext.encode("utf-8")).hexdigest()
        chunks.append(
            EvidenceChunk(
                chunk_id=f"{record.stable_id}:chunk:{idx}",
                parent_stable_id=record.stable_id,
                chunk_index=idx,
                total_chunks=total,
                start_char=s,
                end_char=e,
                text=ctext,
                chunk_sha256=csha,
            )
        )
    return chunks


# =====================================================================
# Provider Adapters
# =====================================================================


class BaseProviderAdapter:
    """Abstract interface for provider-specific raw evidence ingestion adapters."""

    source_platform: str = "unknown"
    source_format: str = "unknown"

    def can_handle(self, source_path: Path) -> bool:
        raise NotImplementedError

    def inspect_archive(self, source_path: Path) -> ArchiveManifest:
        raise NotImplementedError

    def parse(
        self,
        source_path: Path,
        *,
        source_archive: str | None = None,
        source_archive_sha256: str | None = None,
    ) -> tuple[tuple[NormalizedEvidenceRecord, ...], tuple[MalformedRecord, ...]]:
        raise NotImplementedError


class ChatGPTTakeoutAdapter(BaseProviderAdapter):
    """Adapter for ChatGPT Takeout archives (ZIP or JSON files/directories)."""

    source_platform: str = SOURCE_PLATFORM_CHATGPT
    source_format: str = SOURCE_FORMAT_CHATGPT_ZIP

    def can_handle(self, source_path: Path) -> bool:
        p = Path(source_path)
        if p.is_file():
            if p.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(p, "r") as zf:
                        names = zf.namelist()
                        return any("conversations" in n.lower() for n in names)
                except (zipfile.BadZipFile, OSError):
                    return False
            if p.suffix.lower() == ".json" and "conversation" in p.name.lower():
                return True
        if p.is_dir():
            if (p / "conversations.json").is_file():
                return True
            if list(p.glob("conversations-*.json")):
                return True
        return False

    def inspect_archive(self, source_path: Path) -> ArchiveManifest:
        p = Path(source_path)
        if not p.exists():
            raise FileNotFoundError(f"Source archive not found at {p}")

        if p.is_file():
            size = p.stat().st_size
            hasher = hashlib.sha256()
            with p.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    hasher.update(chunk)
            archive_sha = hasher.hexdigest()

            if p.suffix.lower() == ".zip":
                with zipfile.ZipFile(p, "r") as zf:
                    members = []
                    for info in zf.infolist():
                        if "conversations" in info.filename.lower() or info.filename.endswith(".json"):
                            members.append({
                                "name": info.filename,
                                "size": info.file_size,
                                "compressed_size": info.compress_size,
                            })
                    return ArchiveManifest(
                        archive_path=str(p.resolve()),
                        archive_sha256=archive_sha,
                        archive_bytes=size,
                        provider=self.source_platform,
                        source_format=SOURCE_FORMAT_CHATGPT_ZIP,
                        member_count=len(members),
                        members=tuple(members),
                    )
            return ArchiveManifest(
                archive_path=str(p.resolve()),
                archive_sha256=archive_sha,
                archive_bytes=size,
                provider=self.source_platform,
                source_format=SOURCE_FORMAT_CHATGPT_JSON,
                member_count=1,
                members=({"name": p.name, "size": size},),
            )

        # Directory
        json_files = sorted(list(p.glob("conversations*.json")))
        members = [{"name": f.name, "size": f.stat().st_size} for f in json_files]
        total_size = sum(m["size"] for m in members)
        dir_hasher = hashlib.sha256()
        for f in json_files:
            dir_hasher.update(f.read_bytes())
        return ArchiveManifest(
            archive_path=str(p.resolve()),
            archive_sha256=dir_hasher.hexdigest(),
            archive_bytes=total_size,
            provider=self.source_platform,
            source_format=SOURCE_FORMAT_CHATGPT_JSON,
            member_count=len(members),
            members=tuple(members),
        )

    def parse(
        self,
        source_path: Path,
        *,
        source_archive: str | None = None,
        source_archive_sha256: str | None = None,
    ) -> tuple[tuple[NormalizedEvidenceRecord, ...], tuple[MalformedRecord, ...]]:
        p = Path(source_path)
        manifest = self.inspect_archive(p)
        archive_name = source_archive or p.name
        archive_sha = source_archive_sha256 or manifest.archive_sha256

        json_sources: list[tuple[str, bytes]] = []

        if p.is_file() and p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p, "r") as zf:
                for name in sorted(zf.namelist()):
                    lower = name.lower()
                    if ("conversations" in lower and lower.endswith(".json")) or lower == "conversations.json":
                        json_sources.append((name, zf.read(name)))
        elif p.is_file():
            json_sources.append((p.name, p.read_bytes()))
        elif p.is_dir():
            for f in sorted(p.glob("conversations*.json")):
                json_sources.append((f.name, f.read_bytes()))

        if not json_sources:
            raise ValueError(f"No conversation JSON files found in {p}")

        messages: list[NormalizedEvidenceRecord] = []
        malformed: list[MalformedRecord] = []
        global_source_order = 0

        for member_name, member_bytes in json_sources:
            member_sha = hashlib.sha256(member_bytes).hexdigest()
            try:
                data = json.loads(member_bytes.decode("utf-8"))
            except Exception as exc:
                malformed.append(
                    MalformedRecord(
                        source_order=global_source_order,
                        source_pointer=f"{member_name}",
                        reason=f"Failed to parse JSON: {exc}",
                    )
                )
                continue

            if not isinstance(data, list):
                malformed.append(
                    MalformedRecord(
                        source_order=global_source_order,
                        source_pointer=f"{member_name}",
                        reason="Top-level conversations JSON must be an array",
                    )
                )
                continue

            for conv_idx, conv in enumerate(data):
                if not isinstance(conv, dict):
                    malformed.append(
                        MalformedRecord(
                            source_order=global_source_order,
                            source_pointer=f"{member_name}#item-{conv_idx}",
                            reason="Conversation entry is not an object",
                        )
                    )
                    continue

                source_conv_id = str(conv.get("id") or conv.get("conversation_id") or "")
                if not source_conv_id:
                    malformed.append(
                        MalformedRecord(
                            source_order=global_source_order,
                            source_pointer=f"{member_name}#item-{conv_idx}",
                            reason="Conversation missing id",
                        )
                    )
                    continue

                title = conv.get("title")
                conv_title = str(title).strip() if title is not None else None
                mapping = conv.get("mapping")
                if not isinstance(mapping, dict):
                    continue

                conv_messages: list[dict[str, Any]] = []
                for node_id, node in mapping.items():
                    if not isinstance(node, dict):
                        continue
                    msg = node.get("message")
                    if not msg or not isinstance(msg, dict):
                        continue

                    source_msg_id = str(msg.get("id") or node_id)
                    author = msg.get("author") or {}
                    raw_role = str(author.get("role") or "user").lower()
                    role = raw_role if raw_role in ALLOWED_ROLES else "activity"

                    author_name = author.get("name")
                    if author_name:
                        speaker = str(author_name)
                    elif role == "user":
                        speaker = "user"
                    elif role == "assistant":
                        speaker = "ChatGPT"
                    else:
                        speaker = role

                    raw_time = msg.get("create_time") or conv.get("create_time")
                    iso_time, source_time = parse_unix_timestamp(raw_time)

                    content = msg.get("content") or {}
                    ct = content.get("content_type", "text")
                    activity_type = "conversation"

                    extracted_parts: list[str] = []
                    if ct in ("text", "multimodal_text"):
                        parts = content.get("parts") or []
                        for part in parts:
                            if isinstance(part, str):
                                extracted_parts.append(part)
                            elif isinstance(part, dict) and "text" in part:
                                extracted_parts.append(str(part["text"]))
                    elif ct in ("thoughts", "reasoning_recap"):
                        activity_type = "thought"
                        thoughts_list = content.get("thoughts") or []
                        if isinstance(thoughts_list, list):
                            for th in thoughts_list:
                                if isinstance(th, dict) and "content" in th:
                                    extracted_parts.append(str(th["content"]))
                        if not extracted_parts and "content" in content:
                            extracted_parts.append(str(content["content"]))
                    elif ct in ("code", "execution_output"):
                        activity_type = "code_execution"
                        if "text" in content:
                            extracted_parts.append(str(content["text"]))
                    else:
                        parts = content.get("parts") or []
                        if isinstance(parts, list):
                            extracted_parts.extend(str(p) for p in parts if p is not None)
                        elif "text" in content:
                            extracted_parts.append(str(content["text"]))

                    raw_text = "".join(extracted_parts)
                    if not raw_text.strip():
                        continue

                    record_bytes = json.dumps(msg, sort_keys=True, default=str).encode("utf-8")
                    source_rec_checksum = hashlib.sha256(record_bytes).hexdigest()
                    raw_checksum = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

                    stable_id = f"msg_chatgpt_{source_conv_id}_{source_msg_id}"
                    dedupe_key = f"openai_chatgpt:{source_conv_id}:{source_msg_id}"
                    source_pointer = f"{member_name}#{source_conv_id}:{source_msg_id}"

                    sort_key = (float(raw_time) if isinstance(raw_time, (int, float)) else 0.0)

                    conv_messages.append({
                        "sort_key": sort_key,
                        "stable_id": stable_id,
                        "dedupe_key": dedupe_key,
                        "source_platform": self.source_platform,
                        "source_archive": archive_name,
                        "source_archive_sha256": archive_sha,
                        "source_path": member_name,
                        "source_member_sha256": member_sha,
                        "source_pointer": source_pointer,
                        "source_conversation_id": source_conv_id,
                        "conversation_title": conv_title,
                        "source_message_id": source_msg_id,
                        "timestamp": iso_time,
                        "source_timestamp": source_time,
                        "speaker": speaker,
                        "role": role,
                        "raw_text": raw_text,
                        "raw_checksum": raw_checksum,
                        "source_record_checksum": source_rec_checksum,
                        "activity_type": activity_type,
                    })

                conv_messages.sort(key=lambda m: (m["sort_key"], m["source_message_id"]))

                for msg_order, m in enumerate(conv_messages):
                    messages.append(
                        NormalizedEvidenceRecord(
                            stable_id=m["stable_id"],
                            dedupe_key=m["dedupe_key"],
                            source_platform=m["source_platform"],
                            source_archive=m["source_archive"],
                            source_archive_sha256=m["source_archive_sha256"],
                            source_path=m["source_path"],
                            source_member_sha256=m["source_member_sha256"],
                            source_pointer=m["source_pointer"],
                            source_conversation_id=m["source_conversation_id"],
                            conversation_title=m["conversation_title"],
                            source_message_id=m["source_message_id"],
                            timestamp=m["timestamp"],
                            source_timestamp=m["source_timestamp"],
                            speaker=m["speaker"],
                            role=m["role"],
                            raw_text=m["raw_text"],
                            raw_checksum=m["raw_checksum"],
                            source_record_checksum=m["source_record_checksum"],
                            source_order=global_source_order,
                            message_order=msg_order,
                            activity_type=m["activity_type"],
                            attachment_references=(),
                            historical_only=True,
                            canonical_effect=False,
                        )
                    )
                    global_source_order += 1

        return tuple(messages), tuple(malformed)


class GeminiTakeoutAdapter(BaseProviderAdapter):
    """Adapter for Google Gemini Takeout archives (MyActivity.html or ZIP)."""

    source_platform: str = SOURCE_PLATFORM_GEMINI
    source_format: str = SOURCE_FORMAT_GEMINI_HTML

    def can_handle(self, source_path: Path) -> bool:
        p = Path(source_path)
        if p.is_file():
            if p.suffix.lower() == ".html" and "myactivity" in p.name.lower():
                return True
            if p.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(p, "r") as zf:
                        return any("gemini" in n.lower() and n.endswith(".html") for n in zf.namelist())
                except (zipfile.BadZipFile, OSError):
                    return False
        return False

    def inspect_archive(self, source_path: Path) -> ArchiveManifest:
        p = Path(source_path)
        if not p.exists():
            raise FileNotFoundError(f"Source archive not found at {p}")
        size = p.stat().st_size
        hasher = hashlib.sha256()
        with p.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                hasher.update(chunk)
        archive_sha = hasher.hexdigest()

        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p, "r") as zf:
                members = [{"name": i.filename, "size": i.file_size} for i in zf.infolist() if "gemini" in i.filename.lower()]
                return ArchiveManifest(
                    archive_path=str(p.resolve()),
                    archive_sha256=archive_sha,
                    archive_bytes=size,
                    provider=self.source_platform,
                    source_format=SOURCE_FORMAT_GEMINI_ZIP,
                    member_count=len(members),
                    members=tuple(members),
                )

        return ArchiveManifest(
            archive_path=str(p.resolve()),
            archive_sha256=archive_sha,
            archive_bytes=size,
            provider=self.source_platform,
            source_format=SOURCE_FORMAT_GEMINI_HTML,
            member_count=1,
            members=({"name": p.name, "size": size},),
        )

    def parse(
        self,
        source_path: Path,
        *,
        source_archive: str | None = None,
        source_archive_sha256: str | None = None,
    ) -> tuple[tuple[NormalizedEvidenceRecord, ...], tuple[MalformedRecord, ...]]:
        from .history_inheritance import dry_run_gemini_html

        p = Path(source_path)
        manifest = self.inspect_archive(p)
        archive_name = source_archive or p.name
        archive_sha = source_archive_sha256 or manifest.archive_sha256

        if p.suffix.lower() == ".zip":
            import tempfile
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(p, "r") as zf:
                    target_member = None
                    for name in zf.namelist():
                        if name.endswith("MyActivity.html") and "gemini" in name.lower():
                            target_member = name
                            break
                    if not target_member:
                        raise ValueError(f"No Gemini MyActivity.html found in {p}")
                    zf.extract(target_member, tmp_dir)
                    extracted_path = Path(tmp_dir) / target_member
                    dry_run = dry_run_gemini_html(
                        extracted_path,
                        source_archive=archive_name,
                        source_archive_sha256=archive_sha,
                        source_path=target_member,
                    )
        else:
            dry_run = dry_run_gemini_html(
                p,
                source_archive=archive_name,
                source_archive_sha256=archive_sha,
            )

        messages: list[NormalizedEvidenceRecord] = []
        for m in dry_run.messages:
            messages.append(
                NormalizedEvidenceRecord(
                    stable_id=m.stable_id,
                    dedupe_key=m.dedupe_key,
                    source_platform=m.source_platform,
                    source_archive=m.source_archive,
                    source_archive_sha256=m.source_archive_sha256,
                    source_path=m.source_path,
                    source_member_sha256=m.source_member_sha256,
                    source_pointer=m.source_pointer,
                    source_conversation_id=m.source_conversation_id,
                    conversation_title=m.conversation_title,
                    source_message_id=m.source_message_id,
                    timestamp=m.timestamp,
                    source_timestamp=m.source_timestamp,
                    speaker=m.speaker,
                    role=m.role,
                    raw_text=m.raw_text,
                    raw_checksum=m.raw_checksum,
                    source_record_checksum=m.source_record_checksum,
                    source_order=m.source_order,
                    message_order=m.message_order,
                    activity_type=m.activity_type,
                    attachment_references=m.attachment_references,
                    historical_only=True,
                    canonical_effect=False,
                )
            )

        malformed: list[MalformedRecord] = [
            MalformedRecord(
                source_order=rec.source_order,
                source_pointer=rec.source_pointer,
                reason=rec.reason,
            )
            for rec in dry_run.malformed_records
        ]
        return tuple(messages), tuple(malformed)


REGISTERED_ADAPTERS: list[BaseProviderAdapter] = [
    ChatGPTTakeoutAdapter(),
    GeminiTakeoutAdapter(),
]


def detect_adapter(source_path: Path) -> BaseProviderAdapter:
    """Detect suitable provider adapter for a raw archive."""
    p = Path(source_path)
    for adapter in REGISTERED_ADAPTERS:
        if adapter.can_handle(p):
            return adapter
    raise ValueError(f"No suitable provider adapter found for source archive: {source_path}")


def get_adapter(provider_name: str) -> BaseProviderAdapter:
    """Get adapter by provider name."""
    clean = provider_name.strip().lower()
    for adapter in REGISTERED_ADAPTERS:
        if adapter.source_platform.lower() == clean or clean in adapter.source_platform.lower():
            return adapter
    raise ValueError(f"Unknown provider name: {provider_name}")


# =====================================================================
# Ingestion Engine
# =====================================================================


def dry_run_evidence_ingest(
    source_path: Path,
    *,
    store: LocalStore | None = None,
    adapter: BaseProviderAdapter | None = None,
    source_archive: str | None = None,
    source_archive_sha256: str | None = None,
) -> DryRunSummary:
    """Inspect raw evidence archive without performing any SQLite mutations."""
    p = Path(source_path).resolve()
    active_adapter = adapter or detect_adapter(p)
    manifest = active_adapter.inspect_archive(p)

    messages, malformed = active_adapter.parse(
        p,
        source_archive=source_archive or p.name,
        source_archive_sha256=source_archive_sha256 or manifest.archive_sha256,
    )

    conv_ids = {m.source_conversation_id for m in messages if m.source_conversation_id}

    messages_would_insert = len(messages)
    duplicates = 0
    conflicts = 0

    if store is not None and store.path.exists():
        preflight = store.history_replay_preflight(messages=messages, attachments=())
        messages_would_insert = int(preflight.get("messages_would_insert", len(messages)))
        duplicates = int(preflight.get("messages_existing", 0))
        conflicts = int(preflight.get("message_conflicts", 0))

    return DryRunSummary(
        status="dry_run_complete",
        source_platform=active_adapter.source_platform,
        source_format=active_adapter.source_format,
        source_path=str(p),
        source_archive_sha256=manifest.archive_sha256,
        source_bytes=manifest.archive_bytes,
        conversations_discovered=len(conv_ids),
        messages_discovered=len(messages),
        messages_would_insert=messages_would_insert,
        duplicates=duplicates,
        conflicts=conflicts,
        malformed_count=len(malformed),
        malformed_records=tuple(m.to_dict() for m in malformed[:50]),
        database_target=str(store.path.resolve()) if store else None,
        writes_performed=0,
        canonical_changes=0,
        historical_only=True,
    )


def execute_evidence_ingest(
    source_path: Path,
    store: LocalStore,
    *,
    adapter: BaseProviderAdapter | None = None,
    run_id: str | None = None,
    source_set_id: str | None = None,
    mode: str = "isolated_test_fixture",
    backup: bool = True,
    backup_dir: Path | None = None,
    simulate_failure_after: int | None = None,
) -> IngestionSummary:
    """Safely ingest raw evidence records into SQLite history tables with idempotency and rollback."""
    p = Path(source_path).resolve()
    active_adapter = adapter or detect_adapter(p)

    dry_run = dry_run_evidence_ingest(p, store=store, adapter=active_adapter)

    if dry_run.conflicts > 0:
        raise ValueError(
            f"Evidence conflict detected ({dry_run.conflicts} records have identical keys but different content). "
            "Ingestion aborted to prevent corrupting historical records."
        )

    active_run_id = run_id or f"test-ingest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    active_set_id = source_set_id or p.stem

    if dry_run.messages_would_insert == 0 and dry_run.messages_discovered > 0:
        return IngestionSummary(
            status="idempotent_replay",
            run_id=active_run_id,
            source_platform=active_adapter.source_platform,
            source_format=active_adapter.source_format,
            source_path=str(p),
            source_archive_sha256=dry_run.source_archive_sha256,
            source_bytes=dry_run.source_bytes,
            conversations_seen=dry_run.conversations_discovered,
            requested_messages=dry_run.messages_discovered,
            inserted_messages=0,
            deduplicated_messages=dry_run.duplicates,
            malformed_count=dry_run.malformed_count,
            backup_path=None,
            idempotent_replay=True,
            canonical_records_changed=0,
            historical_only=True,
        )

    backup_path: str | None = None
    if backup and store.path.exists():
        bdir = backup_dir or (store.path.parent / "backups")
        backup_file = store.create_checkpoint_backup(bdir, label="raw-evidence")
        backup_path = str(backup_file.resolve())

    messages, malformed = active_adapter.parse(p)

    stats = store.import_raw_evidence(
        run_id=active_run_id,
        source_set_id=active_set_id,
        source_manifest_sha256=dry_run.source_archive_sha256,
        source_format=active_adapter.source_format,
        source_bytes=dry_run.source_bytes,
        messages=messages,
        attachments=(),
        mode=mode,
        authorized=True,
        simulate_failure_after=simulate_failure_after,
    )

    return IngestionSummary(
        status="success",
        run_id=active_run_id,
        source_platform=active_adapter.source_platform,
        source_format=active_adapter.source_format,
        source_path=str(p),
        source_archive_sha256=dry_run.source_archive_sha256,
        source_bytes=dry_run.source_bytes,
        conversations_seen=int(stats.get("conversations_seen", dry_run.conversations_discovered)),
        requested_messages=int(stats.get("requested_messages", len(messages))),
        inserted_messages=int(stats.get("inserted_messages", 0)),
        deduplicated_messages=int(stats.get("deduplicated_messages", 0)),
        malformed_count=len(malformed),
        backup_path=backup_path,
        idempotent_replay=bool(stats.get("idempotent_replay", False)),
        canonical_records_changed=0,
        historical_only=True,
    )


# =====================================================================
# Archive Discovery / Inventory
# =====================================================================


def discover_available_archives(
    search_roots: Sequence[str | Path] | None = None,
) -> list[dict[str, Any]]:
    """Scan configured storage paths for real historical Takeout archives."""
    roots = search_roots or [
        Path("I:/Josie-Storage/ChatGPTTO"),
        Path("I:/Josie-Storage/GoogleTO"),
        Path("I:/Josie-Storage/staging"),
        Path("D:/Josie/data"),
    ]
    discovered = []
    for root in roots:
        rp = Path(root)
        if not rp.exists():
            continue
        try:
            for p in rp.rglob("*"):
                if not p.is_file():
                    continue
                name_lower = p.name.lower()
                if (
                    name_lower.endswith(".zip")
                    or name_lower.endswith(".html")
                    or ("conversations" in name_lower and name_lower.endswith(".json"))
                ):
                    for adapter in REGISTERED_ADAPTERS:
                        if adapter.can_handle(p):
                            manifest = adapter.inspect_archive(p)
                            discovered.append({
                                "provider": adapter.source_platform,
                                "format": adapter.source_format,
                                "path": str(p.resolve()),
                                "size_bytes": manifest.archive_bytes,
                                "sha256": manifest.archive_sha256,
                                "members": manifest.member_count,
                            })
                            break
        except Exception:
            continue
    return discovered


# =====================================================================
# CLI Entrypoint
# =====================================================================


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Josie Raw Evidence Ingestion Engine")
    parser.add_argument("--archive", type=str, help="Path to archive (ZIP, HTML, or JSON)")
    parser.add_argument("--provider", type=str, help="Provider name (openai_chatgpt, google_gemini)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Perform dry-run inspection without DB writes")
    parser.add_argument("--execute", action="store_true", help="Execute live ingestion into SQLite database")
    parser.add_argument("--db", type=str, default="data/josie.db", help="Target SQLite database path")
    parser.add_argument("--inventory", action="store_true", help="Discover and report available archives on system")
    args = parser.parse_args()

    if args.inventory:
        archives = discover_available_archives()
        print(json.dumps({"discovered_archives": archives}, indent=2))
        sys.exit(0)

    if not args.archive:
        parser.print_help()
        sys.exit(1)

    archive_path = Path(args.archive).resolve()
    target_store = LocalStore(Path(args.db).resolve()) if args.db else None
    target_adapter = get_adapter(args.provider) if args.provider else None

    if args.execute:
        if not target_store:
            print("ERROR: --db is required for --execute", file=sys.stderr)
            sys.exit(1)
        summary = execute_evidence_ingest(
            archive_path,
            store=target_store,
            adapter=target_adapter,
        )
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        dry_run_res = dry_run_evidence_ingest(
            archive_path,
            store=target_store,
            adapter=target_adapter,
        )
        print(json.dumps(dry_run_res.to_dict(), indent=2))
