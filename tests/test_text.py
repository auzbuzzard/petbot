"""Tests for the neutral text utilities (pure; shared by every frontend)."""

from __future__ import annotations

from petbot.core.text import chunk_text


def test_short_text_is_single_chunk() -> None:
    assert chunk_text("hello") == ["hello"]


def test_empty_text_is_no_chunks() -> None:
    assert chunk_text("") == []


def test_splits_on_newlines_within_limit() -> None:
    text = "\n".join(["line"] * 100)  # 100 lines of 4 chars + newlines
    chunks = chunk_text(text, limit=50)
    assert all(len(chunk) <= 50 for chunk in chunks)
    assert "".join(chunks) == text


def test_hard_splits_an_overlong_line() -> None:
    text = "x" * 130
    chunks = chunk_text(text, limit=50)
    assert [len(c) for c in chunks] == [50, 50, 30]
    assert "".join(chunks) == text
