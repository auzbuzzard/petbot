"""Guardrails for the interactions slash-command definitions and registration.

The command specs in :mod:`petbot.frontends.interactions.commands` are authored
by hand (Discord's schema), so these tests keep them honest against the two
things that can drift out from under them: the set of skills the interactions
frontend actually exposes, and each skill's ``input_schema``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from petbot.core.skills.booru_skill import DerpiSkill, E621Skill
from petbot.core.skills.math_skill import MathSkill
from petbot.core.skills.music_skill import MusicSkill
from petbot.core.skills.registry import SkillRegistry
from petbot.frontends.interactions.app import INTERACTIONS_CAPABILITIES
from petbot.frontends.interactions.commands import COMMANDS
from petbot.frontends.interactions.register import API_BASE, RegisterError, register


# Skills wired into the interactions handler (mirrors app.build_handler), used to
# derive the expected command surface from the real registry rather than a
# hand-maintained list.
async def _interactions_skill_names() -> set[str]:
    async with httpx.AsyncClient() as client:
        registry = SkillRegistry(
            [
                MathSkill(),
                DerpiSkill(client=client),
                E621Skill(client=client, user_agent="test"),
                MusicSkill(),
            ]
        )
        return {skill.name for skill in registry.available_for(INTERACTIONS_CAPABILITIES)}


# input_schema lives on the skill *class*, so no instance/client is needed here.
_SCHEMA_BY_NAME: dict[str, Any] = {
    "math": MathSkill.input_schema,
    "derpi": DerpiSkill.input_schema,
    "e621": E621Skill.input_schema,
}


async def test_commands_cover_exactly_the_interactions_surface() -> None:
    names = {command["name"] for command in COMMANDS}
    # Every interactions-available skill is registered, plus the adapter-level
    # /ping — and nothing else (so /music, which is voice-gated, stays absent).
    assert names == await _interactions_skill_names() | {"ping"}


def test_ping_takes_no_options() -> None:
    (ping,) = (command for command in COMMANDS if command["name"] == "ping")
    assert ping["options"] == []


def test_options_match_each_skill_schema() -> None:
    for command in COMMANDS:
        if command["name"] == "ping":
            continue
        schema = _SCHEMA_BY_NAME[command["name"]]
        option_names = {option["name"] for option in command["options"]}
        required_names = {opt["name"] for opt in command["options"] if opt.get("required")}

        # Every option must be a real schema property, and the required options
        # must be exactly the schema's required keys.
        assert option_names <= set(schema["properties"])
        assert required_names == set(schema["required"])


def test_required_options_precede_optional() -> None:
    # Discord rejects a command whose required options come after an optional one.
    for command in COMMANDS:
        seen_optional = False
        for option in command["options"]:
            if option.get("required"):
                assert not seen_optional, f"{command['name']}: required option after optional"
            else:
                seen_optional = True


@respx.mock
def test_register_targets_the_guild_endpoint_when_a_guild_is_given() -> None:
    route = respx.put(f"{API_BASE}/applications/app123/guilds/guild456/commands").mock(
        return_value=httpx.Response(200, json=COMMANDS)
    )
    result = register("app123", "tok", guild_id="guild456")

    assert route.called
    assert route.calls.last.request.headers["Authorization"] == "Bot tok"
    assert len(result) == len(COMMANDS)


@respx.mock
def test_register_targets_the_global_endpoint_without_a_guild() -> None:
    route = respx.put(f"{API_BASE}/applications/app123/commands").mock(
        return_value=httpx.Response(200, json=COMMANDS)
    )
    register("app123", "tok")

    assert route.called


@respx.mock
def test_register_raises_on_a_discord_error() -> None:
    respx.put(f"{API_BASE}/applications/app123/commands").mock(
        return_value=httpx.Response(403, json={"message": "Missing Access", "code": 50001})
    )
    with pytest.raises(RegisterError, match="403"):
        register("app123", "tok")
