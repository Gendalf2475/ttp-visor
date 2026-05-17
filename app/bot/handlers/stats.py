from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.loader import AppConfig
from app.services.report_service import ReportService
from app.utils.dates import parse_period_expression
from app.utils.messages import safe_answer


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
        await safe_answer(message, f"Не понял период: {exc}")
        return
    async with session_factory() as session:
        text = await report_service.build_report_text(session, period)

    await safe_answer(message, text)


@router.message(Command("stats_full"))
async def stats_full(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    report_service: ReportService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    try:
        period = parse_period_expression(app_config.timezone, command.args)
    except ValueError as exc:
        await safe_answer(message, f"Не понял период: {exc}")
        return
    async with session_factory() as session:
        text = await report_service.build_full_report_text(session, period)

    await safe_answer(message, text)


@router.message(Command("stats_user"))
async def stats_user(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    report_service: ReportService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    args = (command.args or "").strip().split()
    if not args:
        await safe_answer(message, "Использование: /stats_user [ник] [period]")
        return

    nickname = args[0]
    period_expression = " ".join(args[1:]) if len(args) > 1 else None
    try:
        period = parse_period_expression(app_config.timezone, period_expression)
    except ValueError as exc:
        await safe_answer(message, f"Не понял период: {exc}")
        return

    async with session_factory() as session:
        text = await report_service.build_user_report_text(session, nickname, period)

    await safe_answer(message, text)


@router.message(Command("stats_direction"))
async def stats_direction(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    report_service: ReportService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    args = (command.args or "").strip().split()
    if not args:
        await safe_answer(message, "Использование: /stats_direction [направление] [period]")
        return

    direction = args[0]
    period_expression = " ".join(args[1:]) if len(args) > 1 else None
    try:
        period = parse_period_expression(app_config.timezone, period_expression)
    except ValueError as exc:
        await safe_answer(message, f"Не понял период: {exc}")
        return

    async with session_factory() as session:
        text = await report_service.build_direction_report_text(session, direction, period)

    await safe_answer(message, text)
