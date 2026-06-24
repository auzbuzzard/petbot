"""Skill errors — expected failures, *raised* not returned.

A skill signals an expected failure (an empty search, bad input, a site that won't
answer) by **raising** a :class:`SkillError` carrying a plain, user-facing message.
The exception propagates uncaught up to the process output boundary, which catches it
once, voices the message in PetBot's persona (a :class:`~petbot.domain.ports.StylePort`),
and returns it as the result. A skill never builds a failure result itself — it raises
and lets the boundary present it. An *unexpected* exception is caught at the same
boundary and shown as a generic line, so PetBot always answers.
"""

from __future__ import annotations


class SkillError(Exception):
    """An expected skill failure carrying a plain, user-facing ``message``.

    Subclasses name the *kind* of failure so the output boundary (or a test) can tell
    them apart; the boundary voices ``message`` in persona regardless.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInput(SkillError):
    """The arguments don't make sense (an empty query, a missing level)."""


class EmptyResult(SkillError):
    """A search or lookup that ran cleanly but found nothing.

    ``reason`` is an optional machine-readable tag (a plain string so the domain stays
    provider-agnostic) letting the skill layer classify *why* it was empty for telemetry,
    without re-deriving it. ``None`` when the caller has no finer signal than the message.
    """

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason


class UpstreamUnavailable(SkillError):
    """A remote service the skill depends on didn't answer."""
