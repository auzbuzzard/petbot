"""PetBot platform: the worker runtime, the typed ``Skills`` client, and transports.

:class:`Worker` hosts skills and runs a dispatched call; :class:`SkillsClient` is
the one typed client; :class:`LocalTransport` / :class:`HttpTransport` /
:class:`LambdaTransport` move a call to a worker.
"""

from __future__ import annotations

from petbot.platform.client import SkillsClient
from petbot.platform.transport import HttpTransport, LambdaTransport, LocalTransport
from petbot.platform.worker import SKILLS_GROUP, Worker

__all__ = [
    "SKILLS_GROUP",
    "HttpTransport",
    "LambdaTransport",
    "LocalTransport",
    "SkillsClient",
    "Worker",
]
