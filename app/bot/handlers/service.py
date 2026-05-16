from __future__ import annotations

import logging
from dataclasses import asdict

from aiogram import F, Router
from aiogram.types import Message, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.loader import AppConfig
from app.db.repositories.bindings_repo import BindingsRepo
from app.db.repositories.kt_repo import KTRepo
from app.db.repositories.punishments_repo import PunishmentsRepo
from app.db.repositories.support_repo import SupportRepo
from app.services.parser_kt import KTParser, ParsedKTCheck
from app.services.parser_punishments import ParsedPunishment, PunishmentParser
from app.services.parser_support import ParsedSupportTicket, SupportParser
from app.utils.telegram_sources import message_matches_source
from app.utils.text import clean_username


logger = logging.getLogger(__name__)
router = Router(name="service")
router.message.filter(F.chat.type.in_({"group", "supergroup", "channel"}))
router.edited_message.filter(F.chat.type.in_({"group", "supergroup", "channel"}))


@router.message()
async def collect_message(
    message: Message,
    app_config: AppConfig,
    session_factory: async_sessionmaker[AsyncSession],
    support_parser: SupportParser,
    kt_parser: KTParser,
    punishment_parser: PunishmentParser,
) -> None:
    await _collect(message, app_config, session_factory, support_parser, kt_parser, punishment_parser)


@router.edited_message()
async def collect_edited_message(
    message: Message,
    app_config: AppConfig,
    session_factory: async_sessionmaker[AsyncSession],
    support_parser: SupportParser,
    kt_parser: KTParser,
    punishment_parser: PunishmentParser,
) -> None:
    await _collect(message, app_config, session_factory, support_parser, kt_parser, punishment_parser)


async def _collect(
    message: Message,
    app_config: AppConfig,
    session_factory: async_sessionmaker[AsyncSession],
    support_parser: SupportParser,
    kt_parser: KTParser,
    punishment_parser: PunishmentParser,
) -> None:
    kind = _source_kind(message, app_config)
    if kind is None:
        return

    parsed: ParsedSupportTicket | ParsedKTCheck | ParsedPunishment | None
    if kind == "support":
        parsed = support_parser.parse(message)
    elif kind == "kt":
        parsed = kt_parser.parse(message)
    else:
        parsed = punishment_parser.parse(message)

    if parsed is None:
        return

    async with session_factory() as session:
        bindings = BindingsRepo(session)
        staff_id = await _resolve_staff_id(bindings, parsed.moderator_alias, message.from_user)
        values = asdict(parsed)
        values["staff_id"] = staff_id
        values.update(_sender_metadata(message))

        if kind == "support":
            event_id = await SupportRepo(session).upsert(values)
        elif kind == "kt":
            event_id = await KTRepo(session).upsert(values)
        else:
            event_id = await PunishmentsRepo(session).upsert(values)

        await session.commit()

    logger.info(
        "Collected %s event id=%s chat=%s message=%s staff_id=%s",
        kind,
        event_id,
        message.chat.id,
        message.message_id,
        staff_id,
    )


def _source_kind(message: Message, app_config: AppConfig) -> str | None:
    sources = app_config.telegram_sources
    if message_matches_source(message, sources.support):
        return "support"
    if message_matches_source(message, sources.kt):
        return "kt"
    if message_matches_source(message, sources.punishments):
        return "punishments"
    return None


def _sender_metadata(message: Message) -> dict[str, object]:
    if message.from_user is None:
        return {
            "sender_user_id": None,
            "sender_username": None,
            "sender_is_bot": False,
        }

    return {
        "sender_user_id": message.from_user.id,
        "sender_username": clean_username(message.from_user.username),
        "sender_is_bot": message.from_user.is_bot,
    }


async def _resolve_staff_id(
    bindings: BindingsRepo,
    alias: str | None,
    from_user: User | None,
) -> int | None:
    telegram_user_id: int | None = None
    username: str | None = None
    if from_user and not from_user.is_bot and alias in {from_user.username, from_user.full_name}:
        telegram_user_id = from_user.id
        username = from_user.username

    return await bindings.resolve_staff_id(
        alias=alias,
        telegram_user_id=telegram_user_id,
        username=username,
    )
