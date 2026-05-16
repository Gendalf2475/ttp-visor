from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram.types import Message

from app.config.loader import ParserRulesConfig
from app.utils.dates import to_utc
from app.utils.regex import contains_any, first_match, stable_hash


DEFAULT_TICKET_PATTERNS = [
    r"(?:кт|контроль|ticket|тикет|заявк[аи])\D{0,12}#?([A-Za-zА-Яа-я0-9_-]+)",
    r"#(\d{3,})",
]
DEFAULT_MODERATOR_PATTERNS = [
    r"(?:проверил(?:а)?|проверяющий|модератор|сотрудник)\s*[:\-]\s*(@?[A-Za-zА-Яа-я0-9_.\-\s]+)",
    r"@([A-Za-z0-9_]{5,32})",
]
DEFAULT_REQUIRED_MARKERS = ["кт", "контроль", "проверил", "проверена", "проверен"]


@dataclass(slots=True)
class ParsedKTCheck:
    event_key: str
    ticket_id: str | None
    status: str | None
    moderator_alias: str | None
    chat_id: int
    topic_id: int | None
    message_id: int
    checked_at: datetime
    raw_text: str


class KTParser:
    def __init__(self, config: ParserRulesConfig):
        self.ticket_id_patterns = config.ticket_id_patterns or DEFAULT_TICKET_PATTERNS
        self.moderator_patterns = config.moderator_patterns or DEFAULT_MODERATOR_PATTERNS
        self.required_markers = config.required_markers or DEFAULT_REQUIRED_MARKERS

    def parse(self, message: Message) -> ParsedKTCheck | None:
        text = message.text or message.caption or ""
        if not text.strip() or not contains_any(self.required_markers, text):
            return None

        ticket_id = first_match(self.ticket_id_patterns, text)
        moderator_alias = first_match(self.moderator_patterns, text)
        if not moderator_alias and message.from_user:
            moderator_alias = message.from_user.username or message.from_user.full_name

        status = "checked"
        lowered = text.lower()
        if "ошиб" in lowered or "отклон" in lowered:
            status = "rejected"
        elif "прин" in lowered or "ок" in lowered or "✅" in lowered:
            status = "accepted"

        event_key = f"kt:ticket:{message.chat.id}:{ticket_id}" if ticket_id else self._message_event_key(message, text)

        return ParsedKTCheck(
            event_key=event_key,
            ticket_id=ticket_id,
            status=status,
            moderator_alias=moderator_alias,
            chat_id=message.chat.id,
            topic_id=message.message_thread_id,
            message_id=message.message_id,
            checked_at=to_utc(message.date),
            raw_text=text,
        )

    @staticmethod
    def _message_event_key(message: Message, text: str) -> str:
        fingerprint = stable_hash(message.chat.id, message.message_id, text)[:16]
        return f"kt:message:{message.chat.id}:{message.message_id}:{fingerprint}"
