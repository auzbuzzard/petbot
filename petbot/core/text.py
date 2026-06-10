"""Platform-neutral text utilities.

:func:`chunk_text` is dependency-pure (no platform types), so it lives in the
core and is shared by every frontend that has a per-message length cap — rather
than being duplicated per adapter.
"""

from __future__ import annotations

#: A sensible default cap (matches Discord's message limit); callers may override.
DEFAULT_CHUNK_LIMIT = 2000


def chunk_text(text: str, *, limit: int = DEFAULT_CHUNK_LIMIT) -> list[str]:
    """Split ``text`` into chunks no longer than ``limit``, preferring newlines.

    Never splits mid-line unless a single line itself exceeds ``limit``. Returns
    an empty list for empty input. The concatenation of the chunks always equals
    the input.
    """
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            # A single over-long line: hard-split it.
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
