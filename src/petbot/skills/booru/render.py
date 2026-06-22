"""Turn a :class:`Post` into a neutral :class:`SkillResult`.

This is the one place that knows how a result is presented, and it knows nothing
about ratings beyond the resolved ``color``/``is_safe`` already on the ``Post``.

The outcome is modelled, not stringly-typed: a found post becomes a card with no
greeting text (the persona layer greets over it), and an empty search **raises**
:class:`~petbot.domain.errors.EmptyResult` carrying the factual reason. The voice —
greeting or relaying that reason — is added downstream (the chat agent, or the command
process's stylist), never shipped from here.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from petbot.domain import EmbedSpec, EmptyResult, SkillResult
from petbot.skills.booru.types import Post, SearchRequest


class EmptyReason(StrEnum):
    """Why a search came back empty — the fact the persona layer relays."""

    #: A safe-only search (the channel isn't age-gated) found nothing.
    SAFE_FLOOR = "safe_floor"
    #: A search that looked at everything available found nothing.
    NO_MATCH = "no_match"


#: One factual note per reason. Stated plainly so whoever voices it (chat agent or
#: stylist) relays the real reason instead of inventing one (a typo, etc.).
_EMPTY_NOTE: dict[EmptyReason, str] = {
    EmptyReason.SAFE_FLOOR: (
        "No results. This channel isn't age-gated, so only safe-rated posts were "
        "searched — there may be more in an NSFW channel."
    ),
    EmptyReason.NO_MATCH: "No results found for those tags.",
}


def render(post: Post | None, *, request: SearchRequest) -> SkillResult:
    """Render a found post. An empty search **raises** :class:`EmptyResult`, whose factual
    note the process output boundary voices in persona."""
    if post is None:
        reason = EmptyReason.SAFE_FLOOR if request.safe_only else EmptyReason.NO_MATCH
        raise EmptyResult(_EMPTY_NOTE[reason])

    if post.total is not None:
        title = f"{post.total} result{'s' if post.total != 1 else ''}: {tags_label(request.tags)}"
    else:
        title = f"result for: {tags_label(request.tags)}"
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
    # No greeting text: the card is the content, and the persona layer greets over it.
    return SkillResult.message(embed=embed)


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
