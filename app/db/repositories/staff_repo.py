from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.staff import StaffActivePeriod, StaffMember
from app.utils.text import clean_username, normalize_alias, normalize_nickname


@dataclass(slots=True)
class StaffUpsert:
    nickname: str
    external_key: str | None = None
    rank: str | None = None
    mentor: str | None = None
    real_name: str | None = None
    telegram_raw: str | None = None
    telegram_username: str | None = None
    telegram_id: int | None = None
    is_active: bool = True
    aliases: list[str] = field(default_factory=list)


class StaffRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, staff_id: int) -> StaffMember | None:
        return await self.session.get(StaffMember, staff_id)

    async def list_active(self) -> list[StaffMember]:
        return await self.get_active_members()

    async def get_active_members(self) -> list[StaffMember]:
        result = await self.session.scalars(
            select(StaffMember)
            .where(StaffMember.is_active.is_(True))
            .order_by(StaffMember.nickname, StaffMember.full_name)
        )
        return list(result)

    async def get_many_by_nicknames_ci(self, nicknames: set[str] | list[str]) -> dict[str, StaffMember]:
        normalized = {normalize_nickname(nickname) for nickname in nicknames}
        normalized.discard("")
        if not normalized:
            return {}

        result = await self.session.scalars(select(StaffMember).order_by(StaffMember.is_active.desc()))
        by_key: dict[str, StaffMember] = {}
        for staff in result:
            for value in (staff.nickname, staff.full_name):
                key = normalize_nickname(value)
                if key and key in normalized and key not in by_key:
                    by_key[key] = staff
        return by_key

    async def get_by_nickname_ci(self, nickname: str) -> StaffMember | None:
        return (await self.get_many_by_nicknames_ci([nickname])).get(normalize_nickname(nickname))

    async def search(self, query: str, limit: int = 10) -> list[StaffMember]:
        normalized = f"%{query.strip().lower()}%"
        result = await self.session.scalars(
            select(StaffMember)
            .where(
                or_(
                    func.lower(StaffMember.full_name).like(normalized),
                    func.lower(StaffMember.nickname).like(normalized),
                    func.lower(StaffMember.real_name).like(normalized),
                    func.lower(StaffMember.username).like(normalized),
                    cast(StaffMember.telegram_id, String).like(normalized),
                )
            )
            .order_by(StaffMember.is_active.desc(), StaffMember.nickname, StaffMember.full_name)
            .limit(limit)
        )
        return list(result)

    async def find_by_nickname(self, nickname: str) -> StaffMember | None:
        return await self.get_by_nickname_ci(nickname)

    async def upsert(self, data: StaffUpsert, synced_at: datetime) -> tuple[StaffMember, bool]:
        staff = await self._find_existing(data)
        created = False

        if staff is None:
            staff = StaffMember(full_name=data.nickname)
            self.session.add(staff)
            created = True

        staff.external_key = data.external_key
        staff.full_name = data.nickname
        staff.nickname = data.nickname
        staff.rank = data.rank
        staff.mentor = data.mentor
        staff.real_name = data.real_name
        staff.username = clean_username(data.telegram_username)
        staff.telegram_raw = data.telegram_raw
        staff.telegram_id = data.telegram_id
        staff.role = data.rank
        staff.is_active = data.is_active
        staff.deactivated_at = None if data.is_active else synced_at
        staff.synced_at = synced_at

        await self.session.flush()
        await self._sync_active_period(staff, data.is_active, synced_at)
        return staff, created

    async def deactivate_matching(self, data: StaffUpsert, synced_at: datetime) -> int:
        staff = await self._find_existing(data)
        if staff is None:
            return 0

        was_active = staff.is_active
        staff.is_active = False
        staff.deactivated_at = synced_at
        staff.synced_at = synced_at

        await self.session.flush()
        await self._sync_active_period(staff, False, synced_at)
        return 1 if was_active else 0

    async def deactivate_missing_external_keys(self, external_keys: set[str], synced_at: datetime) -> int:
        conditions = [
            StaffMember.external_key.is_not(None),
            StaffMember.is_active.is_(True),
        ]
        if external_keys:
            conditions.append(StaffMember.external_key.not_in(external_keys))

        staff_ids = await self.session.scalars(
            select(StaffMember.id).where(*conditions)
        )
        ids = list(staff_ids)
        if not ids:
            return 0

        result = await self.session.execute(
            update(StaffMember)
            .where(StaffMember.id.in_(ids))
            .values(is_active=False, deactivated_at=synced_at, synced_at=synced_at)
        )

        await self.session.execute(
            update(StaffActivePeriod)
            .where(StaffActivePeriod.staff_id.in_(ids), StaffActivePeriod.ended_at.is_(None))
            .values(ended_at=synced_at)
        )
        return result.rowcount or 0

    async def _sync_active_period(self, staff: StaffMember, is_active: bool, synced_at: datetime) -> None:
        open_period = await self.session.scalar(
            select(StaffActivePeriod).where(
                StaffActivePeriod.staff_id == staff.id,
                StaffActivePeriod.ended_at.is_(None),
            )
        )

        if is_active and open_period is None:
            self.session.add(StaffActivePeriod(staff_id=staff.id, started_at=synced_at))
        elif not is_active and open_period is not None:
            open_period.ended_at = synced_at

    async def _find_existing(self, data: StaffUpsert) -> StaffMember | None:
        if data.external_key:
            result = await self.session.scalar(
                select(StaffMember).where(StaffMember.external_key == data.external_key)
            )
            if result is not None:
                return result

        if data.telegram_id:
            result = await self.session.scalar(
                select(StaffMember).where(StaffMember.telegram_id == data.telegram_id)
            )
            if result is not None:
                return result

        username = clean_username(data.telegram_username)
        if username:
            result = await self.session.scalar(
                select(StaffMember).where(func.lower(StaffMember.username) == username)
            )
            if result is not None:
                return result

        normalized_nickname = normalize_alias(data.nickname)
        if normalized_nickname:
            result = await self.session.scalars(select(StaffMember))
            for staff in result:
                if normalized_nickname in {
                    normalize_nickname(staff.nickname),
                    normalize_nickname(staff.full_name),
                }:
                    return staff

        return None
