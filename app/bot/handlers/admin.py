from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.loader import AppConfig
from app.services.report_service import ReportService
from app.services.staff_sync import StaffSyncService
from app.utils.dates import parse_period_expression


router = Router(name="admin")
router.message.filter(F.chat.type == "private")


HELP_TEXT = """TTP VISOR доступен только супер-админам.

Команды:
/sync_staff - синхронизировать состав из Google Sheets
/stats [period] - показать отчёт в личке
/report [period] - отправить отчёт в настроенный чат
/staff_find текст - найти модератора
/bind staff_id alias [telegram_user_id] - привязать алиас к модератору
/unbind alias - удалить привязку
/bindings [текст] - показать привязки

Периоды:
week, current_month, previous_month, two_months_ago
или даты: 2026-05-01 2026-05-16
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
