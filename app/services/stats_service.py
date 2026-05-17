from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.kt_checks import KTCheck
from app.db.models.punishments import Punishment
from app.db.models.staff import StaffMember
from app.db.models.support_tickets import SupportTicket
from app.db.repositories.extra_occupations_repo import ExtraOccupationsRepo
from app.db.repositories.staff_repo import StaffRepo
from app.services.parser_punishments import (
    classify_punishment_type,
    is_invalid_punishment_moderator_alias,
    is_rule_missing,
    normalize_punishment_moderator_alias,
)
from app.utils.dates import Period
from app.utils.text import normalize_nickname


logger = logging.getLogger(__name__)
PUNISHMENT_TYPES = ("ban", "mute", "warn", "unban", "unmute", "unwarn")


@dataclass(slots=True)
class ExtraOccupationView:
    direction: str
    occupation: str
    position: str

    @property
    def short_label(self) -> str:
        return f"{self.occupation} — {self.position}"


@dataclass(slots=True)
class PunishmentBreakdown:
    ban: int = 0
    mute: int = 0
    warn: int = 0
    unban: int = 0
    unmute: int = 0
    unwarn: int = 0
    without_rule: int = 0

    @property
    def issued(self) -> int:
        return self.ban + self.mute + self.warn

    @property
    def removed(self) -> int:
        return self.unban + self.unmute + self.unwarn

    @property
    def total(self) -> int:
        return self.issued + self.removed

    def add(self, punishment_type: str | None, rule_missing: bool) -> None:
        if punishment_type in PUNISHMENT_TYPES:
            setattr(self, punishment_type, getattr(self, punishment_type) + 1)
        if rule_missing and punishment_type in {"ban", "mute", "warn"}:
            self.without_rule += 1

    def merge(self, other: PunishmentBreakdown) -> None:
        for field_name in ("ban", "mute", "warn", "unban", "unmute", "unwarn", "without_rule"):
            setattr(self, field_name, getattr(self, field_name) + getattr(other, field_name))


@dataclass(slots=True)
class ModeratorStats:
    name: str
    key: str
    staff_id: int | None = None
    rank: str | None = None
    support_tickets: int = 0
    kt_checks: int = 0
    punishments: PunishmentBreakdown = field(default_factory=PunishmentBreakdown)
    extra_occupations: list[ExtraOccupationView] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.support_tickets + self.kt_checks + self.punishments.total


@dataclass(slots=True)
class StatsReport:
    period: Period
    rows: list[ModeratorStats]

    @property
    def totals(self) -> ModeratorStats:
        total = ModeratorStats(name="Итого", key="total")
        for row in self.rows:
            total.support_tickets += row.support_tickets
            total.kt_checks += row.kt_checks
            total.punishments.merge(row.punishments)
        return total


