from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config.loader import AppConfig
from app.utils.telegram_sources import message_is_from_configured_source_chat, message_source_match


logger = logging.getLogger(__name__)


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
        self._log_source_message_debug(message)

        if self._is_debug_command(message):
            if message.from_user and message.from_user.id in self.config.bot.super_admin_ids:
                return await handler(message, data)
            if message.chat.type == ChatType.PRIVATE:
                await message.answer("Доступ запрещён.")
            return None

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
        return message_source_match(message, self.config.telegram_sources).matched

    def _log_source_message_debug(self, message: Message) -> None:
        if not logger.isEnabledFor(logging.DEBUG):
            return
        if not message_is_from_configured_source_chat(message, self.config.telegram_sources):
            return

        from_user = message.from_user
        sender_chat = message.sender_chat
        source_match = message_source_match(message, self.config.telegram_sources)
        text_preview = ((message.text or message.caption or "")[:300]).replace("\n", "\\n")

        logger.debug(
            "Incoming source chat message: chat_id=%s topic_id=%s message_id=%s "
            "from_user_id=%s from_username=%s from_user_is_bot=%s "
            "sender_chat_id=%s sender_chat_title=%s text_preview=%r "
            "source_matched=%s source_name=%s source_reason=%s",
            message.chat.id,
            message.message_thread_id,
            message.message_id,
            from_user.id if from_user else None,
            from_user.username if from_user else None,
            from_user.is_bot if from_user else None,
            sender_chat.id if sender_chat else None,
            sender_chat.title if sender_chat else None,
            text_preview,
            source_match.matched,
            source_match.source_name,
            source_match.reason,
        )

    @staticmethod
    def _is_debug_command(message: Message) -> bool:
        text = message.text or message.caption or ""
        command = text.strip().split(maxsplit=1)[0] if text.strip() else ""
        return command.split("@", maxsplit=1)[0] == "/debug"
