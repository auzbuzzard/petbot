"""The ``music`` skill package.

No auto-discovery entry point: the skill requires a live
:class:`~petbot.domain.ports.VoiceProvider`, so the music worker builds it
explicitly (with its gateway-backed provider) rather than via zero-arg discovery.
"""

from __future__ import annotations

from petbot.skills.music.skill import MusicSkill

__all__ = ["MusicSkill"]
