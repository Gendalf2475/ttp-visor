from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories.bindings_repo import BindingsRepo
from app.db.repositories.staff_repo import StaffRepo
from app.utils.text import html_escape


router = Router(name="bindings")
router.message.filter(F.chat.type == "private")


@router.message(Command("staff_find"))
async def staff_find(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer("Использование: /staff_find текст")
        return

    async with session_factory() as session:
        rows = await StaffRepo(session).search(query)

    if not rows:
        await message.answer("Ничего не найдено.")
        return

    lines = ["Найденные модераторы:"]
    for staff in rows:
        username = f" @{staff.username}" if staff.username else ""
        rank = f", {staff.rank}" if staff.rank else ""
        active = "active" if staff.is_active else "inactive"
        display_name = staff.nickname or staff.full_name
        lines.append(f"{staff.id}: {html_escape(display_name)}{username} ({active}{rank})")
    await message.answer("\n".join(lines))


@router.message(Command("bind"))
async def bind_alias(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    args = (command.args or "").strip()
    if not args or len(args.split(maxsplit=1)) != 2:
        await message.answer("Использование: /bind staff_id alias [telegram_user_id]")
        return

    staff_id_raw, alias_raw = args.split(maxsplit=1)
    if not staff_id_raw.isdigit():
        await message.answer("staff_id должен быть числом. Найти его можно через /staff_find.")
        return

    alias_parts = alias_raw.rsplit(maxsplit=1)
    telegram_user_id: int | None = None
    alias = alias_raw
    if len(alias_parts) == 2 and alias_parts[1].isdigit():
        alias = alias_parts[0]
        telegram_user_id = int(alias_parts[1])

    async with session_factory() as session:
        staff = await StaffRepo(session).get(int(staff_id_raw))
        if staff is None:
            await message.answer("Модератор с таким staff_id не найден.")
            return
        binding = await BindingsRepo(session).upsert_alias(
            staff_id=staff.id,
            alias=alias,
            telegram_user_id=telegram_user_id,
            telegram_username=staff.username,
        )
        await session.commit()

    tail = f" с telegram_user_id={telegram_user_id}" if telegram_user_id else ""
    await message.answer(
        f"Алиас {html_escape(binding.alias)} привязан к {html_escape(staff.nickname or staff.full_name)}{tail}."
    )


@router.message(Command("unbind"))
async def unbind_alias(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alias = (command.args or "").strip()
    if not alias:
        await message.answer("Использование: /unbind alias")
        return

    async with session_factory() as session:
        removed = await BindingsRepo(session).remove_alias(alias)
        await session.commit()

    await message.answer("Привязка удалена." if removed else "Такой привязки не было.")


@router.message(Command("bindings"))
async def bindings(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    query = (command.args or "").strip() or None
    async with session_factory() as session:
        rows = await BindingsRepo(session).list_bindings(query)

    if not rows:
        await message.answer("Привязок не найдено.")
        return

    lines = ["Привязки:"]
    for binding in rows:
        username = f" @{binding.telegram_username}" if binding.telegram_username else ""
        lines.append(
            f"{html_escape(binding.alias)} -> {html_escape(binding.staff.nickname or binding.staff.full_name)}"
            f" [staff_id={binding.staff_id}]{username}"
        )
    await message.answer("\n".join(lines))
