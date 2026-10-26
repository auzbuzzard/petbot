"""Shared reading of AWS SDK errors, without importing botocore (an optional extra)."""

from __future__ import annotations


def aws_error_code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    code = response.get("Error", {}).get("Code")
    return code if isinstance(code, str) else None
