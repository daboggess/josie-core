"""Read-only history reconnaissance and normalized inheritance foundations.

Phase 1 parses staged Google Takeout evidence only. It has no production-import
entry point and never updates canonical state, memories, or current project facts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Iterable
from urllib.parse import urlparse


SOURCE_PLATFORM = "google_gemini"
SOURCE_FORMAT = "google_my_activity_html_cards"
MAX_HTML_BYTES = 20_000_000
GEMINI_ACTIVITY_PATH = "Takeout/My Activity/Gemini Apps/MyActivity.html"
GEMINI_METADATA_PATHS = {
    "Takeout/Gemini/gemini_gems_data.html",
    "Takeout/Gemini/gemini_scheduled_actions_data.html",
}
_CARD_MARKER = '<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">'
_TIMESTAMP = re.compile(
    r"^(?P<date>[A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}(?::\d{2})? [AP]M) "
    r"(?P<zone>[A-Z]{2,5})$"
)
_CONVERSATION_URL = re.compile(
    r"^https://gemini\.google\.com/app/(?P<id>[A-Za-z0-9_-]+)(?:[/?#].*)?$"
)
_BLOCK_TAGS = {
    "address",
    "blockquote",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ol",
    "p",
    "pre",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
_ZONE_MAP = {
    "EST": -5,
    "EDT": -4,
    "CST": -6,
    "CDT": -5,
    "MST": -7,
    "MDT": -6,
    "PST": -8,
    "PDT": -7,
    "UTC": 0,
    "GMT": 0,
}


class GeminiHistoryError(ValueError):
    """The staged Gemini history is malformed or outside Phase 1 bounds."""


@dataclass(frozen=True)
class ParsedHistoryMessage:
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
    attachment_references: tuple[str, ...]
    historical_only: bool = True
    canonical_effect: bool = False


@dataclass(frozen=True)
class MalformedHistoryRecord:
    source_order: int
    source_pointer: str
    reason: str


@dataclass(frozen=True)
class GeminiDryRun:
    messages: tuple[ParsedHistoryMessage, ...]
    malformed_records: tuple[MalformedHistoryRecord, ...]
    card_count: int
    prompted_cards: int
    activity_cards: int
    source_member_sha256: str
    source_bytes: int

    def public(self) -> dict[str, object]:
        roles = Counter(message.role for message in self.messages)
        activity_types = Counter(
            message.activity_type
            for message in self.messages
            if message.role == "activity"
        )
        conversation_ids = {
            message.source_conversation_id
            for message in self.messages
            if message.source_conversation_id
            and message.role in {"user", "assistant"}
        }
        timestamps = sorted(message.timestamp for message in self.messages)
        dedupe_counts = Counter(message.dedupe_key for message in self.messages)
        attachment_references = {
            reference
            for message in self.messages
            for reference in message.attachment_references
        }
        attachment_types = Counter(
            Path(urlparse(reference).path).suffix.lower() or "[none]"
            for reference in attachment_references
        )
        return {
            "status": "dry_run_complete",
            "source_platform": SOURCE_PLATFORM,
            "source_format": SOURCE_FORMAT,
            "source_bytes": self.source_bytes,
            "source_member_sha256": self.source_member_sha256,
            "activity_cards": self.card_count,
            "prompted_cards": self.prompted_cards,
            "non_prompt_activity_cards": self.activity_cards,
            "normalized_conversations": len(conversation_ids),
            "normalized_messages": len(self.messages),
            "user_messages": roles["user"],
            "gemini_messages": roles["assistant"],
            "activity_messages": roles["activity"],
            "prompt_cards_without_exported_response": max(
                0, self.prompted_cards - roles["assistant"]
            ),
            "prompt_cards_without_conversation_id": sum(
                1
                for message in self.messages
                if message.role == "user" and not message.source_conversation_id
            ),
            "conversation_titles_present": sum(
                1 for message in self.messages if message.conversation_title
            ),
            "source_message_ids_present": sum(
                1 for message in self.messages if message.source_message_id
            ),
            "date_range": {
                "start": timestamps[0] if timestamps else None,
                "end": timestamps[-1] if timestamps else None,
            },
            "duplicate_messages": sum(count - 1 for count in dedupe_counts.values()),
            "malformed_records": len(self.malformed_records),
            "malformed_details": [
                {
                    "source_order": record.source_order,
                    "source_pointer": record.source_pointer,
                    "reason": record.reason,
                }
                for record in self.malformed_records[:50]
            ],
            "activity_types": dict(sorted(activity_types.items())),
            "attachment_references": len(attachment_references),
            "attachment_types": dict(sorted(attachment_types.items())),
            "raw_text_utf8_bytes": sum(
                len(message.raw_text.encode("utf-8")) for message in self.messages
            ),
            "production_rows_inserted": 0,
            "canonical_state_changes": 0,
            "memories_changed": 0,
            "current_state_changed": False,
            "historical_only": True,
        }


def _append_break(parts: list[str]) -> None:
    if parts and not parts[-1].endswith("\n"):
        parts.append("\n")


class _CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.div_depth = 0
        self.section: str | None = None
        self.section_depth: int | None = None
        self.body_parts: list[str] = []
        self.caption_parts: list[str] = []
        self.hrefs: list[str] = []
        self.references: list[str] = []

    def _parts(self) -> list[str] | None:
        if self.section == "body":
            return self.body_parts
        if self.section == "caption":
            return self.caption_parts
        return None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "div":
            self.div_depth += 1
            classes = set(attributes.get("class", "").split())
            if self.section is None and {
                "content-cell",
                "mdl-typography--body-1",
            }.issubset(classes) and "mdl-typography--text-right" not in classes:
                self.section = "body"
                self.section_depth = self.div_depth
            elif self.section is None and "mdl-typography--caption" in classes:
                self.section = "caption"
                self.section_depth = self.div_depth

        parts = self._parts()
        if parts is not None:
            if tag == "br":
                parts.append("\n")
            elif tag == "li":
                _append_break(parts)
                parts.append("- ")
            elif tag in _BLOCK_TAGS:
                _append_break(parts)
            if tag == "img":
                reference = attributes.get("src", "").strip()
                if reference:
                    self.references.append(reference)
                alt = attributes.get("alt", "").strip()
                parts.append(f"[image: {alt}]" if alt else "[image]")
            elif tag == "a":
                href = attributes.get("href", "").strip()
                if href:
                    self.hrefs.append(href)
                    parsed = urlparse(href)
                    if not parsed.scheme and not href.startswith("#"):
                        self.references.append(href)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        parts = self._parts()
        if parts is not None and tag in _BLOCK_TAGS:
            _append_break(parts)
        if tag == "div":
            if self.section is not None and self.div_depth == self.section_depth:
                self.section = None
                self.section_depth = None
            self.div_depth = max(0, self.div_depth - 1)

    def handle_data(self, data: str) -> None:
        parts = self._parts()
        if parts is not None:
            parts.append(data)


def _clean_text(parts: Iterable[str]) -> str:
    text = "".join(parts).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    # Strip only wrapper whitespace. Repeated spaces and line indentation can be
    # material in prompts, source code, tables, and model output and therefore
    # must not be silently normalized away.
    return text.strip()


def classify_takeout_member(source_path: str) -> str | None:
    """Return the narrow Phase 1 Gemini relevance class for a ZIP member."""

    normalized = source_path.replace("\\", "/").lstrip("/")
    if normalized == GEMINI_ACTIVITY_PATH:
        return "gemini_activity_html"
    if normalized in GEMINI_METADATA_PATHS:
        return "gemini_metadata_html"
    attachment_root = "Takeout/My Activity/Gemini Apps/"
    if normalized.startswith(attachment_root) and normalized != attachment_root:
        return "gemini_activity_attachment"
    return None


def _parse_timestamp(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    match = _TIMESTAMP.fullmatch(normalized)
    if match is None:
        raise GeminiHistoryError("Activity timestamp format is unrecognized")
    zone_abbreviation = match.group("zone")
    utc_offset_hours = _ZONE_MAP.get(zone_abbreviation)
    if utc_offset_hours is None:
        raise GeminiHistoryError("Activity timestamp timezone is unrecognized")
    date_text = match.group("date")
    formats = ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %I:%M %p")
    naive = None
    for date_format in formats:
        try:
            naive = datetime.strptime(date_text, date_format)
            break
        except ValueError:
            continue
    if naive is None:
        raise GeminiHistoryError("Activity timestamp date is invalid")
    # Takeout records the effective zone abbreviation on each timestamp.  A
    # fixed offset preserves that evidence exactly and works on Windows Python
    # installations that do not bundle the optional IANA ``tzdata`` package.
    aware = naive.replace(
        tzinfo=timezone(timedelta(hours=utc_offset_hours), zone_abbreviation)
    )
    return aware.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _activity_type(value: str) -> str:
    clean = re.sub(r"\s+", " ", value).strip().lower()
    if clean.startswith("prompted"):
        return "prompted"
    if clean.startswith("used an assistant feature"):
        return "used_assistant_feature"
    if clean.startswith("selected "):
        return "selected_assistant_action"
    if clean.startswith("gave feedback: good"):
        return "feedback_good"
    if clean.startswith("gave feedback: bad"):
        return "feedback_bad"
    if clean.startswith("used gemini apps"):
        return "used_gemini_apps"
    if clean.startswith("created gemini canvas"):
        return "created_gemini_canvas"
    return "other_gemini_activity"


def _conversation_id(hrefs: Iterable[str]) -> str | None:
    for href in hrefs:
        match = _CONVERSATION_URL.match(href)
        if match is not None:
            return match.group("id")
    return None


def _message(
    *,
    source_archive: str,
    source_archive_sha256: str,
    source_path: str,
    source_member_sha256: str,
    card_checksum: str,
    card_index: int,
    conversation_id: str | None,
    timestamp: str,
    source_timestamp: str,
    speaker: str,
    role: str,
    raw_text: str,
    within_card_order: int,
    activity_type: str,
    references: tuple[str, ...],
) -> ParsedHistoryMessage:
    raw_checksum = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    dedupe_material = "\0".join(
        (SOURCE_PLATFORM, conversation_id or "", timestamp, role, raw_text)
    )
    dedupe_key = hashlib.sha256(dedupe_material.encode("utf-8")).hexdigest()
    stable_id = f"histmsg_{dedupe_key}"
    source_pointer = (
        f"{source_path}#activity-card-{card_index + 1}:{within_card_order}"
    )
    return ParsedHistoryMessage(
        stable_id=stable_id,
        dedupe_key=dedupe_key,
        source_platform=SOURCE_PLATFORM,
        source_archive=source_archive,
        source_archive_sha256=source_archive_sha256,
        source_path=source_path,
        source_member_sha256=source_member_sha256,
        source_pointer=source_pointer,
        source_conversation_id=conversation_id,
        conversation_title=None,
        source_message_id=None,
        timestamp=timestamp,
        source_timestamp=source_timestamp,
        speaker=speaker,
        role=role,
        raw_text=raw_text,
        raw_checksum=raw_checksum,
        source_record_checksum=card_checksum,
        source_order=card_index,
        message_order=within_card_order,
        activity_type=activity_type,
        attachment_references=references,
    )


def _parse_card(
    *,
    card_html: str,
    card_index: int,
    source_archive: str,
    source_archive_sha256: str,
    source_path: str,
    source_member_sha256: str,
) -> list[ParsedHistoryMessage]:
    parser = _CardParser()
    parser.feed(card_html)
    parser.close()
    body = _clean_text(parser.body_parts)
    if not body:
        raise GeminiHistoryError("Activity card body is empty")
    lines = body.splitlines()
    timestamp_index = None
    timestamp = None
    for index, line in enumerate(lines):
        try:
            timestamp = _parse_timestamp(line)
            timestamp_index = index
            break
        except GeminiHistoryError:
            continue
    if timestamp_index is None or timestamp is None:
        raise GeminiHistoryError("Activity card has no recognized timestamp")
    source_timestamp = lines[timestamp_index]
    leading = "\n".join(lines[:timestamp_index]).strip()
    trailing = "\n".join(lines[timestamp_index + 1 :]).strip()
    if not leading:
        raise GeminiHistoryError("Activity card has no activity text")
    activity_type = _activity_type(leading)
    conversation_id = _conversation_id(parser.hrefs)
    references = tuple(sorted(set(parser.references)))
    card_checksum = hashlib.sha256(card_html.encode("utf-8")).hexdigest()
    if activity_type == "prompted":
        prompt = re.sub(r"^Prompted\s*", "", leading, count=1, flags=re.IGNORECASE)
        if not prompt:
            raise GeminiHistoryError("Prompted activity has no prompt text")
        messages = [
            _message(
                source_archive=source_archive,
                source_archive_sha256=source_archive_sha256,
                source_path=source_path,
                source_member_sha256=source_member_sha256,
                card_checksum=card_checksum,
                card_index=card_index,
                conversation_id=conversation_id,
                timestamp=timestamp,
                source_timestamp=source_timestamp,
                speaker="google_account_owner",
                role="user",
                raw_text=prompt,
                within_card_order=0,
                activity_type=activity_type,
                references=references,
            )
        ]
        if trailing:
            messages.append(
                _message(
                    source_archive=source_archive,
                    source_archive_sha256=source_archive_sha256,
                    source_path=source_path,
                    source_member_sha256=source_member_sha256,
                    card_checksum=card_checksum,
                    card_index=card_index,
                    conversation_id=conversation_id,
                    timestamp=timestamp,
                    source_timestamp=source_timestamp,
                    speaker="Gemini Apps",
                    role="assistant",
                    raw_text=trailing,
                    within_card_order=1,
                    activity_type=activity_type,
                    references=references,
                )
            )
        return messages

    activity_text = "\n".join(part for part in (leading, trailing) if part).strip()
    return [
        _message(
            source_archive=source_archive,
            source_archive_sha256=source_archive_sha256,
            source_path=source_path,
            source_member_sha256=source_member_sha256,
            card_checksum=card_checksum,
            card_index=card_index,
            conversation_id=conversation_id,
            timestamp=timestamp,
            source_timestamp=source_timestamp,
            speaker="Google My Activity",
            role="activity",
            raw_text=activity_text,
            within_card_order=0,
            activity_type=activity_type,
            references=references,
        )
    ]


def _assign_message_order(
    messages: list[ParsedHistoryMessage],
) -> tuple[ParsedHistoryMessage, ...]:
    grouped: dict[str, list[ParsedHistoryMessage]] = defaultdict(list)
    for message in messages:
        key = message.source_conversation_id or f"activity:{message.stable_id}"
        grouped[key].append(message)
    ordered: list[ParsedHistoryMessage] = []
    for group in grouped.values():
        group.sort(
            key=lambda item: (
                item.timestamp,
                -item.source_order,
                0 if item.role == "user" else 1 if item.role == "assistant" else 2,
            )
        )
        ordered.extend(
            replace(message, message_order=index)
            for index, message in enumerate(group)
        )
    ordered.sort(key=lambda item: (item.timestamp, item.source_order, item.message_order))
    return tuple(ordered)


def dry_run_gemini_html(
    html_path: Path,
    *,
    source_archive: str,
    source_archive_sha256: str,
    source_path: str = GEMINI_ACTIVITY_PATH,
    expected_member_sha256: str | None = None,
) -> GeminiDryRun:
    if not html_path.is_file() or html_path.suffix.lower() != ".html":
        raise GeminiHistoryError("Staged Gemini activity HTML is unavailable")
    if classify_takeout_member(source_path) != "gemini_activity_html":
        raise GeminiHistoryError("Source member is not Gemini Apps activity history")
    size = html_path.stat().st_size
    if size <= 0 or size > MAX_HTML_BYTES:
        raise GeminiHistoryError("Staged Gemini activity HTML exceeds Phase 1 bounds")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", source_archive_sha256):
        raise GeminiHistoryError("Source archive SHA-256 is invalid")
    content_bytes = html_path.read_bytes()
    member_sha256 = hashlib.sha256(content_bytes).hexdigest()
    if expected_member_sha256 and member_sha256 != expected_member_sha256.lower():
        raise GeminiHistoryError("Staged Gemini HTML checksum does not match evidence")
    try:
        html = content_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GeminiHistoryError("Staged Gemini activity HTML is not UTF-8") from exc
    parts = html.split(_CARD_MARKER)
    if len(parts) < 2:
        raise GeminiHistoryError("Google My Activity cards were not found")
    messages: list[ParsedHistoryMessage] = []
    malformed: list[MalformedHistoryRecord] = []
    prompted_cards = 0
    activity_cards = 0
    for card_index, remainder in enumerate(parts[1:]):
        card_html = _CARD_MARKER + remainder
        try:
            card_messages = _parse_card(
                card_html=card_html,
                card_index=card_index,
                source_archive=source_archive,
                source_archive_sha256=source_archive_sha256.lower(),
                source_path=source_path,
                source_member_sha256=member_sha256,
            )
        except GeminiHistoryError as exc:
            malformed.append(
                MalformedHistoryRecord(
                    source_order=card_index,
                    source_pointer=f"{source_path}#activity-card-{card_index + 1}",
                    reason=str(exc),
                )
            )
            continue
        messages.extend(card_messages)
        if card_messages[0].activity_type == "prompted":
            prompted_cards += 1
        else:
            activity_cards += 1
    return GeminiDryRun(
        messages=_assign_message_order(messages),
        malformed_records=tuple(malformed),
        card_count=len(parts) - 1,
        prompted_cards=prompted_cards,
        activity_cards=activity_cards,
        source_member_sha256=member_sha256,
        source_bytes=size,
    )
