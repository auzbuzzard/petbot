"""Discord HTTP-Interactions wire-protocol constants.

The numeric type codes Discord uses on the interaction request/response wire.
Kept in one place so the handler reads declaratively.
See https://discord.com/developers/docs/interactions/receiving-and-responding.
"""

from __future__ import annotations

from typing import Final

# --- Interaction request types (the ``type`` field Discord sends) ---
PING: Final = 1
APPLICATION_COMMAND: Final = 2

# --- Interaction response types (the ``type`` field we send back) ---
PONG: Final = 1
CHANNEL_MESSAGE_WITH_SOURCE: Final = 4
DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE: Final = 5
