from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Period:
    key: str
    title: str
    start: datetime
    end: datetime

    @property
    def start_date(self) -> date:
        return self.start.date()

    @property
    def end_date_inclusive(self) -> date:
        return (self.end - timedelta(microseconds=1)).date()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def local_midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz)


def current_week(tz_name: str) -> Period:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    start_day = now.date() - timedelta(days=now.weekday())
    start = local_midnight(start_day, tz)
    return Period("week", "текущую неделю", to_utc(start), to_utc(now))


def month_period(tz_name: str, offset_months: int, key: str, title: str) -> Period:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    month_index = now.month - 1 + offset_months
    year = now.year + month_index // 12
    month = month_index % 12 + 1
    start = local_midnight(date(year, month, 1), tz)
    next_month_index = month_index + 1
    next_year = now.year + next_month_index // 12
    next_month = next_month_index % 12 + 1
    end = local_midnight(date(next_year, next_month, 1), tz)

    if offset_months == 0:
        end = min(end, now)

    return Period(key, title, to_utc(start), to_utc(end))


def current_month(tz_name: str) -> Period:
    return month_period(tz_name, 0, "current_month", "текущий месяц")


def previous_month(tz_name: str) -> Period:
    return month_period(tz_name, -1, "previous_month", "прошлый месяц")


def two_months_ago(tz_name: str) -> Period:
    return month_period(tz_name, -2, "two_months_ago", "позапрошлый месяц")


def custom_period(tz_name: str, start_day: date, end_day: date) -> Period:
    if end_day < start_day:
        raise ValueError("end date must be greater than or equal to start date")
    tz = ZoneInfo(tz_name)
    start = local_midnight(start_day, tz)
    end = local_midnight(end_day + timedelta(days=1), tz)
    return Period("custom", f"{start_day.isoformat()} - {end_day.isoformat()}", to_utc(start), to_utc(end))


def period_by_key(tz_name: str, key: str) -> Period:
    aliases = {
        "week": current_week,
        "неделя": current_week,
        "month": current_month,
        "current_month": current_month,
        "текущий_месяц": current_month,
        "prev_month": previous_month,
        "previous_month": previous_month,
        "прошлый_месяц": previous_month,
        "prev2_month": two_months_ago,
        "two_months_ago": two_months_ago,
        "позапрошлый_месяц": two_months_ago,
    }
    try:
        return aliases[key](tz_name)
    except KeyError as exc:
        raise ValueError(f"Unknown period key: {key}") from exc


def parse_period_expression(tz_name: str, expression: str | None) -> Period:
    if not expression or not expression.strip():
        return current_week(tz_name)

    parts = expression.strip().split()
    if len(parts) == 2:
        return custom_period(tz_name, parse_date(parts[0]), parse_date(parts[1]))

    return period_by_key(tz_name, parts[0])


def parse_date(value: str) -> date:
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, "%d.%m.%Y").date()
