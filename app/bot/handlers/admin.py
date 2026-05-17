from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.loader import AppConfig
from app.db.models.staff import StaffExtraOccupation
from app.db.repositories.extra_occupations_repo import ExtraOccupationsRepo
from app.services.report_service import ReportService
from app.services.staff_sync import StaffSyncService
from app.utils.dates import parse_period_expression
from app.utils.text import html_escape, split_telegram_text


router = Router(name="admin")
router.message.filter(F.chat.type == "private")


HELP_TEXT = """TTP VISOR доступен только супер-админам.

Команды:
/sync_staff - синхронизировать состав из Google Sheets
/sync_extra - синхронизировать доп. занятости
/stats [period] - показать отчёт в личке
/stats_user ник [period] - отчёт по модератору
/stats_direction направление [period] - отчёт по направлению
/report [period] - отправить отчёт в настроенный чат
/extras [ник] - показать доп. занятости
/staff_find текст - найти модератора
/bind staff_id alias [telegram_user_id] - привязать алиас к модератору
/unbind alias - удалить привязку
/bindings [текст] - показать привязки

Периоды:
week, month/current_month, prev_month/previous_month, prev2_month/two_months_ago
или даты: 2026-05-01 2026-05-16 / 01.05.2026 16.05.2026
"""


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("TTP VISOR на связи. /help покажет команды.")


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("sync_staff"))
async def sync_staff(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    staff_sync_service: StaffSyncService,
) -> None:
    status = await message.answer("Синхронизирую состав из Google Sheets...")
    async with session_factory() as session:
        result = await staff_sync_service.sync(session)
    await status.edit_text(
        "Синхронизация завершена:\n"
        f"получено: {result.fetched}\n"
        f"создано: {result.created}\n"
        f"обновлено: {result.updated}\n"
        f"деактивировано: {result.deactivated}"
        + (
            "\n\nДоп. занятости:\n"
            f"получено: {result.extra.fetched}\n"
            f"создано: {result.extra.created}\n"
            f"обновлено: {result.extra.updated}\n"
            f"активировано снова: {result.extra.reactivated}\n"
            f"деактивировано: {result.extra.deactivated}"
            if result.extra
            else ""
        )
    )


@router.message(Command("sync_extra"))
async def sync_extra(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    staff_sync_service: StaffSyncService,
) -> None:
    status = await message.answer("Синхронизирую доп. занятости из Google Sheets...")
    async with session_factory() as session:
        result = await staff_sync_service.sync_extra(session)
    await status.edit_text(
        "Синхронизация доп. занятостей завершена:\n"
        f"получено: {result.fetched}\n"
        f"создано: {result.created}\n"
        f"обновлено: {result.updated}\n"
        f"активировано снова: {result.reactivated}\n"
        f"деактивировано: {result.deactivated}"
    )


@router.message(Command("report"))
async def send_report(
    message: Message,
    command: CommandObject,
    bot: Bot,
    app_config: AppConfig,
    report_service: ReportService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    try:
        period = parse_period_expression(app_config.timezone, command.args)
    except ValueError as exc:
        await message.answer(f"Не понял период: {exc}")
        return
    try:
        await report_service.send_report(bot, session_factory, period)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await message.answer("Отчёт отправлен в настроенный чат.")


@router.message(Command("extras"))
async def extras(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    nickname = (command.args or "").strip() or None
    async with session_factory() as session:
        rows = await ExtraOccupationsRepo(session).list_active(nickname)

    if nickname:
        text = _format_extras_for_nickname(nickname, rows)
    else:
        text = _format_all_extras(rows)

    for chunk in split_telegram_text(text):
        await message.answer(chunk)


def _format_all_extras(rows: list[StaffExtraOccupation]) -> str:
    if not rows:
        return "Активных доп. занятостей нет."

    grouped = _group_extras(rows)
    lines = ["💼 <b>Доп. занятости</b>"]
    for direction, items in grouped.items():
        lines.extend(["", f"{_direction_icon(direction)} <b>{html_escape(direction)}:</b>"])
        for item in items:
            lines.append(
                f"{html_escape(item.nickname)} — {html_escape(item.occupation)}, {html_escape(item.position)}"
            )
    return "\n".join(lines)


def _format_extras_for_nickname(nickname: str, rows: list[StaffExtraOccupation]) -> str:
    if not rows:
        return "У модератора нет активных доп. занятостей."

    grouped = _group_extras(rows)
    lines = [f"💼 <b>Доп. занятости: {html_escape(nickname)}</b>"]
    for direction, items in grouped.items():
        lines.extend(["", f"{_direction_icon(direction)} <b>{html_escape(direction)}:</b>"])
        for item in items:
            lines.append(f"{html_escape(item.occupation)} — {html_escape(item.position)}")
    return "\n".join(lines)


def _group_extras(rows: list[StaffExtraOccupation]) -> dict[str, list[StaffExtraOccupation]]:
    grouped: dict[str, list[StaffExtraOccupation]] = {}
    for row in rows:
        grouped.setdefault(row.direction, []).append(row)
    return grouped


def _direction_icon(direction: str) -> str:
    lowered = direction.lower()
    if "тикет" in lowered:
        return "🧾"
    if "соц" in lowered:
        return "🌐"
    if "поддерж" in lowered:
        return "🎫"
    return "💼"
