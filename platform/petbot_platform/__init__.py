"""PetBot runtime: skill discovery, registry, manifest, worker, and wire format.

A *worker* (:class:`Worker`) loads its installed skills and runs the one named in
a dispatched request. An *edge* uses :mod:`.manifest` to read skill descriptions
without importing skills, and :mod:`.wire` to serialise the request/result across
the edge→worker hop. That hop is a ``DispatchPort`` (defined in ``petbot_domain``);
its concrete, remote implementation ships with the edge.
"""

from __future__ import annotations

from petbot_platform.loader import SKILLS_GROUP, build_registry, load_skills
from petbot_platform.manifest import dumps, from_manifest, loads, to_manifest
from petbot_platform.registry import SkillNotFoundError, SkillRegistry
from petbot_platform.wire import (
    dump_request,
    dump_result,
    load_request,
    load_result,
    request_from_dict,
    request_to_dict,
    result_from_dict,
    result_to_dict,
)
from petbot_platform.worker import Worker

__all__ = [
    "SKILLS_GROUP",
    "SkillNotFoundError",
    "SkillRegistry",
    "Worker",
    "build_registry",
    "dump_request",
    "dump_result",
    "dumps",
    "from_manifest",
    "load_request",
    "load_result",
    "load_skills",
    "loads",
    "request_from_dict",
    "request_to_dict",
    "result_from_dict",
    "result_to_dict",
    "to_manifest",
]
