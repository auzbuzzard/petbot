"""The core compute service: chat + command over the stateless skills.

Composes the process core for everything that isn't voice: a
:class:`~petbot.platform.registry.ToolRegistry` of the installed skills (math, booru, web
search/fetch and weather, from their entry points), a
:class:`~petbot.process.ChatProcess` (its agent calls those tools in-process), and a
:class:`~petbot.process.CommandProcess` voiced by a :class:`~petbot.process.Stylist`,
behind one :class:`~petbot.process.RouterProcess`. With ``CLAIMS_TABLE`` set (the Lambda
deployment), a :class:`~petbot.platform.ClaimingProcess` in front answers each request id
once, however many frontends deliver it.
Served behind a transport by :mod:`petbot.services.core.handler` (Lambda) or
``python -m petbot.services.core`` (dev HTTP).
"""

from __future__ import annotations

from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_settings import BaseSettings, SettingsConfigDict

from petbot.domain import Process
from petbot.observability import ObservabilitySettings
from petbot.platform import ClaimingProcess, DynamoClaims, ToolRegistry
from petbot.process import ChatProcess, CommandProcess, RouterProcess, Stylist
from petbot.process.settings import ChatSettings


class CoreSettings(BaseSettings):
    """Deployment wiring for the core service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    #: The DynamoDB table of claimed request ids (``CLAIMS_TABLE``); unset ⇒ no claiming.
    claims_table: str | None = None


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
    registry = ToolRegistry.from_installed_skills()
    chat = ChatProcess(
        registry, settings=settings, instrumentation=instrumentation, id_salt=obs.id_salt
    )
    command = CommandProcess(registry, Stylist(settings=settings))
    router = RouterProcess(chat=chat, command=command)
    table = CoreSettings().claims_table
    return ClaimingProcess(router, DynamoClaims.from_table_name(table)) if table else router


__all__ = ["CoreSettings", "build_process"]
