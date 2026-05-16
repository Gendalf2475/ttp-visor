from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.loader import AppConfig
from app.services.report_service import ReportService
from app.services.staff_sync import StaffSyncService
from app.utils.dates import period_by_key


logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        *,
        config: AppConfig,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        staff_sync_service: StaffSyncService,
        report_service: ReportService,
    ):
        self.config = config
        self.bot = bot
        self.session_factory = session_factory
        self.staff_sync_service = staff_sync_service
        self.report_service = report_service
        self.scheduler = AsyncIOScheduler(timezone=ZoneInfo(config.scheduler.timezone))

    def start(self) -> None:
        if not self.config.scheduler.enabled:
            logger.info("Scheduler is disabled")
            return

        staff_sync = self.config.scheduler.staff_sync
        if staff_sync and staff_sync.enabled:
            self.scheduler.add_job(
                self.run_staff_sync,
                CronTrigger.from_crontab(staff_sync.cron, timezone=ZoneInfo(self.config.scheduler.timezone)),
                id="staff_sync",
                replace_existing=True,
            )

        for index, report in enumerate(self.config.scheduler.reports):
            if not report.enabled:
                continue
            self.scheduler.add_job(
                self.run_report,
                CronTrigger.from_crontab(report.cron, timezone=ZoneInfo(self.config.scheduler.timezone)),
                id=f"report_{index}_{report.period}",
                replace_existing=True,
                kwargs={"period_key": report.period, "title": report.title},
            )

        self.scheduler.start()
        logger.info("Scheduler started with %s jobs", len(self.scheduler.get_jobs()))

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def run_staff_sync(self) -> None:
        logger.info("Scheduled staff sync started")
        async with self.session_factory() as session:
            result = await self.staff_sync_service.sync(session)
        logger.info(
            "Scheduled staff sync finished: fetched=%s created=%s updated=%s deactivated=%s",
            result.fetched,
            result.created,
            result.updated,
            result.deactivated,
        )

    async def run_report(self, *, period_key: str, title: str | None = None) -> None:
        logger.info("Scheduled report started: period=%s", period_key)
        period = period_by_key(self.config.timezone, period_key)
        await self.report_service.send_report(self.bot, self.session_factory, period, title)
        logger.info("Scheduled report sent: period=%s", period_key)

