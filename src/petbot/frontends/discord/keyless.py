"""Startup probe: can the Lightsail container's own AWS identity replace the edge's static key?

Runs only when ``KEYLESS_PROBE`` names the service's principal ARNs (a JSON object of
label to ARN). It logs outcomes only, never an ARN or a credential.
"""

from __future__ import annotations

import json
import logging
import os

from petbot.platform._aws import aws_error_code

logger = logging.getLogger(__name__)

_CONTAINER_URI_VARS = (
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
)


def role_identity(arn: str) -> tuple[str, str] | None:
    """(account, role name) of an IAM role ARN or an STS assumed-role ARN."""
    parts = arn.split(":", 5)
    if len(parts) != 6:
        return None
    account, resource = parts[4], parts[5]
    if resource.startswith("role/"):
        return account, resource.rsplit("/", 1)[-1]
    if resource.startswith("assumed-role/"):
        return account, resource.split("/")[1]
    return None


def probe_container_identity() -> None:
    raw = os.environ.get("KEYLESS_PROBE")
    if not raw:
        return
    expected: dict[str, str] = json.loads(raw)
    present = any(os.environ.get(name) for name in _CONTAINER_URI_VARS)
    logger.info("keyless-probe: container credentials %s", "present" if present else "absent")
    if not present:
        return
    try:
        import boto3
        from botocore.credentials import ContainerProvider

        creds = ContainerProvider().load()
        if creds is None:
            logger.info("keyless-probe: container credentials did not load")
            return
        frozen = creds.get_frozen_credentials()
        sts = boto3.client(
            "sts",
            aws_access_key_id=frozen.access_key,
            aws_secret_access_key=frozen.secret_key,
            aws_session_token=frozen.token,
        )
        caller = role_identity(sts.get_caller_identity()["Arn"])
    except Exception as exc:
        logger.info(
            "keyless-probe: caller identity failed: %s", aws_error_code(exc) or type(exc).__name__
        )
        return
    for label, arn in expected.items():
        verdict = (
            "matches" if caller is not None and caller == role_identity(arn) else "differs from"
        )
        logger.info("keyless-probe: caller identity %s the %s principal", verdict, label)