class StatsService:
    def __init__(self, ignored_nicknames: list[str] | None = None):
        self.ignored_nickname_keys = {
            key
            for key in (normalize_nickname(nickname) for nickname in (ignored_nicknames or []))
            if key
        }

    async def collect(
        self,
        session: AsyncSession,
        period: Period,
        *,
        show_zero_activity_staff: bool = True,
    ) -> StatsReport:
        buckets: dict[str, ModeratorStats] = {}

        if show_zero_activity_staff:
            for staff in await StaffRepo(session).get_active_members():
                if self._is_ignored_staff(staff):
                    continue
                self._bucket(
                    buckets,
                    staff_id=staff.id,
                    alias=staff.nickname or staff.full_name,
                    staff_nickname=staff.nickname,
                    staff_full_name=staff.full_name,
                    rank=staff.rank,
                )

        await self._collect_support(session, period, buckets)
        await self._collect_kt(session, period, buckets)
        await self._collect_punishments(session, period, buckets)
        await self._enrich_rows(session, buckets)

        rows = sorted(
            buckets.values(),
            key=lambda item: (-item.total, item.name.lower()),
        )
        return StatsReport(period=period, rows=rows)

    async def collect_for_staff(self, session: AsyncSession, period: Period, staff: StaffMember) -> ModeratorStats:
        if self._is_ignored_staff(staff):
            return ModeratorStats(
                name=staff.nickname or staff.full_name,
                key=normalize_nickname(staff.nickname or staff.full_name),
                staff_id=staff.id,
                rank=staff.rank,
            )

        report = await self.collect(session, period, show_zero_activity_staff=True)
        staff_key = normalize_nickname(staff.nickname or staff.full_name)
        for row in report.rows:
            if row.staff_id == staff.id or row.key == staff_key:
                row.staff_id = staff.id
                row.name = staff.nickname or staff.full_name
                row.rank = staff.rank
                return row

        stats = ModeratorStats(
            name=staff.nickname or staff.full_name,
            key=staff_key,
            staff_id=staff.id,
            rank=staff.rank,
        )
        await self._enrich_rows(session, {staff_key: stats})
        return stats

    async def _collect_support(
        self,
        session: AsyncSession,
        period: Period,
        buckets: dict[str, ModeratorStats],
    ) -> None:
        result = await session.execute(
            select(
                SupportTicket.staff_id,
                SupportTicket.moderator_alias,
                StaffMember.nickname,
                StaffMember.full_name,
                StaffMember.rank,
                func.count(),
            )
            .outerjoin(StaffMember, SupportTicket.staff_id == StaffMember.id)
            .where(
                SupportTicket.closed_at >= period.start,
                SupportTicket.closed_at < period.end,
                SupportTicket.is_ignored.is_(False),
            )
            .group_by(
                SupportTicket.staff_id,
                SupportTicket.moderator_alias,
                StaffMember.nickname,
                StaffMember.full_name,
                StaffMember.rank,
            )
        )
        for staff_id, alias, staff_nickname, staff_full_name, rank, count in result.all():
            stats = self._bucket(
                buckets,
                staff_id=staff_id,
                alias=alias,
                staff_nickname=staff_nickname,
                staff_full_name=staff_full_name,
                rank=rank,
            )
            if stats is not None:
                stats.support_tickets += int(count)

    async def _collect_kt(
        self,
        session: AsyncSession,
        period: Period,
        buckets: dict[str, ModeratorStats],
    ) -> None:
        result = await session.execute(
            select(
                KTCheck.staff_id,
                KTCheck.moderator_alias,
                StaffMember.nickname,
                StaffMember.full_name,
                StaffMember.rank,
                func.coalesce(func.sum(func.coalesce(KTCheck.tickets_count, 1)), 0),
            )
            .outerjoin(StaffMember, KTCheck.staff_id == StaffMember.id)
            .where(
                KTCheck.checked_at >= period.start,
                KTCheck.checked_at < period.end,
                KTCheck.is_ignored.is_(False),
            )
            .group_by(
                KTCheck.staff_id,
                KTCheck.moderator_alias,
                StaffMember.nickname,
                StaffMember.full_name,
                StaffMember.rank,
            )
        )
        for staff_id, alias, staff_nickname, staff_full_name, rank, count in result.all():
            stats = self._bucket(
                buckets,
                staff_id=staff_id,
                alias=alias,
                staff_nickname=staff_nickname,
                staff_full_name=staff_full_name,
                rank=rank,
            )
            if stats is not None:
                stats.kt_checks += int(count)

    async def _collect_punishments(
        self,
        session: AsyncSession,
        period: Period,
        buckets: dict[str, ModeratorStats],
    ) -> None:
        result = await session.execute(
            select(
                Punishment.staff_id,
                Punishment.moderator_alias,
                StaffMember.nickname,
                StaffMember.full_name,
                StaffMember.rank,
                Punishment.punishment_type,
                Punishment.rule_missing,
                Punishment.raw_text,
            )
            .outerjoin(StaffMember, Punishment.staff_id == StaffMember.id)
            .where(
                Punishment.punished_at >= period.start,
                Punishment.punished_at < period.end,
                Punishment.is_valid.is_(True),
                Punishment.is_ignored.is_(False),
            )
        )
        for (
            staff_id,
            alias,
            staff_nickname,
            staff_full_name,
            rank,
            punishment_type,
            rule_missing,
            raw_text,
        ) in result.all():
            alias = normalize_punishment_moderator_alias(alias)
            if is_invalid_punishment_moderator_alias(alias):
                continue

            resolved_type = punishment_type or classify_punishment_type(raw_text or "")
            resolved_rule_missing = bool(rule_missing) or is_rule_missing(raw_text or "")
            stats = self._bucket(
                buckets,
                staff_id=staff_id,
                alias=alias,
                staff_nickname=staff_nickname,
                staff_full_name=staff_full_name,
                rank=rank,
            )
            if stats is not None:
                stats.punishments.add(resolved_type, resolved_rule_missing)

    async def _enrich_rows(self, session: AsyncSession, buckets: dict[str, ModeratorStats]) -> None:
        for key, row in list(buckets.items()):
            if self.is_ignored(row.name):
                buckets.pop(key, None)

        rows = list(buckets.values())
        nicknames = {row.name for row in rows if row.name}

        staff_by_key = await StaffRepo(session).get_many_by_nicknames_ci(nicknames)
        staff_found_by_row: dict[int, bool] = {}
        for original_key, row in list(buckets.items()):
            key = normalize_nickname(row.name)
            staff = staff_by_key.get(key)
            staff_found_by_row[id(row)] = staff is not None
            if not staff:
                continue
            if self._is_ignored_staff(staff):
                buckets.pop(original_key, None)
                continue
            row.staff_id = staff.id
            row.name = staff.nickname or staff.full_name
            row.key = normalize_nickname(row.name)
            row.rank = staff.rank

        rows = list(buckets.values())
        enriched_nicknames = {row.name for row in rows if row.name}
        extras_by_key = await ExtraOccupationsRepo(session).get_many_active_by_nicknames_ci(enriched_nicknames)

        logger.info(
            "Stats enrichment: staff_loaded=%s extras_loaded=%s nicknames=%s",
            len(staff_by_key),
            sum(len(items) for items in extras_by_key.values()),
            sorted(enriched_nicknames),
        )

        for row in rows:
            key = normalize_nickname(row.name)
            row.extra_occupations = [
                ExtraOccupationView(
                    direction=extra.direction,
                    occupation=extra.occupation,
                    position=extra.position,
                )
                for extra in extras_by_key.get(key, [])
            ]
            logger.info(
                "Stats enrichment: nickname=%s key=%s staff_found=%s rank=%s extras=%s",
                row.name,
                key,
                staff_found_by_row.get(id(row), False),
                row.rank,
                len(row.extra_occupations),
            )

    def _bucket(
        self,
        buckets: dict[str, ModeratorStats],
        *,
        staff_id: int | None,
        alias: str | None,
        staff_nickname: str | None,
        staff_full_name: str | None,
        rank: str | None,
    ) -> ModeratorStats | None:
        if any(self.is_ignored(value) for value in (staff_nickname, staff_full_name, alias)):
            return None

        display_name = staff_nickname or staff_full_name or alias or "Не распознано"
        key = normalize_nickname(display_name) or (f"staff:{staff_id}" if staff_id is not None else "unknown")

        if key not in buckets:
            buckets[key] = ModeratorStats(
                name=display_name,
                key=key,
                staff_id=staff_id,
                rank=rank,
            )

        stats = buckets[key]
        if staff_id is not None:
            stats.staff_id = staff_id
        if staff_nickname or staff_full_name:
            stats.name = staff_nickname or staff_full_name or stats.name
        if rank:
            stats.rank = rank
        return stats

    def is_ignored(self, nickname: str | None) -> bool:
        return normalize_nickname(nickname) in self.ignored_nickname_keys

    def _is_ignored_staff(self, staff: StaffMember) -> bool:
        return self.is_ignored(staff.nickname) or self.is_ignored(staff.full_name)
