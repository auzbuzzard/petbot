"""Assemble the brain worker: math + booru search + the chat agent.

This is the compute side of A3a for everything that isn't voice. Math and the
booru skills are discovered from their entry points; the chat skill is built
explicitly with a ``LocalSkills`` bound to this same worker, so its LLM tools call
its siblings in-process (no wire hop) before being registered.
"""

from __future__ import annotations

from petbot.platform import LocalSkills, Worker
from petbot.skills.chat import ChatSkill


def build_worker() -> Worker:
    """Build the brain worker with chat wired to its sibling skills."""
    worker = Worker.from_installed_skills()  # math, derpi, e621 (entry points)
    worker.register(ChatSkill(LocalSkills(worker)))
    return worker
