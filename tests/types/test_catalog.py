"""The command catalog: typed entries the slash surface and the agent both derive from."""

from __future__ import annotations

from petbot.types import CATALOG
from petbot.types.args import BooruArgs, MathArgs


def test_catalog_holds_the_command_skills_only() -> None:
    names = {c.name for c in CATALOG}
    assert names == {"math", "derpi", "e621"}
    # music (a separate service) and chat (the process itself) are absent by design.
    assert "music" not in names and "chat" not in names


def test_catalog_binds_each_name_to_its_args_model() -> None:
    by_name = {c.name: c for c in CATALOG}
    assert by_name["math"].args_model is MathArgs
    assert by_name["derpi"].args_model is BooruArgs
    assert by_name["e621"].args_model is BooruArgs
