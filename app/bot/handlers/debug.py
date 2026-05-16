from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config.loader import AppConfig
from app.utils.text import html_escape


router = Router(name="debug")


@router.message(Command("debug"))
async def debug_message(message: Message, app_config: AppConfig) -> None:
    if not message.from_user or message.from_user.id not in app_config.bot.super_admin_ids:
        return

    topic_id = message.message_thread_id
    from_user = message.from_user
    sender_chat = message.sender_chat

    lines = [
        "🛠 Debug info",
        "",
        f"chat_id: {message.chat.id}",
        f"topic_id: {_value(topic_id)}",
        f"message_id: {message.message_id}",
        f"from_user_id: {from_user.id}",
        f"from_username: {_value(from_user.username)}",
        f"from_full_name: {_value(from_user.full_name)}",
        f"chat_type: {message.chat.type}",
        f"chat_title: {_value(message.chat.title)}",
        f"sender_chat_id: {_value(sender_chat.id if sender_chat else None)}",
        f"sender_chat_title: {_value(sender_chat.title if sender_chat else None)}",
    ]

    is_topic_message = getattr(message, "is_topic_message", None)
    if is_topic_message is not None:
        lines.append(f"is_topic_message: {str(is_topic_message).lower()}")

    text = "\n".join(lines)
    if topic_id is not None:
        await message.answer(text, message_thread_id=topic_id)
    else:
        await message.answer(text)


def _value(value: object | None) -> str:
    if value is None:
        return "none"
    return html_escape(value)

