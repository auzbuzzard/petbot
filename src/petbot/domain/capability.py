from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    VOICE = "voice"
    MESSAGE_CONTENT = "message_content"
    RICH_EMBEDS = "rich_embeds"
