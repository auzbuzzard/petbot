"""PetBot platform: the compute plumbing — registry, transports, serve, client.

:class:`ToolRegistry` holds the tools a process can call; :func:`serve` is the remote
boundary that runs a :class:`~petbot.domain.process.Process` behind a transport;
:class:`ProcessClient` is the frontend's handle to a process; :class:`HttpTransport` /
:class:`LambdaTransport` carry a :class:`Dispatch` to it. Platform-agnostic: it knows
no skill, no frontend, and no concrete process impl.
"""

from __future__ import annotations

from petbot.platform.client import ProcessClient
from petbot.platform.dispatch import Dispatch, Transport
from petbot.platform.registry import SKILLS_GROUP, ToolRegistry
from petbot.platform.serve import serve
from petbot.platform.transport import HttpTransport, LambdaTransport

__all__ = [
    "SKILLS_GROUP",
    "Dispatch",
    "HttpTransport",
    "LambdaTransport",
    "ProcessClient",
    "ToolRegistry",
    "Transport",
    "serve",
]
