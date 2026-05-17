from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config.loader import ExtraOccupationsGoogleSheetConfig, GoogleSheetsConfig, StaffGoogleSheetConfig
from app.config.settings import Settings


SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


@dataclass(slots=True)
class StaffSheetRow:
    nickname: str
    rank: str | None = None
    mentor: str | None = None
    real_name: str | None = None
    telegram_raw: str | None = None
    telegram_username: str | None = None
    external_key: str | None = None
    telegram_id: int | None = None
    is_active: bool = True
    aliases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExtraOccupationSheetRow:
    nickname: str
    direction: str
    occupation: str
    position: str


class GoogleSheetsClient:
    def __init__(self, settings: Settings, config: GoogleSheetsConfig):
        self.settings = settings
        self.config = config

    async def fetch_staff_rows(self) -> list[StaffSheetRow]:
        staff_config = self.config.staff_config()
        if not staff_config.enabled:
            return []
        if not staff_config.spreadsheet_id:
            raise ValueError("google_sheets.spreadsheet_id is required when Google sync is enabled")

        values = await asyncio.to_thread(self._fetch_values, staff_config.spreadsheet_id, staff_config.range_name)
        return [
            self._parse_staff_row(row, staff_config)
            for row in values[staff_config.header_rows :]
            if self._row_has_nickname(row, staff_config)
        ]

    async def fetch_extra_occupation_rows(self) -> list[ExtraOccupationSheetRow]:
        extra_config = self.config.extra_occupations
        if not extra_config.enabled:
            return []
        if not extra_config.spreadsheet_id:
            raise ValueError("google_sheets.extra_occupations.spreadsheet_id is required when sync is enabled")

        values = await asyncio.to_thread(
            self._fetch_values,
            extra_config.spreadsheet_id,
            extra_config.range_name,
        )
        return self._parse_extra_occupation_rows(values, extra_config)

    def _fetch_values(self, spreadsheet_id: str, range_name: str) -> list[list[str]]:
        credentials = self._load_credentials()
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        return result.get("values", [])

    def _load_credentials(self):
        if self.settings.google_credentials_json:
            info = json.loads(self.settings.google_credentials_json)
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

        credentials_file = self.settings.google_credentials_file
        if credentials_file is None:
            raise ValueError("GOOGLE_CREDENTIALS_FILE or GOOGLE_CREDENTIALS_JSON must be provided")
        return service_account.Credentials.from_service_account_file(Path(credentials_file), scopes=SCOPES)

    def _parse_staff_row(self, row: list[str], config: StaffGoogleSheetConfig) -> StaffSheetRow:
        nickname = self._cell(row, config.nickname_column).strip()
        rank = self._cell_optional(row, config.rank_column)
        mentor = self._cell_optional(row, config.mentor_column)
        real_name = self._cell_optional(row, config.real_name_column)
        telegram_raw = self._cell_optional(row, config.telegram_column)
        telegram_username = self._normalize_telegram_username(telegram_raw)
        external_key = self._cell_optional(row, config.external_key_column)
        telegram_id = self._parse_int(self._cell_optional(row, config.telegram_id_column))
        aliases = self._parse_aliases(self._cell_optional(row, config.aliases_column))

        is_active = bool(nickname)
        if config.active_mode == "presence_in_sheet":
            is_active = bool(nickname)
        elif config.active_column is not None:
            active_value = (self._cell_optional(row, config.active_column) or "").strip().lower()
            is_active = active_value in config.active_values

        return StaffSheetRow(
            nickname=nickname,
            rank=rank,
            mentor=mentor,
            real_name=real_name,
            telegram_raw=telegram_raw,
            telegram_username=telegram_username,
            external_key=external_key,
            telegram_id=telegram_id,
            is_active=is_active,
            aliases=aliases,
        )

    def _parse_extra_occupation_rows(
        self,
        rows: list[list[str]],
        config: ExtraOccupationsGoogleSheetConfig,
    ) -> list[ExtraOccupationSheetRow]:
        del config
        parsed: list[ExtraOccupationSheetRow] = []
        current_direction: str | None = None

        for row in rows:
            cells = [self._cell(row, index).strip() for index in range(3)]
            non_empty = [cell for cell in cells if cell]
            if not non_empty:
                continue

            lowered = {cell.lower() for cell in cells}
            if {"ник", "занятость", "должность"}.issubset(lowered):
                continue

            nickname, occupation, position = cells
            if len(non_empty) == 1:
                current_direction = non_empty[0]
                continue

            if not current_direction:
                current_direction = non_empty[0]
                continue

            if nickname and occupation and position:
                parsed.append(
                    ExtraOccupationSheetRow(
                        nickname=nickname,
                        direction=current_direction,
                        occupation=occupation,
                        position=position,
                    )
                )

        return parsed

    def _row_has_nickname(self, row: list[str], config: StaffGoogleSheetConfig) -> bool:
        return bool(self._cell(row, config.nickname_column).strip())

    @staticmethod
    def _cell(row: list[str], index: int) -> str:
        if index < 0 or index >= len(row):
            return ""
        return str(row[index])

    def _cell_optional(self, row: list[str], index: int | None) -> str | None:
        if index is None:
            return None
        value = self._cell(row, index).strip()
        return value or None

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        if not value:
            return None
        value = value.strip()
        return int(value) if value.isdigit() else None

    @staticmethod
    def _parse_aliases(value: str | None) -> list[str]:
        if not value:
            return []
        aliases = []
        for chunk in value.replace("\n", ",").replace(";", ",").split(","):
            alias = chunk.strip()
            if alias:
                aliases.append(alias)
        return aliases

    @staticmethod
    def _normalize_telegram_username(value: str | None) -> str | None:
        if not value:
            return None

        username = value.strip()
        username = re.sub(r"^https?://t\.me/", "", username, flags=re.IGNORECASE)
        username = re.sub(r"^t\.me/", "", username, flags=re.IGNORECASE)
        username = username.removeprefix("@")
        username = username.split("?", maxsplit=1)[0].strip().strip("/")
        return username or None
