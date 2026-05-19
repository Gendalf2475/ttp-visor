from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.loader import AppConfig
from app.db.models.staff import StaffExtraOccupation
from app.db.repositories.extra_occupations_repo import ExtraOccupationsRepo
from app.db.repositories.punishments_repo import PunishmentsRepo
from app.db.repositories.staff_repo import StaffRepo
from app.services.event_filters import EventFilter, IgnoredEventView, normalize_event_kind
from app.services.report_service import ReportService
from app.services.staff_sync import StaffSyncService
from app.utils.dates import current_week, parse_period_expression
from app.utils.messages import safe_answer
from app.utils.text import html_escape, normalize_nickname, split_telegram_text


router = Router(name="admin")
router.message.filter(F.chat.type == "private")


HELP_TEXT = """TTP VISOR доступен только супер-админам.

Команды:
/sync_staff - синхронизировать состав из Google Sheets
/sync_extra - синхронизировать доп. занятости
/stats [period] - короткая сводка
/stats_full [period] - полный отчёт
/stats_user [ник] [period] - отчёт по модератору
/stats_direction [направление] [period] - отчёт по направлению
/report [period] - отправить отчёт в настроенный чат
/extras [ник] - показать доп. занятости
/ignored_staff - показать ignore-list сотрудников
/debug_staff [ник] - проверить staff/extras/events lookup
/normalize_punishments - нормализовать сохранённые наказания
/apply_filters - применить filters к старым событиям
/ignored_events [punishments|support|kt] - показать ignored-события
/restore_event тип id - восстановить событие
/ignore_event тип id причина - исключить событие вручную
/parse_kt_test [текст] - проверить парсинг КТ
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
    await safe_answer(message, "TTP VISOR на связи. /help покажет команды.")


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await safe_answer(message, HELP_TEXT)


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
        await safe_answer(message, f"Не понял период: {exc}")
        return
    try:
        await report_service.send_report(bot, session_factory, period)
    except ValueError as exc:
        await safe_answer(message, str(exc))
        return
    await safe_answer(message, "✅ Отчёт отправлен.")


@router.message(Command("extras"))
async def extras(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    nickname = (command.args or "").strip() or None
    async with session_factory() as session:
        rows = await ExtraOccupationsRepo(session).list_active(nickname)

    ignored_keys = _ignored_nickname_keys(app_config)
    rows = [row for row in rows if normalize_nickname(row.nickname) not in ignored_keys]

    if nickname:
        text = _format_extras_for_nickname(nickname, rows)
    else:
        text = _format_all_extras(rows)

    for chunk in split_telegram_text(text):
        await message.answer(chunk)


@router.message(Command("ignored_staff"))
async def ignored_staff(message: Message, app_config: AppConfig) -> None:
    ignored = [
        nickname.strip()
        for nickname in app_config.staff.ignored_nicknames
        if normalize_nickname(nickname)
    ]
    lines = ["🚫 Игнорируемые сотрудники:"]
    if ignored:
        lines.extend(f"- {html_escape(nickname)}" for nickname in ignored)
    else:
        lines.append("список пуст")
    await message.answer("\n".join(lines))


@router.message(Command("normalize_punishments"))
async def normalize_punishments(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        result = await PunishmentsRepo(session).normalize_punishments()
        await session.commit()

    await safe_answer(
        message,
        "Нормализация наказаний завершена:\n"
        f"проверено: {result.scanned}\n"
        f"нормализовано aliases: {result.normalized}\n"
        f"исправлено punishment_type: {result.types_fixed}\n"
        "по типам: "
        f"ban={result.ban_fixed}, "
        f"mute={result.mute_fixed}, "
        f"warn={result.warn_fixed}, "
        f"unban={result.unban_fixed}, "
        f"unmute={result.unmute_fixed}, "
        f"unwarn={result.unwarn_fixed}\n"
        f"исправлено action: {result.actions_fixed}\n"
        f"помечено invalid: {result.invalidated}\n"
        f"всего исправлений: {result.fixed_total}",
    )


@router.message(Command("apply_filters"))
async def apply_filters(
    message: Message,
    app_config: AppConfig,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        result = await EventFilter(app_config.filters).apply_existing(session)
        await session.commit()

    await safe_answer(
        message,
        "Фильтры применены:\n"
        f"Наказания: {result.punishments} помечено ignored\n"
        f"ТП: {result.support} помечено ignored\n"
        f"КТ: {result.kt} помечено ignored",
    )


@router.message(Command("ignored_events"))
async def ignored_events(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    args = (command.args or "").strip()
    kind = normalize_event_kind(args) if args else None
    if args and kind is None:
        await safe_answer(message, "Неизвестный тип. Используйте punishments, support или kt.")
        return

    async with session_factory() as session:
        rows = await EventFilter(app_config.filters).list_ignored(session, kind, limit=20)

    await safe_answer(message, _format_ignored_events(rows))


@router.message(Command("restore_event"))
async def restore_event(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    parsed = _parse_event_command(command.args, require_reason=False)
    if parsed is None:
        await safe_answer(message, "Использование: /restore_event punishment|support|kt [id]")
        return
    kind, event_id, _reason = parsed

    async with session_factory() as session:
        restored = await EventFilter(app_config.filters).set_ignored(
            session,
            kind,
            event_id,
            is_ignored=False,
            ignore_reason=None,
        )
        await session.commit()

    await safe_answer(message, "✅ Событие восстановлено." if restored else "Событие не найдено.")


@router.message(Command("ignore_event"))
async def ignore_event(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    parsed = _parse_event_command(command.args, require_reason=True)
    if parsed is None:
        await safe_answer(message, "Использование: /ignore_event punishment|support|kt [id] [reason]")
        return
    kind, event_id, reason = parsed

    async with session_factory() as session:
        ignored = await EventFilter(app_config.filters).set_ignored(
            session,
            kind,
            event_id,
            is_ignored=True,
            ignore_reason=reason,
        )
        await session.commit()

    await safe_answer(message, "✅ Событие исключено." if ignored else "Событие не найдено.")


@router.message(Command("debug_staff"))
async def debug_staff(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    report_service: ReportService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    nickname = (command.args or "").strip()
    if not nickname:
        await message.answer("Использование: /debug_staff ник")
        return

    normalized = normalize_nickname(nickname)
    async with session_factory() as session:
        staff = await StaffRepo(session).get_by_nickname_ci(nickname)
        extras_rows = await ExtraOccupationsRepo(session).get_active_by_nickname_ci(nickname)
        stats = (
            await report_service.stats_service.collect_for_staff(
                session,
                current_week(app_config.timezone),
                staff,
            )
            if staff
            else None
        )

    lines = [
        f"🛠 <b>Staff debug: {html_escape(nickname)}</b>",
        "",
        "Lookup:",
        f"input: {html_escape(nickname)}",
        f"normalized: {html_escape(normalized)}",
        "",
        "Staff:",
        f"found: {'yes' if staff else 'no'}",
        f"nickname: {html_escape((staff.nickname or staff.full_name) if staff else 'none')}",
        f"rank: {html_escape((staff.rank or 'none') if staff else 'none')}",
        f"is_active: {str(staff.is_active).lower() if staff else 'none'}",
        "",
        "Extra occupations:",
    ]

    if extras_rows:
        for index, extra in enumerate(extras_rows, start=1):
            lines.append(
                f"{index}. {html_escape(extra.direction)} — "
                f"{html_escape(extra.occupation)} — {html_escape(extra.position)}"
            )
    else:
        lines.append("none")

    lines.extend(
        [
            "",
            "Events current week:",
            f"support: {stats.support_tickets if stats else 0}",
            f"kt: {stats.kt_checks if stats else 0}",
            f"punishments: {stats.punishments.total if stats else 0}",
        ]
    )

    await message.answer("\n".join(lines))


def _parse_event_command(args: str | None, *, require_reason: bool) -> tuple[str, int, str | None] | None:
    parts = (args or "").strip().split(maxsplit=2)
    min_parts = 3 if require_reason else 2
    if len(parts) < min_parts:
        return None

    kind = normalize_event_kind(parts[0])
    if kind is None:
        return None

    try:
        event_id = int(parts[1])
    except ValueError:
        return None

    reason = parts[2].strip() if len(parts) > 2 else None
    if require_reason and not reason:
        return None
    return kind, event_id, reason


def _format_ignored_events(rows: list[IgnoredEventView]) -> str:
    lines = ["🚫 Игнорируемые события"]
    if not rows:
        return "\n".join([*lines, "", "нет данных"])

    labels = {
        "punishment": "Наказания",
        "support": "ТП",
        "kt": "КТ",
    }
    grouped: dict[str, list[IgnoredEventView]] = {}
    for row in rows:
        grouped.setdefault(row.kind, []).append(row)

    for kind in ("punishment", "support", "kt"):
        items = grouped.get(kind)
        if not items:
            continue
        lines.extend(["", f"{labels[kind]}:"])
        for item in items:
            moderator = item.moderator_alias or "unknown"
            lines.append(f"#{item.id} {moderator} — {item.summary}")
            lines.append(f"Причина игнора: {item.ignore_reason or 'none'}")
    return "\n".join(lines)


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


def _ignored_nickname_keys(app_config: AppConfig) -> set[str]:
    return {
        key
        for key in (normalize_nickname(nickname) for nickname in app_config.staff.ignored_nicknames)
        if key
    }
