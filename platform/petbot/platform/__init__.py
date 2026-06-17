"""PetBot platform: the worker runtime and the typed skill-client implementations.

:class:`Worker` hosts skills and runs a dispatched call; :class:`RemoteSkills` /
:class:`LocalSkills` are the :class:`petbot.types.Skills` client implementations;
:class:`HttpTransport` / :class:`LambdaTransport` move a call to a worker.
"""

from __future__ import annotations

from petbot.platform.skills import LocalSkills, RemoteSkills
from petbot.platform.transport import HttpTransport, LambdaTransport
from petbot.platform.worker import SKILLS_GROUP, Worker

__all__ = [
    "SKILLS_GROUP",
    "HttpTransport",
    "LambdaTransport",
    "LocalSkills",
    "RemoteSkills",
    "Worker",
]
