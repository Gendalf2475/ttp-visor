from __future__ import annotations

import re
from html import escape


ZERO_WIDTH_CHARS = "\u200b\u200c\u200d\ufeff"


def normalize_nickname(value: object | None) -> str:
    if value is None:
        return ""

    normalized = str(value).replace("\u00a0", " ").strip()
    for char in ZERO_WIDTH_CHARS:
        normalized = normalized.replace(char, "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()


def normalize_alias(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_nickname(value)
    normalized = normalized.removeprefix("@")
    return normalized or None


def clean_username(value: str | None) -> str | None:
    normalized = normalize_alias(value)
    if not normalized:
        return None
    return normalized.replace(" ", "")


def html_escape(value: object) -> str:
    return escape(str(value), quote=False)


def split_telegram_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        if current and current_len + len(line) > limit:
            chunks.append("".join(current).rstrip())
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)

    if current:
        chunks.append("".join(current).rstrip())

    return chunks
