from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.loader import AppConfig
from app.services.report_service import ReportService
from app.utils.dates import parse_period_expression
from app.utils.text import split_telegram_text


router = Router(name="stats")
router.message.filter(F.chat.type == "private")


@router.message(Command("stats"))
async def stats(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    report_service: ReportService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    try:
        period = parse_period_expression(app_config.timezone, command.args)
    except ValueError as exc:
        await message.answer(f"Не понял период: {exc}")
        return
    async with session_factory() as session:
        text = await report_service.build_report_text(session, period)

    for chunk in split_telegram_text(text):
        await message.answer(chunk)
