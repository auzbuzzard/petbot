"""Platform-neutral text chunking for the per-message length cap.

Pure (no platform types): the edge is the only thing left that needs it, so it
lives beside the renderer rather than in the kernel.
"""

from __future__ import annotations

#: Discord's hard limit on message content length.
DISCORD_MAX_TEXT = 2000


def chunk_text(text: str, *, limit: int = DISCORD_MAX_TEXT) -> list[str]:
    """Split ``text`` into chunks no longer than ``limit``, preferring newlines.

    Never splits mid-line unless a single line itself exceeds ``limit``. Returns
    an empty list for empty input. The concatenation of the chunks equals the input.
    """
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]
