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


def test_chunk_text_short_is_single_chunk() -> None:
    assert render.chunk_text("hello") == ["hello"]


def test_chunk_text_empty_is_no_chunks() -> None:
    assert render.chunk_text("") == []


def test_chunk_text_splits_on_newlines_within_limit() -> None:
    text = "\n".join(["line"] * 100)  # 100 lines of 4 chars + newlines
    chunks = render.chunk_text(text, limit=50)
    assert all(len(chunk) <= 50 for chunk in chunks)
    assert "".join(chunks) == text


def test_chunk_text_hard_splits_overlong_line() -> None:
    text = "x" * 130
    chunks = render.chunk_text(text, limit=50)
    assert [len(c) for c in chunks] == [50, 50, 30]
    assert "".join(chunks) == text
