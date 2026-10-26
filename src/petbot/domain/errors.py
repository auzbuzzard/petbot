from __future__ import annotations


class SkillError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInput(SkillError):
    """The arguments don't make sense (an empty query, a missing level)."""


class EmptyResult(SkillError):
    """A search or lookup that ran cleanly but found nothing."""


class UpstreamUnavailable(SkillError):
    """A remote service the skill depends on didn't answer."""
