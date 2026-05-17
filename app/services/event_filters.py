from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import FiltersConfig
from app.db.models.kt_checks import KTCheck
from app.db.models.punishments import Punishment
from app.db.models.support_tickets import SupportTicket


EventKind = Literal["punishment", "support", "kt"]
EVENT_KIND_ALIASES = {
    "punishment": "punishment",
    "punishments": "punishment",
    "наказания": "punishment",
    "support": "support",
    "tp": "support",
    "тп": "support",
    "поддержка": "support",
    "kt": "kt",
    "кт": "kt",
    "checks": "kt",
}
EVENT_MODELS = {
    "punishment": Punishment,
    "support": SupportTicket,
    "kt": KTCheck,
}


@dataclass(slots=True)
class EventFilterMatch:
    is_ignored: bool
    ignore_reason: str | None = None


@dataclass(slots=True)
class ApplyFiltersResult:
    punishments: int = 0
    support: int = 0
    kt: int = 0


@dataclass(slots=True)
class IgnoredEventView:
    kind: EventKind
    id: int
    moderator_alias: str | None
    summary: str
    ignore_reason: str | None
    created_at: datetime


class EventFilter:
    def __init__(self, config: FiltersConfig):
        self.ignore_reasons = _normalize_patterns(config.ignore_reasons)
        self.ignore_targets = _normalize_patterns(config.ignore_targets)

    def evaluate_punishment(
        self,
        *,
        reason: str | None,
        target: str | None,
        raw_text: str | None = None,
    ) -> EventFilterMatch:
        reason_match = self._match_contains(reason, self.ignore_reasons)
        if reason_match:
            return EventFilterMatch(True, f"reason matched: {reason_match}")

        target_match = self._match_contains(target, self.ignore_targets)
        if target_match:
            return EventFilterMatch(True, f"target matched: {target_match}")

        raw_match = self.evaluate_raw_text(raw_text)
        if raw_match.is_ignored:
            return raw_match

        return EventFilterMatch(False)

    def evaluate_raw_text(self, raw_text: str | None) -> EventFilterMatch:
        reason_match = self._match_contains(raw_text, self.ignore_reasons)
        if reason_match:
            return EventFilterMatch(True, f"raw_text matched: {reason_match}")

        target_match = self._match_contains(raw_text, self.ignore_targets)
        if target_match:
            return EventFilterMatch(True, f"raw_text matched: {target_match}")

        return EventFilterMatch(False)

    async def apply_existing(self, session: AsyncSession) -> ApplyFiltersResult:
        result = ApplyFiltersResult()

        punishments = list(await session.scalars(select(Punishment)))
        for row in punishments:
            match = self.evaluate_punishment(reason=row.reason, target=row.target, raw_text=row.raw_text)
            if match.is_ignored and not row.is_ignored:
                row.is_ignored = True
                row.ignore_reason = match.ignore_reason
                result.punishments += 1

        support_rows = list(await session.scalars(select(SupportTicket)))
        for row in support_rows:
            match = self.evaluate_raw_text(row.raw_text)
            if match.is_ignored and not row.is_ignored:
                row.is_ignored = True
                row.ignore_reason = match.ignore_reason
                result.support += 1

        kt_rows = list(await session.scalars(select(KTCheck)))
        for row in kt_rows:
            match = self.evaluate_raw_text(row.raw_text)
            if match.is_ignored and not row.is_ignored:
                row.is_ignored = True
                row.ignore_reason = match.ignore_reason
                result.kt += 1

        await session.flush()
        return result

    async def list_ignored(
        self,
        session: AsyncSession,
        kind: EventKind | None = None,
        *,
        limit: int = 20,
    ) -> list[IgnoredEventView]:
        kinds: tuple[EventKind, ...] = (kind,) if kind else ("punishment", "support", "kt")
        rows: list[IgnoredEventView] = []
        per_kind_limit = limit if kind else limit
        for item_kind in kinds:
            model = EVENT_MODELS[item_kind]
            result = await session.scalars(
                select(model)
                .where(model.is_ignored.is_(True))
                .order_by(model.created_at.desc())
                .limit(per_kind_limit)
            )
            rows.extend(_event_view(item_kind, row) for row in result)
        return sorted(rows, key=lambda row: row.created_at, reverse=True)[:limit]

    async def set_ignored(
        self,
        session: AsyncSession,
        kind: EventKind,
        event_id: int,
        *,
        is_ignored: bool,
        ignore_reason: str | None,
    ) -> bool:
        model = EVENT_MODELS[kind]
        row = await session.get(model, event_id)
        if row is None:
            return False
        row.is_ignored = is_ignored
        row.ignore_reason = ignore_reason if is_ignored else None
        await session.flush()
        return True

    @staticmethod
    def _match_contains(value: str | None, patterns: list[str]) -> str | None:
        if not value:
            return None
        normalized_value = value.strip().casefold()
        if not normalized_value:
            return None
        for pattern in patterns:
            if pattern and pattern in normalized_value:
                return pattern
        return None


def normalize_event_kind(value: str | None) -> EventKind | None:
    if not value:
        return None
    return EVENT_KIND_ALIASES.get(value.strip().casefold())


def _normalize_patterns(values: list[str]) -> list[str]:
    return [value.strip().casefold() for value in values if value and value.strip()]


def _event_view(kind: EventKind, row: object) -> IgnoredEventView:
    if kind == "punishment":
        return IgnoredEventView(
            kind=kind,
            id=row.id,
            moderator_alias=row.moderator_alias,
            summary=f"{row.punishment_type or 'unknown'} — reason: {row.reason or 'none'} — target: {row.target or 'none'}",
            ignore_reason=row.ignore_reason,
            created_at=row.created_at,
        )
    if kind == "support":
        return IgnoredEventView(
            kind=kind,
            id=row.id,
            moderator_alias=row.moderator_alias,
            summary=f"ticket: {row.ticket_id or 'none'}",
            ignore_reason=row.ignore_reason,
            created_at=row.created_at,
        )
    return IgnoredEventView(
        kind=kind,
        id=row.id,
        moderator_alias=row.moderator_alias,
        summary=f"{row.tickets_count or 1} тикетов",
        ignore_reason=row.ignore_reason,
        created_at=row.created_at,
    )
