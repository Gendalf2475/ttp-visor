from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import Message

from app.config.loader import TelegramSourcesConfig, TopicSourceConfig


@dataclass(slots=True, frozen=True)
class SourceMatch:
    source_name: str | None
    matched: bool
    reason: str


def message_matches_source(message: Message, source_config: TopicSourceConfig | None) -> bool:
    return source_match_reason(message, source_config).matched


def source_match_reason(message: Message, source_config: TopicSourceConfig | None) -> SourceMatch:
    if source_config is None or not source_config.enabled:
        return SourceMatch(source_name=None, matched=False, reason="source_disabled_or_missing")

    if message.chat.id != source_config.chat_id:
        return SourceMatch(
            source_name=None,
            matched=False,
            reason=f"chat_id_mismatch expected={source_config.chat_id}",
        )

    topic_id = message.message_thread_id
    if source_config.all_topics:
        return SourceMatch(source_name=None, matched=True, reason="all_topics")

    if source_config.topic_ids:
        if topic_id in source_config.topic_ids:
            return SourceMatch(source_name=None, matched=True, reason="topic_ids")
        return SourceMatch(
            source_name=None,
            matched=False,
            reason=f"topic_ids_mismatch topic_id={_topic_label(topic_id)} allowed={source_config.topic_ids}",
        )

    if source_config.topic_id is not None:
        if topic_id == source_config.topic_id:
            return SourceMatch(source_name=None, matched=True, reason="topic_id")
        return SourceMatch(
            source_name=None,
            matched=False,
            reason=f"topic_id_mismatch topic_id={_topic_label(topic_id)} expected={source_config.topic_id}",
        )

    return SourceMatch(source_name=None, matched=True, reason="whole_chat")


def message_source_match(message: Message, sources: TelegramSourcesConfig) -> SourceMatch:
    same_chat_reasons: list[str] = []

    for source_name, source_config in _iter_sources(sources):
        match = source_match_reason(message, source_config)
        if match.matched:
            return SourceMatch(source_name=source_name, matched=True, reason=match.reason)

        if source_config and message.chat.id == source_config.chat_id:
            same_chat_reasons.append(f"{source_name}:{match.reason}")

    if same_chat_reasons:
        return SourceMatch(source_name=None, matched=False, reason="; ".join(same_chat_reasons))

    return SourceMatch(source_name=None, matched=False, reason="chat_id_not_configured")


def message_is_from_configured_source_chat(message: Message, sources: TelegramSourcesConfig) -> bool:
    return any(
        source_config is not None and message.chat.id == source_config.chat_id
        for _, source_config in _iter_sources(sources)
    )


def _iter_sources(sources: TelegramSourcesConfig) -> list[tuple[str, TopicSourceConfig | None]]:
    return [
        ("support", sources.support),
        ("kt", sources.kt),
        ("punishments", sources.punishments),
    ]


def _topic_label(topic_id: int | None) -> str:
    return "none" if topic_id is None else str(topic_id)
