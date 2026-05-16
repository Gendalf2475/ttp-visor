from __future__ import annotations

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.loader import AppConfig
from app.services.stats_service import ModeratorStats, StatsService
from app.utils.dates import Period
from app.utils.text import html_escape, split_telegram_text


class ReportService:
    def __init__(self, config: AppConfig, stats_service: StatsService):
        self.config = config
        self.stats_service = stats_service

    async def build_report_text(self, session: AsyncSession, period: Period, title: str | None = None) -> str:
        report = await self.stats_service.collect(session, period)
        title_text = title or f"Отчёт TTP VISOR за {period.title}"
        lines = [
            f"<b>{html_escape(title_text)}</b>",
            f"Период: {period.start_date.isoformat()} - {period.end_date_inclusive.isoformat()}",
            "",
        ]

        if not report.rows:
            lines.append("За период нет сохранённых событий.")
            return "\n".join(lines)

        lines.append(self._format_row("Модератор", "ТП", "КТ", "Выд", "Снят", "Всего"))
        for row in report.rows:
            lines.append(
                self._format_row(
                    row.name,
                    row.support_tickets,
                    row.kt_checks,
                    row.punishments_issued,
                    row.punishments_removed,
                    row.total,
                )
            )

        totals = report.totals
        lines.append(
            self._format_row(
                totals.name,
                totals.support_tickets,
                totals.kt_checks,
                totals.punishments_issued,
                totals.punishments_removed,
                totals.total,
            )
        )
        return "\n".join(lines)

    async def send_report(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        period: Period,
        title: str | None = None,
    ) -> None:
        if self.config.report_target.chat_id is None:
            raise ValueError("report_target.chat_id is not configured")

        async with session_factory() as session:
            text = await self.build_report_text(session, period, title)

        for chunk in split_telegram_text(text):
            await bot.send_message(
                chat_id=self.config.report_target.chat_id,
                message_thread_id=self.config.report_target.topic_id,
                text=chunk,
            )

    @staticmethod
    def _format_row(
        name: str,
        support: int | str,
        kt: int | str,
        issued: int | str,
        removed: int | str,
        total: int | str,
    ) -> str:
        safe_name = html_escape(name)
        return f"{safe_name} | {support} | {kt} | {issued} | {removed} | {total}"
