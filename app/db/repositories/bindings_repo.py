from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.bindings import ModeratorBinding
from app.db.models.staff import StaffMember
from app.utils.text import clean_username, normalize_alias


class BindingsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_alias(
        self,
        *,
        staff_id: int,
        alias: str,
        telegram_user_id: int | None = None,
        telegram_username: str | None = None,
    ) -> ModeratorBinding:
        alias_normalized = normalize_alias(alias)
        if not alias_normalized:
            raise ValueError("alias cannot be empty")

        binding = await self.session.scalar(
            select(ModeratorBinding).where(ModeratorBinding.alias_normalized == alias_normalized)
        )
        if binding is None:
            binding = ModeratorBinding(
                staff_id=staff_id,
                alias=alias.strip(),
                alias_normalized=alias_normalized,
            )
            self.session.add(binding)

        binding.staff_id = staff_id
        binding.alias = alias.strip()
        binding.alias_normalized = alias_normalized
        binding.telegram_user_id = telegram_user_id
        binding.telegram_username = clean_username(telegram_username)
        await self.session.flush()
        return binding

    async def remove_alias(self, alias: str) -> int:
        alias_normalized = normalize_alias(alias)
        if not alias_normalized:
            return 0
        result = await self.session.execute(
            delete(ModeratorBinding).where(ModeratorBinding.alias_normalized == alias_normalized)
        )
        return result.rowcount or 0

    async def list_bindings(self, query: str | None = None, limit: int = 30) -> list[ModeratorBinding]:
        stmt = (
            select(ModeratorBinding)
            .join(ModeratorBinding.staff)
            .options(selectinload(ModeratorBinding.staff))
            .order_by(StaffMember.nickname, StaffMember.full_name, ModeratorBinding.alias)
            .limit(limit)
        )
        if query:
            normalized = f"%{query.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    ModeratorBinding.alias_normalized.like(normalized),
                    func.lower(StaffMember.full_name).like(normalized),
                    func.lower(StaffMember.nickname).like(normalized),
                    func.lower(StaffMember.real_name).like(normalized),
                    func.lower(ModeratorBinding.telegram_username).like(normalized),
                )
            )
        result = await self.session.scalars(stmt)
        return list(result)

    async def resolve_staff_id(
        self,
        *,
        alias: str | None = None,
        telegram_user_id: int | None = None,
        username: str | None = None,
    ) -> int | None:
        if telegram_user_id:
            staff_id = await self.session.scalar(
                select(StaffMember.id).where(StaffMember.telegram_id == telegram_user_id)
            )
            if staff_id:
                return staff_id

            staff_id = await self.session.scalar(
                select(ModeratorBinding.staff_id).where(ModeratorBinding.telegram_user_id == telegram_user_id)
            )
            if staff_id:
                return staff_id

        username_normalized = clean_username(username)
        if username_normalized:
            staff_id = await self.session.scalar(
                select(StaffMember.id).where(func.lower(StaffMember.username) == username_normalized)
            )
            if staff_id:
                return staff_id

            staff_id = await self.session.scalar(
                select(ModeratorBinding.staff_id).where(
                    or_(
                        ModeratorBinding.alias_normalized == username_normalized,
                        func.lower(ModeratorBinding.telegram_username) == username_normalized,
                    )
                )
            )
            if staff_id:
                return staff_id

        alias_normalized = normalize_alias(alias)
        if alias_normalized:
            staff_id = await self.session.scalar(
                select(ModeratorBinding.staff_id).where(ModeratorBinding.alias_normalized == alias_normalized)
            )
            if staff_id:
                return staff_id

            staff_id = await self.session.scalar(
                select(StaffMember.id).where(
                    or_(
                        func.lower(StaffMember.full_name) == alias_normalized,
                        func.lower(StaffMember.nickname) == alias_normalized,
                        func.lower(StaffMember.real_name) == alias_normalized,
                        func.lower(StaffMember.username) == alias_normalized,
                    )
                )
            )
            if staff_id:
                return staff_id

        return None
