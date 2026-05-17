from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.bindings_repo import BindingsRepo
from app.db.repositories.extra_occupations_repo import ExtraOccupationSyncResult, ExtraOccupationUpsert, ExtraOccupationsRepo
from app.db.repositories.staff_repo import StaffRepo, StaffUpsert
from app.services.google_sheets import ExtraOccupationSheetRow, GoogleSheetsClient, StaffSheetRow
from app.utils.dates import utc_now
from app.utils.text import normalize_alias


@dataclass(slots=True)
class StaffSyncResult:
    fetched: int
    created: int
    updated: int
    deactivated: int
    extra: ExtraOccupationSyncResult | None = None


class StaffSyncService:
    def __init__(self, sheets_client: GoogleSheetsClient):
        self.sheets_client = sheets_client

    async def sync(self, session: AsyncSession) -> StaffSyncResult:
        staff_result = await self.sync_staff(session, commit=False)
        extra_result = await self.sync_extra(session, commit=False)
        await session.commit()
        staff_result.extra = extra_result
        return staff_result

    async def sync_staff(self, session: AsyncSession, *, commit: bool = True) -> StaffSyncResult:
        if not self.sheets_client.config.staff_config().enabled:
            return StaffSyncResult(fetched=0, created=0, updated=0, deactivated=0)

        rows = await self.sheets_client.fetch_staff_rows()
        staff_repo = StaffRepo(session)
        bindings_repo = BindingsRepo(session)
        synced_at = utc_now()

        created = 0
        updated = 0
        external_keys: set[str] = set()

        for row in rows:
            external_key = self._external_key(row)
            external_keys.add(external_key)
            staff, was_created = await staff_repo.upsert(
                StaffUpsert(
                    external_key=external_key,
                    nickname=row.nickname,
                    rank=row.rank,
                    mentor=row.mentor,
                    real_name=row.real_name,
                    telegram_raw=row.telegram_raw,
                    telegram_username=row.telegram_username,
                    telegram_id=row.telegram_id,
                    is_active=row.is_active,
                    aliases=row.aliases,
                ),
                synced_at=synced_at,
            )

            aliases = [row.nickname, *row.aliases]
            if row.real_name:
                aliases.append(row.real_name)
            if row.telegram_username:
                aliases.append(row.telegram_username)
            for alias in aliases:
                await bindings_repo.upsert_alias(
                    staff_id=staff.id,
                    alias=alias,
                    telegram_user_id=row.telegram_id,
                    telegram_username=row.telegram_username,
                )

            if was_created:
                created += 1
            else:
                updated += 1

        deactivated = await staff_repo.deactivate_missing_external_keys(external_keys, synced_at)
        if commit:
            await session.commit()
        return StaffSyncResult(
            fetched=len(rows),
            created=created,
            updated=updated,
            deactivated=deactivated,
        )

    async def sync_extra(self, session: AsyncSession, *, commit: bool = True) -> ExtraOccupationSyncResult:
        config = self.sheets_client.config
        if "extra_occupations" not in config.model_fields_set and not config.enabled:
            return ExtraOccupationSyncResult(fetched=0, created=0, updated=0, reactivated=0, deactivated=0)
        if not config.extra_occupations.enabled:
            return ExtraOccupationSyncResult(fetched=0, created=0, updated=0, reactivated=0, deactivated=0)

        rows = await self.sheets_client.fetch_extra_occupation_rows()
        result = await ExtraOccupationsRepo(session).sync(
            [self._extra_upsert(row) for row in rows],
            synced_at=utc_now(),
        )
        if commit:
            await session.commit()
        return result

    @staticmethod
    def _external_key(row: StaffSheetRow) -> str:
        if row.external_key:
            return row.external_key
        if row.telegram_id:
            return f"telegram:{row.telegram_id}"
        return f"nickname:{normalize_alias(row.nickname)}"

    @staticmethod
    def _extra_upsert(row: ExtraOccupationSheetRow) -> ExtraOccupationUpsert:
        return ExtraOccupationUpsert(
            nickname=row.nickname,
            direction=row.direction,
            occupation=row.occupation,
            position=row.position,
        )
