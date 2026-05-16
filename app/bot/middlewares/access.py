from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config.loader import AppConfig, TopicSourceConfig


class AccessMiddleware(BaseMiddleware):
    def __init__(self, config: AppConfig):
        self.config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            return await self._handle_message(handler, event, data)
        if isinstance(event, CallbackQuery):
            return await self._handle_callback(handler, event, data)
        return await handler(event, data)

    async def _handle_message(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        message: Message,
        data: dict[str, Any],
    ) -> Any:
        if self._is_source_message(message):
            return await handler(message, data)

        user = message.from_user
        if message.chat.type == ChatType.PRIVATE and user and user.id in self.config.bot.super_admin_ids:
            return await handler(message, data)

        if message.chat.type == ChatType.PRIVATE:
            await message.answer("Доступ запрещён.")
        return None

    async def _handle_callback(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        callback: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        if callback.from_user and callback.from_user.id in self.config.bot.super_admin_ids:
            return await handler(callback, data)
        await callback.answer("Доступ запрещён.", show_alert=True)
        return None

    def _is_source_message(self, message: Message) -> bool:
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}:
            return False
        topic_id = message.message_thread_id
        return any(
            self._matches_source(source, message.chat.id, topic_id)
            for source in (
                self.config.telegram_sources.support,
                self.config.telegram_sources.kt,
                self.config.telegram_sources.punishments,
            )
        )

    @staticmethod
    def _matches_source(source: TopicSourceConfig | None, chat_id: int, topic_id: int | None) -> bool:
        return bool(source and source.matches(chat_id, topic_id))

