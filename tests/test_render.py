"""Tests for the Discord render helpers (pure; no gateway needed)."""

from __future__ import annotations

from petbot.core.skills.context import EmbedSpec
from petbot.frontends.discord import render


def test_to_embed_maps_all_fields() -> None:
    spec = EmbedSpec(
        title="t",
        description="d",
        url="https://example.com",
        color=0x00FF00,
        image_url="https://example.com/i.png",
        author_name="Derpibooru",
        author_url="https://derpibooru.org/",
        author_icon_url="https://example.com/icon.png",
    )
    embed = render.to_embed(spec)
    assert embed.title == "t"
    assert embed.description == "d"
    assert embed.url == "https://example.com"
    assert embed.color is not None and embed.color.value == 0x00FF00
    assert embed.image.url == "https://example.com/i.png"
    assert embed.author.name == "Derpibooru"
