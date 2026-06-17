"""Edge <-> worker wire format.

Pydantic is the boundary adapter: it serialises/validates the kernel's plain
dataclasses, so there is no hand-rolled JSON mapping and the domain keeps no
pydantic dependency. JSON helpers (``*_json``) are for a string transport; dict
helpers are for a transport that already hands over a parsed object (a Lambda
event).
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import TypeAdapter

from petbot_domain import DispatchRequest, SkillResult

_REQUEST: TypeAdapter[DispatchRequest] = TypeAdapter(DispatchRequest)
_RESULT: TypeAdapter[SkillResult] = TypeAdapter(SkillResult)


def dump_request(request: DispatchRequest) -> str:
    return _REQUEST.dump_json(request).decode()


def load_request(text: str | bytes) -> DispatchRequest:
    return _REQUEST.validate_json(text)


def dump_result(result: SkillResult) -> str:
    return _RESULT.dump_json(result).decode()


def load_result(text: str | bytes) -> SkillResult:
    return _RESULT.validate_json(text)


def request_to_dict(request: DispatchRequest) -> dict[str, Any]:
    return cast(dict[str, Any], _REQUEST.dump_python(request, mode="json"))


def request_from_dict(data: dict[str, Any]) -> DispatchRequest:
    return _REQUEST.validate_python(data)


def result_to_dict(result: SkillResult) -> dict[str, Any]:
    return cast(dict[str, Any], _RESULT.dump_python(result, mode="json"))


def result_from_dict(data: dict[str, Any]) -> SkillResult:
    return _RESULT.validate_python(data)
