from __future__ import annotations

import hashlib
import re


def first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            if match.groups():
                return next((group.strip() for group in match.groups() if group and group.strip()), None)
            return match.group(0).strip()
    return None


def contains_any(markers: list[str], text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def stable_hash(*parts: object) -> str:
    payload = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

