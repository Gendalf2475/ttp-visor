from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.types import Message

from app.config.loader import PunishmentParserConfig
from app.utils.dates import to_utc
from app.utils.regex import contains_any, first_match, stable_hash
from app.utils.text import normalize_nickname


DEFAULT_ID_PATTERNS = [
    r"(?:наказани[ея]|punishment|id)\D{0,12}#?([A-Za-zА-Яа-я0-9_-]+)",
    r"#(\d{3,})",
]
STRICT_MODERATOR_PATTERNS = [
    r"(?im)^\s*Модератор\s*:\s*(?P<moderator>[^\n\r]+)\s*$",
]
STRICT_TARGET_PATTERNS = [
    r"(?im)^\s*Нарушитель\s*:\s*(?P<target>[^\n\r]+)\s*$",
]
STRICT_DATE_PATTERNS = [
    r"(?im)^\s*Дата\s*:\s*(?P<date>[^\n\r]+)\s*$",
]
DEFAULT_REASON_PATTERNS = [
    r"(?:причина|reason)\s*[:\-]\s*([^\n]+)",
]
DEFAULT_ISSUED_MARKERS = ["выдал", "выдан", "наказал", "наказание", "ban", "mute", "warn", "кик"]
DEFAULT_REMOVED_MARKERS = ["снял", "снято", "разбан", "размут", "unban", "unmute", "амнист"]
PUNISHMENT_TYPES = {"ban", "mute", "warn", "unban", "unmute", "unwarn"}
RULE_PATTERNS = [
    r"(?:пункт|п\.|правил[ао]?|rule)\s*[:#№\-]?\s*\d+(?:\.\d+)*",
    r"\b\d+\.\d+(?:\.\d+)*\b",
]
INVALID_MODERATOR_ALIAS_LABELS = {
    "unknown",
    "нарушитель",
    "длительность",
    "причина",
    "дата",
    "модератор",
}
VALID_ACTIONS = {"issued", "removed"}


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ParsedPunishment:
    event_key: str
    punishment_id: str | None
    action: str
    punishment_type: str
    rule_missing: bool
    is_valid: bool
    target: str | None
    reason: str | None
    moderator_alias: str | None
    chat_id: int
    topic_id: int | None
    message_id: int
    punished_at: datetime
    raw_text: str


@dataclass(slots=True)
class PunishmentParseDiagnostics:
    parsed: ParsedPunishment | None
    failure_reason: str | None = None

    @property
    def success(self) -> bool:
        return self.parsed is not None


