from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class BotAccessConfig(BaseModel):
    super_admin_ids: set[int] = Field(default_factory=set)


class TopicSourceConfig(BaseModel):
    enabled: bool = True
    chat_id: int
    topic_id: int | None = None
    topic_ids: list[int] = Field(default_factory=list)
    all_topics: bool = False

    def matches(self, chat_id: int, topic_id: int | None) -> bool:
        if not self.enabled or self.chat_id != chat_id:
            return False
        if self.all_topics:
            return True
        if self.topic_ids:
            return topic_id in self.topic_ids
        if self.topic_id is not None:
            return self.topic_id == topic_id
        return True


class TelegramSourcesConfig(BaseModel):
    support: TopicSourceConfig | None = None
    kt: TopicSourceConfig | None = None
    punishments: TopicSourceConfig | None = None

    def source_names(self) -> list[str]:
        return [
            name
            for name in ("support", "kt", "punishments")
            if getattr(self, name) is not None and getattr(self, name).enabled
        ]


class ReportTargetConfig(BaseModel):
    chat_id: int | None = None
    topic_id: int | None = None


class ReportsConfig(BaseModel):
    show_zero_support_without_extra: bool = False
    show_zero_kt_without_extra: bool = False


class StaffGoogleSheetConfig(BaseModel):
    enabled: bool = True
    spreadsheet_id: str | None = "1Ss0Eq_zqrbQh2JQ4cr4d1AVG8-7-OPeHorSdh5-umII"
    sheet_name: str = "Администрация | Штат"
    range_name: str = "'Администрация | Штат'!A4:E"
    active_mode: Literal["presence_in_sheet"] = "presence_in_sheet"
    external_key_column: int | None = None
    rank_column: int = 0
    nickname_column: int = 1
    mentor_column: int | None = 2
    real_name_column: int | None = 3
    telegram_column: int | None = 4
    telegram_id_column: int | None = None
    active_column: int | None = None
    aliases_column: int | None = None
    active_values: set[str] = Field(default_factory=lambda: {"active", "yes", "true", "1", "да", "активен"})
    header_rows: int = 0


class ExtraOccupationsGoogleSheetConfig(BaseModel):
    enabled: bool = True
    spreadsheet_id: str | None = "1Ss0Eq_zqrbQh2JQ4cr4d1AVG8-7-OPeHorSdh5-umII"
    sheet_name: str = "Таблица | Доп. занятость"
    range_name: str = "'Таблица | Доп. занятость'!A1:C200"


class GoogleSheetsConfig(StaffGoogleSheetConfig):
    staff: StaffGoogleSheetConfig | None = None
    extra_occupations: ExtraOccupationsGoogleSheetConfig = Field(
        default_factory=ExtraOccupationsGoogleSheetConfig
    )

    def staff_config(self) -> StaffGoogleSheetConfig:
        if self.staff is not None:
            return self.staff
        return StaffGoogleSheetConfig(
            enabled=self.enabled,
            spreadsheet_id=self.spreadsheet_id,
            sheet_name=self.sheet_name,
            range_name=self.range_name,
            active_mode=self.active_mode,
            external_key_column=self.external_key_column,
            rank_column=self.rank_column,
            nickname_column=self.nickname_column,
            mentor_column=self.mentor_column,
            real_name_column=self.real_name_column,
            telegram_column=self.telegram_column,
            telegram_id_column=self.telegram_id_column,
            active_column=self.active_column,
            aliases_column=self.aliases_column,
            active_values=self.active_values,
            header_rows=self.header_rows,
        )


class ParserRulesConfig(BaseModel):
    ticket_id_patterns: list[str] = Field(default_factory=list)
    moderator_patterns: list[str] = Field(default_factory=list)
    required_markers: list[str] = Field(default_factory=list)


class PunishmentParserConfig(ParserRulesConfig):
    issued_markers: list[str] = Field(default_factory=list)
    removed_markers: list[str] = Field(default_factory=list)


class ParsersConfig(BaseModel):
    support: ParserRulesConfig = Field(default_factory=ParserRulesConfig)
    kt: ParserRulesConfig = Field(default_factory=ParserRulesConfig)
    punishments: PunishmentParserConfig = Field(default_factory=PunishmentParserConfig)


class CronJobConfig(BaseModel):
    enabled: bool = False
    cron: str = "0 0 * * *"

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        if len(value.split()) != 5:
            raise ValueError("cron must use standard 5-field crontab format")
        return value


class ReportJobConfig(CronJobConfig):
    period: Literal["week", "current_month", "previous_month", "two_months_ago"] = "week"
    title: str | None = None


class SchedulerConfig(BaseModel):
    enabled: bool = True
    timezone: str = "Europe/Moscow"
    staff_sync: CronJobConfig | None = None
    reports: list[ReportJobConfig] = Field(default_factory=list)


class AppConfig(BaseModel):
    timezone: str = "Europe/Moscow"
    bot: BotAccessConfig = Field(default_factory=BotAccessConfig)
    telegram_sources: TelegramSourcesConfig = Field(default_factory=TelegramSourcesConfig)
    report_target: ReportTargetConfig = Field(default_factory=ReportTargetConfig)
    reports: ReportsConfig = Field(default_factory=ReportsConfig)
    google_sheets: GoogleSheetsConfig = Field(default_factory=GoogleSheetsConfig)
    parsers: ParsersConfig = Field(default_factory=ParsersConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)


def load_app_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    return AppConfig.model_validate(raw)
