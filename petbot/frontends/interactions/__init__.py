"""HTTP-Interactions frontend.

The stateless counterpart to the gateway adapter in
:mod:`petbot.frontends.discord`. Discord POSTs each slash command to a URL; this
adapter verifies the request signature, maps the interaction onto a neutral
:class:`~petbot.core.skills.context.SkillContext`, runs the skill via the shared
:class:`~petbot.core.skills.registry.SkillRegistry`, and renders the
:class:`~petbot.core.skills.context.SkillResult` back as interaction-response
JSON.

It imports **no** ``discord`` (it emits raw JSON), so it runs on minimal
serverless runtimes. See ``docs/adr/0005-serverless-deployment.md``.
"""

from __future__ import annotations

from petbot.frontends.interactions.app import build_handler, lambda_handler
from petbot.frontends.interactions.handler import InteractionHandler

__all__ = ["InteractionHandler", "build_handler", "lambda_handler"]
