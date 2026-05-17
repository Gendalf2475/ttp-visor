from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.config.loader import AppConfig
from app.services.parser_kt import KTParser


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
    await message.answer(text, parse_mode=None)


@router.message(Command("parse_kt_test"))
async def parse_kt_test(
    message: Message,
    command: CommandObject,
    app_config: AppConfig,
    kt_parser: KTParser,
) -> None:
    if not message.from_user or message.from_user.id not in app_config.bot.super_admin_ids:
        return

    text = _reply_text(message) or (command.args or "").strip()
    if not text:
        await message.answer("Использование: /parse_kt_test [текст] или reply на сообщение.", parse_mode=None)
        return

    analysis = kt_parser.analyze_text(text)
    first_numbers = ",".join(str(number) for number in analysis.ticket_numbers[:5])
    if analysis.ticket_numbers and len(analysis.ticket_numbers) > 5:
        first_numbers += "..."

    lines = [
        f"matched: {_yes_no(analysis.matched)}",
        f"ignored: {_yes_no(analysis.ignored)}",
        f"ranges: {', '.join(analysis.ranges) if analysis.ranges else '[]'}",
        f"singles: {_format_list(analysis.singles)}",
        f"tickets_count: {analysis.tickets_count}",
        f"ticket_numbers_first: {first_numbers or '[]'}",
    ]
    if analysis.failure_reason:
        lines.append(f"failure_reason: {analysis.failure_reason}")

    await message.answer("\n".join(lines), parse_mode=None)


def _value(value: object | None) -> str:
    if value is None:
        return "none"
    return str(value)


def _reply_text(message: Message) -> str | None:
    if not message.reply_to_message:
        return None
    text = message.reply_to_message.text or message.reply_to_message.caption
    return text.strip() if text and text.strip() else None


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_list(values: list[int]) -> str:
    return "[" + ", ".join(str(value) for value in values) + "]" if values else "[]"
