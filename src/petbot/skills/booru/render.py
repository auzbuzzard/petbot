"""Turn a :class:`Post` into a neutral :class:`SkillResult`.

This is the one place that knows how a result is presented, and it knows nothing
about ratings beyond the resolved ``color``/``is_safe`` already on the ``Post``.
The randomized, in-character greeter lives here too (it reads ``utterances.json``
shipped alongside this package).
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Mapping, Sequence
from functools import lru_cache
from importlib import resources
from typing import Any

from petbot.domain import EmbedSpec, SkillResult
from petbot.skills.booru.types import Post, SearchRequest

logger = logging.getLogger(__name__)

_UTTERANCES_RESOURCE = "utterances.json"


def render(post: Post | None, *, request: SearchRequest, author: str) -> SkillResult:
    """Render a search outcome. ``post is None`` is an ordinary empty result."""
    if post is None:
        return SkillResult.message(
            result_greeter(has_image=False, is_explicit=not request.safe_only, author=author)
        )

    greeter = result_greeter(has_image=True, is_explicit=not post.is_safe, author=author)
    if post.total is not None:
        title = f"{post.total} result{'s' if post.total != 1 else ''}: {tags_label(request.tags)}"
    else:
        title = f"results: {tags_label(request.tags)}"
    description = (
        f"score: {post.score} | faves: {post.favorites} | "
        f"source: [{post.site_name}]({post.page_url}) | filetype: {post.file_ext}"
    )
    embed = EmbedSpec(
        title=title,
        description=description,
        url=post.page_url,
        color=post.color,
        image_url=post.image_url,
        author_name=post.site_name,
        author_url=post.site_root,
        author_icon_url=post.site_icon_url,
    )
    return SkillResult.message(greeter, embed=embed)


def tags_label(tags: Sequence[str], *, limit: int = 256) -> str:
    """A comma-joined tag label, truncated to ``limit`` characters."""
    label = ", ".join(tags)
    if len(label) <= limit:
        return label
    truncated: list[str] = []
    used = 0
    for tag in tags:
        if used + len(tag) + 2 > limit:
            break
        truncated.append(tag)
        used += len(tag) + 2
    return ", ".join(truncated) + " …"


@lru_cache(maxsize=1)
def _load_utterances() -> Mapping[str, Any]:
    text = resources.files(__package__).joinpath(_UTTERANCES_RESOURCE).read_text(encoding="utf-8")
    parsed: Mapping[str, Any] = json.loads(text)
    return parsed


def result_greeter(*, has_image: bool, is_explicit: bool, author: str) -> str:
    """Return a randomized, in-character greeting for a search result.

    ``author`` is a plain display name (no Discord objects), keeping this neutral.
    """
    try:
        greeter = _load_utterances()["image_result_greeter"]
        bucket = greeter["success"] if has_image else greeter["no_image"]
        sentences: list[str] = list(bucket["universal"])
        sentences += bucket["explicit"] if is_explicit else bucket["safe"]
        return random.choice(sentences).format(author=author)
    except (OSError, KeyError, ValueError):
        logger.warning("Falling back to default greeter (utterances unavailable)", exc_info=True)
        return "I have found this image." if has_image else "I couldn't find anything."
