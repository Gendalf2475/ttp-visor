from __future__ import annotations

from aiogram.types import Message

from app.config.loader import TopicSourceConfig


def message_matches_source(message: Message, source_config: TopicSourceConfig | None) -> bool:
    if source_config is None or not source_config.enabled:
        return False

    if message.chat.id != source_config.chat_id:
        return False

    topic_id = message.message_thread_id
    if source_config.all_topics:
        return True

    if source_config.topic_ids:
        return topic_id in source_config.topic_ids

    if source_config.topic_id is not None:
        return topic_id == source_config.topic_id

    return True

