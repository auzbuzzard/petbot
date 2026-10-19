"""Shared reading of AWS SDK errors, without importing botocore (an optional extra)."""

from __future__ import annotations


def aws_error_code(exc: BaseException) -> str | None:
    """The AWS error code of a botocore ``ClientError`` (read structurally, so botocore stays
    a lazy import), or ``None`` for anything else."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    code = response.get("Error", {}).get("Code")
    return code if isinstance(code, str) else None
