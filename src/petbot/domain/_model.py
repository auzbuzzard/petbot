"""The shared pydantic base for every neutral domain model.

Frozen (immutable, hashable) and strict-ish: extra fields are rejected so a
malformed wire payload fails loudly instead of silently dropping data. Every
value object a frontend and a compute service exchange derives from this, which is what
lets them serialise themselves with ``model_dump_json`` / ``model_validate_json``
— no hand-rolled wire layer anywhere.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    """Immutable pydantic base: frozen, forbids unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")
