"""The core compute service: chat + command over the stateless skills.

Composes the process core for everything that isn't voice: a
:class:`~petbot.platform.registry.ToolRegistry` of the installed skills (math + booru,
from their entry points), a :class:`~petbot.process.ChatProcess` (its agent calls those
tools in-process), and a :class:`~petbot.process.CommandProcess` voiced by a
:class:`~petbot.process.Stylist`, behind one :class:`~petbot.process.RouterProcess`.
Served behind a transport by :mod:`petbot.services.core.handler` (Lambda) or
``python -m petbot.services.core`` (dev HTTP).
"""

from __future__ import annotations

from pydantic_ai.models.instrumented import InstrumentationSettings

from petbot.domain import Process
from petbot.observability import ObservabilitySettings
from petbot.platform import ToolRegistry
from petbot.process import ChatProcess, CommandProcess, RouterProcess, Stylist
from petbot.process.settings import ChatSettings


def build_process() -> Process:
    """Build the core service's process: chat + command over the installed skills.

    The entrypoint has already called ``configure_observability`` (so the global OTel
    providers exist); here we only decide whether to instrument the agent. When telemetry
    is enabled the chat agent emits spans/metrics with ``include_content=False`` (metadata
    only), and the chat process tags its run-outcome record with a salted user-id hash.
    """
    settings = ChatSettings()
    obs = ObservabilitySettings()
    instrumentation = (
        InstrumentationSettings(version=3, include_content=False) if obs.enabled else None
    )
    registry = ToolRegistry.from_installed_skills()  # math, derpi, e621
    chat = ChatProcess(
        registry, settings=settings, instrumentation=instrumentation, id_salt=obs.id_salt
    )
    command = CommandProcess(registry, Stylist(settings=settings))
    return RouterProcess(chat=chat, command=command)


__all__ = ["build_process"]
