from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.kt_checks import KTCheck
from app.db.models.punishments import Punishment
from app.db.models.staff import StaffMember
from app.db.models.support_tickets import SupportTicket
from app.utils.dates import Period
from app.utils.text import normalize_alias


@dataclass(slots=True)
class ModeratorStats:
    name: str
    staff_id: int | None = None
    support_tickets: int = 0
    kt_checks: int = 0
    punishments_issued: int = 0
    punishments_removed: int = 0

    @property
    def total(self) -> int:
        return self.support_tickets + self.kt_checks + self.punishments_issued + self.punishments_removed


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
            total.punishments_issued += row.punishments_issued
            total.punishments_removed += row.punishments_removed
        return total


class StatsService:
    async def collect(self, session: AsyncSession, period: Period) -> StatsReport:
        buckets: dict[tuple[str, str | int], ModeratorStats] = {}

        await self._collect_support(session, period, buckets)
        await self._collect_kt(session, period, buckets)
        await self._collect_punishments(session, period, buckets)
        await self._attach_staff_names(session, buckets)

        rows = sorted(
            buckets.values(),
            key=lambda item: (-item.total, item.name.lower()),
        )
        return StatsReport(period=period, rows=rows)

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
            select(Punishment.staff_id, Punishment.moderator_alias, Punishment.action, func.count())
            .where(Punishment.punished_at >= period.start, Punishment.punished_at < period.end)
            .group_by(Punishment.staff_id, Punishment.moderator_alias, Punishment.action)
        )
        for staff_id, alias, action, count in result.all():
            stats = self._bucket(buckets, staff_id, alias)
            if action == "removed":
                stats.punishments_removed += int(count)
            else:
                stats.punishments_issued += int(count)

    async def _attach_staff_names(
        self,
        session: AsyncSession,
        buckets: dict[tuple[str, str | int], ModeratorStats],
    ) -> None:
        staff_ids = [stats.staff_id for stats in buckets.values() if stats.staff_id is not None]
        if not staff_ids:
            return
        result = await session.execute(
            select(StaffMember.id, StaffMember.nickname, StaffMember.full_name).where(StaffMember.id.in_(staff_ids))
        )
        names = {staff_id: nickname or full_name for staff_id, nickname, full_name in result.all()}
        for stats in buckets.values():
            if stats.staff_id in names:
                stats.name = names[stats.staff_id]

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
