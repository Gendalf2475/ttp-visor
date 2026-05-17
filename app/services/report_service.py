from __future__ import annotations

from collections.abc import Callable

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.loader import AppConfig
from app.db.models.staff import StaffMember
from app.db.repositories.staff_repo import StaffRepo
from app.services.stats_service import ModeratorStats, PunishmentBreakdown, StatsReport, StatsService
from app.utils.dates import Period
from app.utils.messages import safe_send_message


DIRECTION_ALIASES = {
    "punishments": "punishments",
    "наказания": "punishments",
    "баны": "punishments",
    "bun": "punishments",
    "support": "support",
    "tp": "support",
    "тп": "support",
    "поддержка": "support",
    "kt": "kt",
    "кт": "kt",
    "checks": "kt",
    "ticket_checks": "kt",
    "проверка": "kt",
    "проверка_тикетов": "kt",
}


class ReportService:
    def __init__(self, config: AppConfig, stats_service: StatsService):
        self.config = config
        self.stats_service = stats_service

    async def build_report_text(
        self,
        session: AsyncSession,
        period: Period,
        title: str | None = None,
        report_format: str | None = None,
    ) -> str:
        selected_format = report_format or self.config.reports.default_stats_format
        if selected_format == "full":
            return await self.build_full_report_text(session, period, title)
        return await self.build_compact_report_text(session, period, title)

    async def build_compact_report_text(
        self,
        session: AsyncSession,
        period: Period,
        title: str | None = None,
    ) -> str:
        report = await self.stats_service.collect(
            session,
            period,
            show_zero_activity_staff=self.config.reports.compact_show_extra_directions,
        )
        totals = report.totals
        title_text = title or f"TTP VISOR — {_format_compact_title(period)}"
        lines = [
            f"📊 {title_text}",
            f"🗓 {_format_compact_period(period)}",
            "",
            "📌 Всего:",
            f"🎫 ТП: {totals.support_tickets}",
            f"🧾 КТ: {totals.kt_checks}",
            f"⚖️ Наказаний: {totals.punishments.issued}",
            f"✅ Снятий: {totals.punishments.removed}",
            f"🔢 Действий: {totals.total}",
            "",
            "⚖️ Наказания:",
            (
                f"⛔️ Баны: {totals.punishments.ban} | "
                f"🔇 Муты: {totals.punishments.mute} | "
                f"⚠️ Варны: {totals.punishments.warn}"
            ),
            f"✅ Снятия: {totals.punishments.removed} | ❗️Без пункта: {totals.punishments.without_rule}",
            "",
            f"🏆 Топ-{self.config.reports.compact_top_limit}:",
        ]
        lines.extend(
            self._format_top(
                report.rows,
                limit=self.config.reports.compact_top_limit,
                suffix="",
            )
        )

        if self.config.reports.compact_show_extra_directions:
            lines.extend(["", *self._format_compact_extra_directions(report.rows)])

        lines.extend(
            [
                "",
                "📎 Подробно: /stats_full",
                "👤 По модератору: /stats_user [ник]",
                "📂 По направлению: /stats_direction [направление]",
            ]
        )
        return "\n".join(lines)

    async def build_full_report_text(
        self,
        session: AsyncSession,
        period: Period,
        title: str | None = None,
    ) -> str:
        report = await self.stats_service.collect(session, period)
        rows = self._full_report_rows(report.rows)
        title_text = title or f"TTP VISOR — отчёт за {period.title}"
        lines = [
            f"📊 {title_text}",
            f"🗓 Период: {_format_period(period)}",
            "",
        ]

        if not rows:
            lines.append("За период нет сохранённых событий.")
            return "\n".join(lines)

        totals = report.totals
        lines.extend(self._format_summary(totals))
        lines.extend(["", *self._format_punishment_details(totals.punishments)])
        lines.extend(["", "🏆 Топ модераторов:"])
        lines.extend(self._format_top(report.rows))
        lines.extend(["", "👮‍♂️ Модераторы:"])
        for index, row in enumerate(rows, start=1):
            lines.extend(["", *self._format_moderator_card(row, index=index)])
        return "\n".join(lines)

    async def build_user_report_text(self, session: AsyncSession, nickname: str, period: Period) -> str:
        if self.stats_service.is_ignored(nickname):
            return "Этот сотрудник находится в ignore-list и не учитывается в статистике."

        staff = await StaffRepo(session).find_by_nickname(nickname)
        if staff is None:
            return "Модератор не найден в базе состава."
        if self.stats_service.is_ignored(staff.nickname) or self.stats_service.is_ignored(staff.full_name):
            return "Этот сотрудник находится в ignore-list и не учитывается в статистике."

        stats = await self.stats_service.collect_for_staff(session, period, staff)
        if stats.total == 0:
            return "За выбранный период по этому модератору нет сохранённых событий."

        lines = [
            f"👮‍♂️ Отчёт по модератору: {staff.nickname or staff.full_name}",
            f"🗓 Период: {_format_period(period)}",
            "",
            f"🏷 Ранг: {stats.rank or 'нет'}",
            f"💼 Доп. занятость: {_extras_inline(stats)}",
            "",
            "📌 Общая активность:",
            f"🎫 Поддержка: {stats.support_tickets}",
            f"🧾 Проверка тикетов: {stats.kt_checks}",
            f"⚖️ Наказаний всего: {stats.punishments.total}",
            f"🔢 Всего действий: {stats.total}",
            "",
            *self._format_punishment_details(stats.punishments),
        ]
        return "\n".join(lines)

    async def build_direction_report_text(self, session: AsyncSession, direction: str, period: Period) -> str:
        normalized_direction = DIRECTION_ALIASES.get(direction.strip().lower())
        if normalized_direction is None:
            return "Неизвестное направление. Используйте punishments, support или kt."

        report = await self.stats_service.collect(session, period, show_zero_activity_staff=False)
        if normalized_direction == "punishments":
            return self._format_punishments_direction(report)
        if normalized_direction == "support":
            return self._format_support_direction(report)
        return self._format_kt_direction(report)

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
            text = await self.build_report_text(
                session,
                period,
                title,
                report_format=self.config.reports.auto_report_format,
            )

        await safe_send_message(
            bot,
            self.config.report_target.chat_id,
            text,
            topic_id=self.config.report_target.topic_id,
        )

    def _format_summary(self, totals: ModeratorStats) -> list[str]:
        return [
            "📌 Общая статистика:",
            f"🎫 Закрыто тикетов ТП: {totals.support_tickets}",
            f"🧾 Проверено тикетов КТ: {totals.kt_checks}",
            f"⚖️ Выдано наказаний: {totals.punishments.issued}",
            f"✅ Снято наказаний: {totals.punishments.removed}",
            f"🔢 Всего действий: {totals.total}",
        ]

    def _format_punishment_details(self, punishments: PunishmentBreakdown) -> list[str]:
        return [
            "⚖️ Детализация наказаний:",
            f"⛔️ Баны: {punishments.ban}",
            f"🔇 Муты: {punishments.mute}",
            f"⚠️ Предупреждения: {punishments.warn}",
            f"✅ Снятия наказаний: {punishments.removed}",
            f"   ├ Анбаны: {punishments.unban}",
            f"   ├ Анмуты: {punishments.unmute}",
            f"   └ Снятия предупреждений: {punishments.unwarn}",
            f"❗️Без пункта правила: {punishments.without_rule}",
        ]

    def _format_top(
        self,
        rows: list[ModeratorStats],
        metric: str = "total",
        suffix: str = "действий",
        limit: int = 10,
    ) -> list[str]:
        top_rows = sorted(
            (row for row in rows if self._metric(row, metric) > 0),
            key=lambda row: (-self._metric(row, metric), row.name.lower()),
        )
        if not top_rows:
            return ["нет данных"]
        return [
            f"{index}. {row.name} — {self._metric(row, metric)} {suffix}".rstrip()
            for index, row in enumerate(top_rows[:limit], start=1)
        ]

    def _format_moderator_card(self, row: ModeratorStats, index: int) -> list[str]:
        show_support = (
            row.support_tickets > 0
            or self.config.reports.show_zero_support_without_extra
            or _has_support_extra(row)
        )
        show_kt = (
            row.kt_checks > 0
            or self.config.reports.show_zero_kt_without_extra
            or _has_kt_extra(row)
        )

        lines = [
            f"{index}. {row.name}",
            f"🏷 Ранг: {row.rank or 'нет'}",
            f"💼 Доп. занятость: {_extras_inline(row)}",
        ]
        if show_support:
            lines.append(f"🎫 Поддержка: {row.support_tickets}")
        if show_kt:
            lines.append(f"🧾 Проверка тикетов: {row.kt_checks}")
        lines.extend(
            [
                f"⚖️ Наказания: {row.punishments.total}",
                f"⛔️ Баны: {row.punishments.ban}",
                f"🔇 Муты: {row.punishments.mute}",
                f"⚠️ Предупреждения: {row.punishments.warn}",
                f"✅ Снятия: {row.punishments.removed}",
                f"❗️ Без пункта правила: {row.punishments.without_rule}",
                f"🔢 Всего: {row.total}",
            ]
        )
        return lines

    def _full_report_rows(self, rows: list[ModeratorStats]) -> list[ModeratorStats]:
        if self.config.reports.full_report_show_zero_activity_staff:
            return rows
        return [row for row in rows if row.total > 0 or row.extra_occupations]

    def _format_compact_extra_directions(self, rows: list[ModeratorStats]) -> list[str]:
        groups = [
            ("🎫 ТП", _has_support_extra),
            ("🧾 КТ", _has_kt_extra),
            ("🌐 Соцсети", _has_social_extra),
        ]
        lines = ["💼 Доп. направления:"]
        has_data = False
        for label, predicate in groups:
            names = _extra_direction_names(rows, predicate)
            if not names:
                continue
            has_data = True
            lines.append(f"{label}: {', '.join(names)}")
        if not has_data:
            lines.append("нет данных")
        return lines

    def _format_punishments_direction(self, report: StatsReport) -> str:
        totals = report.totals.punishments
        rows = [row for row in report.rows if row.punishments.total > 0]
        lines = [
            "⚖️ Отчёт по направлению: Наказания",
            f"🗓 Период: {_format_period(report.period)}",
            "",
            f"📌 Всего наказаний: {totals.total}",
            f"⛔️ Баны: {totals.ban}",
            f"🔇 Муты: {totals.mute}",
            f"⚠️ Предупреждения: {totals.warn}",
            f"✅ Снятия наказаний: {totals.removed}",
            f"❗️Без пункта правила: {totals.without_rule}",
            "",
            "🏆 Топ-10 по наказаниям:",
        ]
        lines.extend(self._format_top(rows, metric="punishments", suffix="", limit=10))
        return "\n".join(lines)

    def _format_support_direction(self, report: StatsReport) -> str:
        rows = [row for row in report.rows if row.support_tickets > 0]
        lines = [
            "🎫 Отчёт по направлению: Поддержка",
            f"🗓 Период: {_format_period(report.period)}",
            "",
            f"📌 Всего закрыто тикетов: {report.totals.support_tickets}",
            "",
            "🏆 Топ-10 по закрытым тикетам:",
        ]
        lines.extend(self._format_top(rows, metric="support", suffix="", limit=10))
        return "\n".join(lines)

    def _format_kt_direction(self, report: StatsReport) -> str:
        rows = [row for row in report.rows if row.kt_checks > 0]
        lines = [
            "🧾 Отчёт по направлению: Проверка тикетов",
            f"🗓 Период: {_format_period(report.period)}",
            "",
            f"📌 Всего проверено тикетов: {report.totals.kt_checks}",
            "",
            "🏆 Топ-10 по проверенным тикетам:",
        ]
        lines.extend(self._format_top(rows, metric="kt", suffix="", limit=10))
        return "\n".join(lines)

    @staticmethod
    def _metric(row: ModeratorStats, metric: str) -> int:
        if metric == "support":
            return row.support_tickets
        if metric == "kt":
            return row.kt_checks
        if metric == "punishments":
            return row.punishments.total
        return row.total


