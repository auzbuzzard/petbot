"""PetBot platform: the compute plumbing — registry, transports, serve, client.

:class:`ToolRegistry` holds the tools a process can call; :func:`serve` is the remote
boundary that runs a :class:`~petbot.domain.process.Process` behind a transport;
:class:`ProcessClient` is the frontend's handle to a process; :class:`HttpTransport` /
:class:`LambdaTransport` carry a :class:`Dispatch` to it; :func:`report` / :func:`observe`
pass a turn's :class:`Phase` from the transport to the caller waiting on it.
Platform-agnostic: it knows no skill, no frontend, and no concrete process impl.
"""

from __future__ import annotations

from petbot.platform.client import ProcessClient
from petbot.platform.dedup import ClaimingProcess, ClaimStore, DynamoClaims
from petbot.platform.dispatch import Dispatch, Transport
from petbot.platform.progress import Phase, observe, report
from petbot.platform.registry import SKILLS_GROUP, ToolRegistry
from petbot.platform.serve import serve
from petbot.platform.transport import HttpTransport, LambdaTransport

__all__ = [
    "SKILLS_GROUP",
    "ClaimStore",
    "ClaimingProcess",
    "Dispatch",
    "DynamoClaims",
    "HttpTransport",
    "LambdaTransport",
    "Phase",
    "ProcessClient",
    "ToolRegistry",
    "Transport",
    "observe",
    "report",
    "serve",
]
