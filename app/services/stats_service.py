from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.kt_checks import KTCheck
from app.db.models.punishments import Punishment
from app.db.models.staff import StaffMember
from app.db.models.support_tickets import SupportTicket
from app.db.repositories.extra_occupations_repo import ExtraOccupationsRepo
from app.services.parser_punishments import classify_punishment_type, is_rule_missing
from app.utils.dates import Period
from app.utils.text import normalize_alias


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
        total = ModeratorStats(name="Итого")
        for row in self.rows:
            total.support_tickets += row.support_tickets
            total.kt_checks += row.kt_checks
            total.punishments.merge(row.punishments)
        return total


class StatsService:
    async def collect(self, session: AsyncSession, period: Period) -> StatsReport:
        buckets: dict[tuple[str, str | int], ModeratorStats] = {}

        await self._collect_support(session, period, buckets)
        await self._collect_kt(session, period, buckets)
        await self._collect_punishments(session, period, buckets)
        await self._attach_staff_details(session, buckets)

        rows = sorted(
            buckets.values(),
            key=lambda item: (-item.total, item.name.lower()),
        )
        return StatsReport(period=period, rows=rows)

    async def collect_for_staff(self, session: AsyncSession, period: Period, staff: StaffMember) -> ModeratorStats:
        report = await self.collect(session, period)
        for row in report.rows:
            if row.staff_id == staff.id or row.name.lower() == (staff.nickname or staff.full_name).lower():
                row.staff_id = staff.id
                row.rank = staff.rank
                return row

        stats = ModeratorStats(
            name=staff.nickname or staff.full_name,
            staff_id=staff.id,
            rank=staff.rank,
        )
        await self._attach_extras_for_rows(session, [stats])
        return stats

    async def _collect_support(
        self,
        session: AsyncSession,
        period: Period,
        buckets: dict[tuple[str, str | int], ModeratorStats],
    ) -> None:
        result = await session.execute(
            select(SupportTicket.staff_id, SupportTicket.moderator_alias, func.count())
            .where(SupportTicket.closed_at >= period.start, SupportTicket.closed_at < period.end)
            .group_by(SupportTicket.staff_id, SupportTicket.moderator_alias)
        )
        for staff_id, alias, count in result.all():
            self._bucket(buckets, staff_id, alias).support_tickets += int(count)

    async def _collect_kt(
        self,
        session: AsyncSession,
        period: Period,
        buckets: dict[tuple[str, str | int], ModeratorStats],
    ) -> None:
        result = await session.execute(
            select(KTCheck.staff_id, KTCheck.moderator_alias, func.count())
            .where(KTCheck.checked_at >= period.start, KTCheck.checked_at < period.end)
            .group_by(KTCheck.staff_id, KTCheck.moderator_alias)
        )
        for staff_id, alias, count in result.all():
            self._bucket(buckets, staff_id, alias).kt_checks += int(count)

    async def _collect_punishments(
        self,
        session: AsyncSession,
        period: Period,
        buckets: dict[tuple[str, str | int], ModeratorStats],
    ) -> None:
        result = await session.execute(
            select(
                Punishment.staff_id,
                Punishment.moderator_alias,
                Punishment.punishment_type,
                Punishment.rule_missing,
                Punishment.raw_text,
            ).where(Punishment.punished_at >= period.start, Punishment.punished_at < period.end)
        )
        for staff_id, alias, punishment_type, rule_missing, raw_text in result.all():
            resolved_type = punishment_type or classify_punishment_type(raw_text or "")
            resolved_rule_missing = bool(rule_missing) or is_rule_missing(raw_text or "")
            self._bucket(buckets, staff_id, alias).punishments.add(resolved_type, resolved_rule_missing)

    async def _attach_staff_details(
        self,
        session: AsyncSession,
        buckets: dict[tuple[str, str | int], ModeratorStats],
    ) -> None:
        staff_ids = [stats.staff_id for stats in buckets.values() if stats.staff_id is not None]
        if staff_ids:
            result = await session.execute(
                select(StaffMember.id, StaffMember.nickname, StaffMember.full_name, StaffMember.rank).where(
                    StaffMember.id.in_(staff_ids)
                )
            )
            details = {
                staff_id: (nickname or full_name, rank)
                for staff_id, nickname, full_name, rank in result.all()
            }
            for stats in buckets.values():
                if stats.staff_id in details:
                    stats.name, stats.rank = details[stats.staff_id]

        await self._attach_extras_for_rows(session, list(buckets.values()))

    async def _attach_extras_for_rows(self, session: AsyncSession, rows: list[ModeratorStats]) -> None:
        extras = await ExtraOccupationsRepo(session).list_active_for_nicknames([row.name for row in rows])
        for row in rows:
            row.extra_occupations = [
                ExtraOccupationView(
                    direction=extra.direction,
                    occupation=extra.occupation,
                    position=extra.position,
                )
                for extra in extras.get(row.name.lower(), [])
            ]

    def _bucket(
        self,
        buckets: dict[tuple[str, str | int], ModeratorStats],
        staff_id: int | None,
        alias: str | None,
    ) -> ModeratorStats:
        if staff_id is not None:
            key: tuple[str, str | int] = ("staff", staff_id)
            name = alias or f"staff:{staff_id}"
        else:
            alias_key = normalize_alias(alias) or "unknown"
            key = ("alias", alias_key)
            name = alias or "Не распознано"

        if key not in buckets:
            buckets[key] = ModeratorStats(name=name, staff_id=staff_id)
        return buckets[key]