def _format_period(period: Period) -> str:
    return f"{period.start_date:%d.%m.%Y} — {period.end_date_inclusive:%d.%m.%Y}"


def _format_compact_period(period: Period) -> str:
    start = period.start_date
    end = period.end_date_inclusive
    if start.year == end.year:
        return f"{start:%d.%m}–{end:%d.%m}"
    return f"{start:%d.%m.%Y}–{end:%d.%m.%Y}"


def _format_compact_title(period: Period) -> str:
    titles = {
        "week": "неделя",
        "current_month": "месяц",
        "previous_month": "прошлый месяц",
        "two_months_ago": "позапрошлый месяц",
    }
    return titles.get(period.key, "период")


def _extras_inline(row: ModeratorStats | StaffMember) -> str:
    extras = getattr(row, "extra_occupations", [])
    if not extras:
        return "нет"
    return ", ".join(extra.short_label for extra in extras)


def _has_support_extra(row: ModeratorStats) -> bool:
    return _has_extra_with_markers(
        row,
        markers=("тп", "тех", "поддерж", "техническая поддержка", "поддержка"),
    )


def _has_kt_extra(row: ModeratorStats) -> bool:
    return _has_extra_with_markers(
        row,
        markers=("кт", "контроль тикетов", "проверка тикетов"),
    )


def _has_social_extra(row: ModeratorStats) -> bool:
    return _has_extra_with_markers(row, markers=("соц", "социаль"))


def _has_extra_with_markers(row: ModeratorStats, markers: tuple[str, ...]) -> bool:
    for extra in row.extra_occupations:
        text = f"{extra.direction} {extra.occupation}".lower()
        if any(marker in text for marker in markers):
            return True
    return False


def _extra_direction_names(rows: list[ModeratorStats], predicate: Callable[[ModeratorStats], bool]) -> list[str]:
    names_by_key: dict[str, str] = {}
    for row in rows:
        if not predicate(row):
            continue
        key = row.name.lower()
        names_by_key.setdefault(key, row.name)
    return [names_by_key[key] for key in sorted(names_by_key)]
