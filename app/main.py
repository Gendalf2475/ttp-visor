from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.dispatcher import build_dispatcher
from app.config.loader import load_app_config
from app.config.settings import Settings
from app.db.session import create_engine, create_session_factory
from app.services.google_sheets import GoogleSheetsClient
from app.services.parser_kt import KTParser
from app.services.parser_punishments import PunishmentParser
from app.services.parser_support import SupportParser
from app.services.report_service import ReportService
from app.services.scheduler import SchedulerService
from app.services.staff_sync import StaffSyncService
from app.services.stats_service import StatsService
from app.utils.logging import setup_logging


logger = logging.getLogger(__name__)


async def run() -> None:
    settings = Settings()
    setup_logging(settings.log_level)
    app_config = load_app_config(settings.config_path)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    sheets_client = GoogleSheetsClient(settings, app_config.google_sheets)
    staff_sync_service = StaffSyncService(sheets_client, app_config.staff.ignored_nicknames)
    stats_service = StatsService(app_config.staff.ignored_nicknames)
    report_service = ReportService(app_config, stats_service)
    support_parser = SupportParser(app_config.parsers.support)
    kt_parser = KTParser(app_config.parsers.kt)
    punishment_parser = PunishmentParser(app_config.parsers.punishments, app_config.timezone)

    dispatcher = build_dispatcher(
        app_config=app_config,
        session_factory=session_factory,
        staff_sync_service=staff_sync_service,
        report_service=report_service,
        support_parser=support_parser,
        kt_parser=kt_parser,
        punishment_parser=punishment_parser,
    )

    scheduler = SchedulerService(
        config=app_config,
        bot=bot,
        session_factory=session_factory,
        staff_sync_service=staff_sync_service,
        report_service=report_service,
    )
    scheduler.start()

    try:
        logger.info("Starting TTP VISOR polling")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await scheduler.shutdown()
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
