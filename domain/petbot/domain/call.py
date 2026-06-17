"""The wire primitives: the dispatch envelope and the transport port.

A :class:`SkillCall` is exactly what crosses the edge -> worker boundary: the
target skill's name, its arguments pre-serialised as JSON, and the neutral
:class:`~petbot.domain.context.SkillContext`. The args ride as an opaque
``args_json`` string here — the kernel never needs to know a skill's argument
shape; the worker re-validates it against that skill's ``args_model``.

A :class:`Transport` is the single verb that moves a call to the worker and
returns its result, with one implementation per mechanism (HTTP, Lambda). The
typed :class:`~petbot.platform.skills.RemoteSkills` client wraps a transport so
callers never see ``SkillCall`` or the skill-name string.
"""

from __future__ import annotations

from typing import Protocol

from petbot.domain._model import Frozen
from petbot.domain.context import SkillContext
from petbot.domain.result import SkillResult


class SkillCall(Frozen):
    """A unit of work the edge hands to a worker over a :class:`Transport`."""

    skill: str
    #: The skill's arguments, already serialised (``args_model.model_dump_json``).
    #: Opaque to the kernel; the worker re-validates it against ``args_model``.
    args_json: str
    context: SkillContext


class Transport(Protocol):
    """Moves a :class:`SkillCall` to the worker that hosts the skill and returns its result."""

    async def send(self, call: SkillCall) -> SkillResult:
        """Dispatch ``call`` and return the worker's :class:`SkillResult`."""
        ...
