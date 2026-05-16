from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram.types import Message

from app.config.loader import PunishmentParserConfig
from app.utils.dates import to_utc
from app.utils.regex import contains_any, first_match, stable_hash


DEFAULT_ID_PATTERNS = [
    r"(?:наказани[ея]|punishment|id)\D{0,12}#?([A-Za-zА-Яа-я0-9_-]+)",
    r"#(\d{3,})",
]
DEFAULT_MODERATOR_PATTERNS = [
    r"(?:модератор|выдал(?:а)?|снял(?:а)?|сотрудник)\s*[:\-]\s*(@?[A-Za-zА-Яа-я0-9_.\-\s]+)",
    r"@([A-Za-z0-9_]{5,32})",
]
DEFAULT_TARGET_PATTERNS = [
    r"(?:игрок|нарушитель|пользователь|ник|target)\s*[:\-]\s*([^\n]+)",
]
DEFAULT_REASON_PATTERNS = [
    r"(?:причина|reason)\s*[:\-]\s*([^\n]+)",
]
DEFAULT_ISSUED_MARKERS = ["выдал", "выдан", "наказал", "наказание", "ban", "mute", "warn", "кик"]
DEFAULT_REMOVED_MARKERS = ["снял", "снято", "разбан", "размут", "unban", "unmute", "амнист"]


@dataclass(slots=True)
class ParsedPunishment:
    event_key: str
    punishment_id: str | None
    action: str
    target: str | None
    reason: str | None
    moderator_alias: str | None
    chat_id: int
    topic_id: int | None
    message_id: int
    punished_at: datetime
    raw_text: str


class PunishmentParser:
    def __init__(self, config: PunishmentParserConfig):
        self.id_patterns = config.ticket_id_patterns or DEFAULT_ID_PATTERNS
        self.moderator_patterns = config.moderator_patterns or DEFAULT_MODERATOR_PATTERNS
        self.required_markers = config.required_markers
        self.issued_markers = config.issued_markers or DEFAULT_ISSUED_MARKERS
        self.removed_markers = config.removed_markers or DEFAULT_REMOVED_MARKERS

    def parse(self, message: Message) -> ParsedPunishment | None:
        text = message.text or message.caption or ""
        if not text.strip():
            return None
        if self.required_markers and not contains_any(self.required_markers, text):
            return None

        action = self._detect_action(text)
        if action is None:
            return None

        punishment_id = first_match(self.id_patterns, text)
        moderator_alias = first_match(self.moderator_patterns, text)
        if not moderator_alias and message.from_user and not message.from_user.is_bot:
            moderator_alias = message.from_user.username or message.from_user.full_name

        event_key = (
            f"punishment:{action}:{message.chat.id}:{punishment_id}"
            if punishment_id
            else self._message_event_key(message, text, action)
        )

        return ParsedPunishment(
            event_key=event_key,
            punishment_id=punishment_id,
            action=action,
            target=first_match(DEFAULT_TARGET_PATTERNS, text),
            reason=first_match(DEFAULT_REASON_PATTERNS, text),
            moderator_alias=moderator_alias,
            chat_id=message.chat.id,
            topic_id=message.message_thread_id,
            message_id=message.message_id,
            punished_at=to_utc(message.date),
            raw_text=text,
        )

    def _detect_action(self, text: str) -> str | None:
        if contains_any(self.removed_markers, text):
            return "removed"
        if contains_any(self.issued_markers, text):
            return "issued"
        return None

    @staticmethod
    def _message_event_key(message: Message, text: str, action: str) -> str:
        fingerprint = stable_hash(message.chat.id, message.message_id, text, action)[:16]
        return f"punishment:{action}:message:{message.chat.id}:{message.message_id}:{fingerprint}"
