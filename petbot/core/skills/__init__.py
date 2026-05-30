"""Skills: the neutral units of behavior the bot can perform.

A skill takes a :class:`~petbot.core.skills.context.SkillContext` plus an
argument mapping and returns a :class:`~petbot.core.skills.context.SkillResult`.
It knows nothing about Discord; adapters build the context and render the result.
"""

from __future__ import annotations
