from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Period:
    key: str
    title: str
    start: datetime
    end: datetime
    timezone_name: str = "UTC"

    @property
    def start_date(self) -> date:
        return self.start.astimezone(ZoneInfo(self.timezone_name)).date()

    @property
    def end_date_inclusive(self) -> date:
        return (self.end - timedelta(microseconds=1)).astimezone(ZoneInfo(self.timezone_name)).date()


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
    return Period("week", "текущую неделю", to_utc(start), to_utc(now), tz_name)


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

    return Period(key, title, to_utc(start), to_utc(end), tz_name)


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
    return Period("custom", f"{start_day.isoformat()} - {end_day.isoformat()}", to_utc(start), to_utc(end), tz_name)


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

    normalized_expression = expression.strip()
    parts = _split_period_expression(normalized_expression)
    if len(parts) == 2:
        current_year = datetime.now(ZoneInfo(tz_name)).year
        return custom_period(
            tz_name,
            parse_date(parts[0], default_year=current_year),
            parse_date(parts[1], default_year=current_year),
        )

    return period_by_key(tz_name, parts[0])


def parse_date(value: str, default_year: int | None = None) -> date:
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass

    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    if default_year is not None:
        try:
            parsed = datetime.strptime(value, "%d.%m")
            return date(default_year, parsed.month, parsed.day)
        except ValueError:
            pass

    raise ValueError(f"Invalid date: {value}")


def _split_period_expression(expression: str) -> list[str]:
    parts = expression.split()
    if len(parts) == 2:
        return parts

    if "–" in expression or "—" in expression:
        return [part.strip() for part in re.split(r"\s*[–—]\s*", expression, maxsplit=1) if part.strip()]

    dotted_range = re.fullmatch(
        r"\s*(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)\s*-\s*(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)\s*",
        expression,
    )
    if dotted_range:
        return [dotted_range.group(1), dotted_range.group(2)]

    spaced_hyphen_range = re.fullmatch(r"\s*(.+?)\s+-\s+(.+?)\s*", expression)
    if spaced_hyphen_range:
        return [spaced_hyphen_range.group(1), spaced_hyphen_range.group(2)]

    return parts