class PunishmentParser:
    def __init__(self, config: PunishmentParserConfig, timezone_name: str = "Europe/Moscow"):
        self.id_patterns = config.ticket_id_patterns or DEFAULT_ID_PATTERNS
        self.moderator_patterns = STRICT_MODERATOR_PATTERNS
        self.required_markers = config.required_markers
        self.issued_markers = config.issued_markers or DEFAULT_ISSUED_MARKERS
        self.removed_markers = config.removed_markers or DEFAULT_REMOVED_MARKERS
        self.timezone = ZoneInfo(timezone_name)

    def parse(self, message: Message) -> ParsedPunishment | None:
        return self.parse_with_diagnostics(message).parsed

    def parse_with_diagnostics(self, message: Message) -> PunishmentParseDiagnostics:
        text = normalize_punishment_text(message.text or message.caption or "")
        if not text.strip():
            return PunishmentParseDiagnostics(parsed=None, failure_reason="empty_text_and_caption")
        if self.required_markers and not contains_any(self.required_markers, text):
            return PunishmentParseDiagnostics(parsed=None, failure_reason="required_markers_missing")

        punishment_type = classify_punishment_type(text)
        action = action_from_punishment_type(punishment_type)
        first_line = punishment_header_line(text)
        logger.info(
            "Punishment type detected: first_line=%r punishment_type=%s action=%s",
            first_line,
            punishment_type,
            action,
        )
        if punishment_type is None or action is None:
            return PunishmentParseDiagnostics(
                parsed=None,
                failure_reason=f"punishment_type_not_detected first_line={first_line or 'none'}",
            )

        punishment_id = first_match(self.id_patterns, text)
        raw_moderator_alias = first_match(self.moderator_patterns, text)
        moderator_alias = normalize_punishment_moderator_alias(raw_moderator_alias)
        if is_invalid_punishment_moderator_alias(moderator_alias):
            return PunishmentParseDiagnostics(
                parsed=None,
                failure_reason=f"invalid_moderator_alias alias={moderator_alias or 'none'}",
            )

        target = first_match(STRICT_TARGET_PATTERNS, text)
        punished_at = parse_punishment_date(first_match(STRICT_DATE_PATTERNS, text), self.timezone)
        if punished_at is None:
            punished_at = to_utc(message.date)

        event_key = (
            f"punishment:{action}:{message.chat.id}:{punishment_id}"
            if punishment_id
            else self._message_event_key(message, text, action)
        )

        diagnostics = PunishmentParseDiagnostics(
            parsed=ParsedPunishment(
                event_key=event_key,
                punishment_id=punishment_id,
                action=action,
                punishment_type=punishment_type,
                rule_missing=is_rule_missing(text),
                is_valid=True,
                target=target,
                reason=first_match(DEFAULT_REASON_PATTERNS, text),
                moderator_alias=moderator_alias,
                chat_id=message.chat.id,
                topic_id=message.message_thread_id,
                message_id=message.message_id,
                punished_at=punished_at,
                raw_text=text,
            )
        )
        return diagnostics

    def _detect_action(self, text: str, punishment_type: str | None) -> str | None:
        return action_from_punishment_type(punishment_type)

    @staticmethod
    def _message_event_key(message: Message, text: str, action: str) -> str:
        fingerprint = stable_hash(message.chat.id, message.message_id, text, action)[:16]
        return f"punishment:{action}:message:{message.chat.id}:{message.message_id}:{fingerprint}"


def classify_punishment_type(text: str) -> str | None:
    first_line_upper = punishment_header_line(text).upper()
    if "СНЯТИЕ | БЛОКИРОВКА ЧАТА" in first_line_upper:
        return "unmute"
    if "СНЯТИЕ | БЛОКИРОВКА" in first_line_upper:
        return "unban"
    if "СНЯТИЕ | ПРЕДУПРЕЖДЕНИЕ" in first_line_upper:
        return "unwarn"
    if "БЛОКИРОВКА ЧАТА" in first_line_upper:
        return "mute"
    if "БЛОКИРОВКА" in first_line_upper:
        return "ban"
    if "ПРЕДУПРЕЖДЕНИЕ" in first_line_upper:
        return "warn"
    return None


def punishment_header_line(text: str | None) -> str:
    return first_non_empty_line(normalize_punishment_text(text))


def normalize_punishment_text(text: str | None) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\ufe0f", "").strip()


def first_non_empty_line(text: str | None) -> str:
    for line in normalize_punishment_text(text).split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def action_from_punishment_type(punishment_type: str | None) -> str | None:
    if punishment_type in {"unban", "unmute", "unwarn"}:
        return "removed"
    if punishment_type in {"ban", "mute", "warn"}:
        return "issued"
    return None


def parse_punishment_date(value: str | None, tz: ZoneInfo) -> datetime | None:
    if not value or not value.strip():
        return None

    normalized = value.strip()
    for fmt in ("%d.%m.%y %H:%M", "%d.%m.%Y %H:%M"):
        try:
            local_dt = datetime.strptime(normalized, fmt).replace(tzinfo=tz)
            return to_utc(local_dt)
        except ValueError:
            continue
    return None


def normalize_punishment_moderator_alias(value: str | None) -> str | None:
    if value is None:
        return None

    alias = value.replace("\r", "\n").split("\n", maxsplit=1)[0].strip()
    alias = re.sub(r"\s+", " ", alias)
    return alias or None


def is_invalid_punishment_moderator_alias(value: str | None) -> bool:
    alias = normalize_punishment_moderator_alias(value)
    if not alias:
        return True
    normalized = normalize_nickname(alias).strip(" :")
    return normalized in INVALID_MODERATOR_ALIAS_LABELS


def is_rule_missing(text: str) -> bool:
    lowered = text.lower()
    if "без пункта" in lowered or "нет пункта" in lowered:
        return True
    return not any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in RULE_PATTERNS)
