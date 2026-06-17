"""Assemble the core worker: math + booru search + the chat agent.

The compute side for everything that isn't voice. Math and the booru skills are
discovered from their entry points; the chat skill is built explicitly with a
``SkillsClient`` over a ``LocalTransport`` bound to this same worker, so its LLM
tools call their siblings in-process (no wire hop), then registered.
"""

from __future__ import annotations

from petbot.platform import LocalTransport, SkillsClient, Worker
from petbot.skills.chat import ChatSkill


def build_worker() -> Worker:
    """Build the core worker with chat wired to its sibling skills."""
    worker = Worker.from_installed_skills()  # math, derpi, e621 (entry points)
    worker.register(ChatSkill(SkillsClient(LocalTransport(worker))))
    return worker
