"""JSON wire format for the edge -> worker hop.

A ``DispatchRequest`` is serialised by the edge, sent to the worker, and run;
the ``SkillResult`` is serialised back. Live ports (``SkillContext.voice``) do
**not** cross the wire — a port-needing skill runs in a worker that reconstructs
the port locally, so the brain worker (stateless skills) never sees one.
"""

from __future__ import annotations

import dataclasses
import json

from petbot_domain import (
    DispatchRequest,
    EmbedSpec,
    Platform,
    SkillContext,
    SkillResult,
    User,
)


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object, got {type(value).__name__}")
    return value


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


def _opt_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raise ValueError(f"expected an integer, got {type(value).__name__}")


# --- request --------------------------------------------------------------


def request_to_dict(request: DispatchRequest) -> dict[str, object]:
    ctx = request.context
    return {
        "skill": request.skill,
        "args": dict(request.args),
        "context": {
            "platform": ctx.platform.value,
            "user": {
                "platform": ctx.user.platform.value,
                "id": ctx.user.id,
                "display_name": ctx.user.display_name,
            },
            "conversation_id": ctx.conversation_id,
            "allows_explicit": ctx.allows_explicit,
            "max_text_length": ctx.max_text_length,
        },
    }


def request_from_dict(data: dict[str, object]) -> DispatchRequest:
    ctx = _as_dict(data["context"])
    user = _as_dict(ctx["user"])
    context = SkillContext(
        platform=Platform(str(ctx["platform"])),
        user=User(
            platform=Platform(str(user["platform"])),
            id=str(user["id"]),
            display_name=str(user["display_name"]),
        ),
        conversation_id=str(ctx["conversation_id"]),
        allows_explicit=bool(ctx.get("allows_explicit", False)),
        max_text_length=_opt_int(ctx.get("max_text_length")) or 2000,
    )
    return DispatchRequest(skill=str(data["skill"]), args=_as_dict(data["args"]), context=context)


# --- result ---------------------------------------------------------------


def result_to_dict(result: SkillResult) -> dict[str, object]:
    return {
        "text": result.text,
        "embed": dataclasses.asdict(result.embed) if result.embed else None,
        "files": list(result.files),
        "error": result.error,
    }


def _embed_from_dict(data: dict[str, object]) -> EmbedSpec:
    return EmbedSpec(
        title=_opt_str(data.get("title")),
        description=_opt_str(data.get("description")),
        url=_opt_str(data.get("url")),
        color=_opt_int(data.get("color")),
        image_url=_opt_str(data.get("image_url")),
        author_name=_opt_str(data.get("author_name")),
        author_url=_opt_str(data.get("author_url")),
        author_icon_url=_opt_str(data.get("author_icon_url")),
    )


def result_from_dict(data: dict[str, object]) -> SkillResult:
    embed_data = data.get("embed")
    files_data = data.get("files") or []
    if not isinstance(files_data, list):
        raise ValueError("'files' must be a list")
    return SkillResult(
        text=_opt_str(data.get("text")),
        embed=_embed_from_dict(_as_dict(embed_data)) if embed_data else None,
        files=tuple(str(f) for f in files_data),
        error=_opt_str(data.get("error")),
    )


# --- json strings ---------------------------------------------------------


def dump_request(request: DispatchRequest) -> str:
    return json.dumps(request_to_dict(request))


def load_request(text: str) -> DispatchRequest:
    return request_from_dict(_as_dict(json.loads(text)))


def dump_result(result: SkillResult) -> str:
    return json.dumps(result_to_dict(result))


def load_result(text: str) -> SkillResult:
    return result_from_dict(_as_dict(json.loads(text)))
