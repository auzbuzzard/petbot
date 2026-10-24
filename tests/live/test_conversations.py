"""Every conversation in ``conversations/``, through the deployed core's chat path.

The model decides each reply, so what it says isn't asserted; that the deployed core answers
each message is: no dispatch fails (the frontend's fallback reply), and every message sent to
PetBot gets a reply. The transcript goes to the job's summary for reading.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

import pytest

from petbot.frontends.discord.render import SERVICE_UNREACHABLE
from petbot.platform import ProcessClient
from petbot.services.core.chat import ChainSettings, Conversation, Deployed, replay

#: Read at collection, so no test reads a file while the event loop runs.
CONVERSATIONS: dict[str, Conversation] = {
    path.name: Conversation.model_validate_json(path.read_text(encoding="utf-8"))
    for path in sorted((Path(__file__).parents[2] / "conversations").glob("*.json"))
}


@pytest.mark.parametrize("name", list(CONVERSATIONS))
async def test_every_message_gets_a_reply(
    core: ProcessClient, record: Callable[[str, str], None], name: str
) -> None:
    conversation = CONVERSATIONS[name]
    out = io.StringIO()
    replies = await replay(
        Deployed(core), conversation, out, max_turns=ChainSettings().history_max_turns
    )
    record(f"conversations/{name}", out.getvalue())
    sent = [m for m in conversation.messages if m.to_bot]
    assert len(replies) == len(sent)
    assert SERVICE_UNREACHABLE not in replies, "a dispatch failed (the frontend's fallback)"
    assert all(r.strip() for r in replies), "a message got an empty reply"
