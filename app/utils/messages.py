from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import Message

from app.utils.text import split_telegram_text


async def safe_send_message(
    bot: Bot,
    chat_id: int | str,
    text: str,
    topic_id: int | None = None,
) -> list[Any]:
    kwargs: dict[str, Any] = {}
    if topic_id is not None:
        kwargs["message_thread_id"] = topic_id

    sent_messages: list[Any] = []
    for chunk in split_telegram_text(text):
        sent_messages.append(
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=None,
                **kwargs,
            )
        )
    return sent_messages


async def safe_answer(message: Message, text: str) -> list[Any]:
    sent_messages: list[Any] = []
    for chunk in split_telegram_text(text):
        sent_messages.append(await message.answer(chunk, parse_mode=None))
    return sent_messages
