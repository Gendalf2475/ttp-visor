from __future__ import annotations

from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.handlers import admin, bindings, debug, service, stats
from app.bot.middlewares.access import AccessMiddleware
from app.config.loader import AppConfig
from app.services.parser_kt import KTParser
from app.services.parser_punishments import PunishmentParser
from app.services.parser_support import SupportParser
from app.services.report_service import ReportService
from app.services.staff_sync import StaffSyncService


def build_dispatcher(
    *,
    app_config: AppConfig,
    session_factory: async_sessionmaker[AsyncSession],
    staff_sync_service: StaffSyncService,
    report_service: ReportService,
    support_parser: SupportParser,
    kt_parser: KTParser,
    punishment_parser: PunishmentParser,
) -> Dispatcher:
    dp = Dispatcher()
    access = AccessMiddleware(app_config)
    dp.message.middleware(access)
    dp.edited_message.middleware(access)
    dp.callback_query.middleware(access)

    dp.workflow_data.update(
        app_config=app_config,
        session_factory=session_factory,
        staff_sync_service=staff_sync_service,
        report_service=report_service,
        support_parser=support_parser,
        kt_parser=kt_parser,
        punishment_parser=punishment_parser,
    )

    dp.include_router(debug.router)
    dp.include_router(admin.router)
    dp.include_router(stats.router)
    dp.include_router(bindings.router)
    dp.include_router(service.router)
    return dp
