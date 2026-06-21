"""Assemble the core worker: math + booru search + the chat agent + the stylizer.

The compute side for everything that isn't voice transport. Math and the booru
skills are discovered from their entry points; the chat skill is built explicitly
with a ``SkillsClient`` over a ``LocalTransport`` bound to this same worker, so its
LLM tools call their siblings in-process (no wire hop). The persona for the LLM-free
slash path is a :class:`~petbot.domain.StyleProvider` (``LLMStyleProvider``) the
worker holds and applies per request — not a dispatched skill.
"""

from __future__ import annotations

from petbot.platform import LocalTransport, SkillsClient, Worker
from petbot.skills.chat import ChatSkill, LLMStyleProvider
from petbot.skills.chat.settings import ChatSettings


def build_worker() -> Worker:
    """Build the core worker with chat + the stylizer wired to their LLM config."""
    settings = ChatSettings()
    # math, derpi, e621 from entry points; the stylizer rides as the worker's
    # StyleProvider, applied to a result only when the request asked to be styled.
    worker = Worker.from_installed_skills(style_provider=LLMStyleProvider(settings))
    worker.register(ChatSkill(SkillsClient(LocalTransport(worker)), settings=settings))
    return worker
