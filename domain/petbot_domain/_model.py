"""Shared base for the kernel's immutable value models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    """An immutable pydantic model — the base for every kernel value object."""

    model_config = ConfigDict(frozen=True)
