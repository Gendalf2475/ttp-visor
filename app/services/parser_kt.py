from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from aiogram.types import Message

from app.config.loader import ParserRulesConfig
from app.utils.dates import to_utc
from app.utils.regex import contains_any, first_match


DEFAULT_TICKET_PATTERNS = [
    r"(?:кт|контроль|ticket|тикет|заявк[аи])\D{0,12}#?([A-Za-zА-Яа-я0-9_-]+)",
    r"#(\d{3,})",
]
DEFAULT_MODERATOR_PATTERNS = [
    r"(?:проверил(?:а)?|проверяющий|модератор|сотрудник)\s*[:\-]\s*(@?[A-Za-zА-Яа-я0-9_.\-\s]+)",
    r"@([A-Za-z0-9_]{5,32})",
]
DEFAULT_REQUIRED_MARKERS = [
    "беру",
    "беру тикеты",
    "взял тикеты",
    "взяла тикеты",
    "тикеты",
    "кт",
    "проверил",
    "проверила",
    "проверены",
    "проверена",
    "проверен",
]
IGNORE_PATTERNS = [
    re.compile(r"(?i)\bмои\s+тикеты\b"),
]
MODE_MARKER_RE = re.compile(r"(?i)\b(?:polit|полит)[ _-]*[12]\b")
RANGE_RE = re.compile(r"(?<!\d)(\d{1,})\s*-\s*(\d{1,})(?!\d)")
SINGLE_NUMBER_RE = re.compile(r"(?<!\d)\d{2,}(?!\d)")


@dataclass(slots=True)
class KTParseAnalysis:
    matched: bool
    ignored: bool
    ranges: list[str]
    singles: list[int]
    ticket_numbers: list[int]
    raw_range_text: str | None = None
    failure_reason: str | None = None

    @property
    def tickets_count(self) -> int:
        return len(self.ticket_numbers)

    @property
    def ticket_id(self) -> str | None:
        if self.ranges:
            return self.ranges[0]
        if self.singles:
            return str(self.singles[0])
        if self.ticket_numbers:
            return str(self.ticket_numbers[0])
        return None


@dataclass(slots=True)
class ParsedKTCheck:
    event_key: str
    ticket_id: str | None
    tickets_count: int
    ticket_numbers: list[int]
    raw_range_text: str | None
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
        self.required_markers = list(dict.fromkeys([*DEFAULT_REQUIRED_MARKERS, *config.required_markers]))

    def parse(self, message: Message) -> ParsedKTCheck | None:
        text = message.text or message.caption or ""
        analysis = self.analyze_text(text)
        if not analysis.matched:
            return None

        ticket_id = analysis.ticket_id
        moderator_alias = first_match(self.moderator_patterns, text)
        if not moderator_alias and message.from_user:
            moderator_alias = message.from_user.username or message.from_user.full_name

        status = "checked"
        lowered = text.lower()
        if "ошиб" in lowered or "отклон" in lowered:
            status = "rejected"
        elif "прин" in lowered or "ок" in lowered or "✅" in lowered:
            status = "accepted"

        event_key = self._message_event_key(message)

        return ParsedKTCheck(
            event_key=event_key,
            ticket_id=ticket_id,
            tickets_count=analysis.tickets_count,
            ticket_numbers=analysis.ticket_numbers,
            raw_range_text=analysis.raw_range_text,
            status=status,
            moderator_alias=moderator_alias,
            chat_id=message.chat.id,
            topic_id=message.message_thread_id,
            message_id=message.message_id,
            checked_at=to_utc(message.date),
            raw_text=text,
        )

    def analyze_text(self, text: str) -> KTParseAnalysis:
        if not text.strip():
            return KTParseAnalysis(
                matched=False,
                ignored=False,
                ranges=[],
                singles=[],
                ticket_numbers=[],
                failure_reason="empty_text",
            )

        ignored = any(pattern.search(text) for pattern in IGNORE_PATTERNS)
        if ignored:
            return KTParseAnalysis(
                matched=False,
                ignored=True,
                ranges=[],
                singles=[],
                ticket_numbers=[],
                failure_reason="ignored_my_tickets",
            )

        if not contains_any(self.required_markers, text):
            return KTParseAnalysis(
                matched=False,
                ignored=False,
                ranges=[],
                singles=[],
                ticket_numbers=[],
                failure_reason="required_markers_missing",
            )

        cleaned_text = MODE_MARKER_RE.sub(" ", text)
        ranges: list[str] = []
        numbers: list[int] = []
        matched_parts: list[str] = []

        for match in RANGE_RE.finditer(cleaned_text):
            start = int(match.group(1))
            end = int(match.group(2))
            if end < start:
                continue
            ranges.append(f"{start}-{end}")
            matched_parts.append(match.group(0).strip())
            numbers.extend(range(start, end + 1))

        without_ranges = RANGE_RE.sub(" ", cleaned_text)
        singles = [int(match.group(0)) for match in SINGLE_NUMBER_RE.finditer(without_ranges)]
        matched_parts.extend(str(single) for single in singles)
        numbers.extend(singles)

        ticket_numbers = sorted(set(numbers))
        return KTParseAnalysis(
            matched=bool(ticket_numbers),
            ignored=False,
            ranges=ranges,
            singles=sorted(set(singles)),
            ticket_numbers=ticket_numbers,
            raw_range_text=", ".join(matched_parts) if matched_parts else text,
            failure_reason=None if ticket_numbers else "ticket_numbers_missing",
        )

    @staticmethod
    def _message_event_key(message: Message) -> str:
        return f"kt:message:{message.chat.id}:{message.message_id}"
