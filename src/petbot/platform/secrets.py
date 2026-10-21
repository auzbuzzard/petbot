"""Read a process's secrets from SSM when it starts, so no secret value is deployed.

The deployment hands each process only the *names* of its secrets: ``SSM_SECRETS`` is a
JSON object of environment-variable name to SSM SecureString parameter name, e.g.
``{"CHAT_LLM__API_KEY": "/petbot/core/bedrock_api_key"}``. :func:`load_ssm_secrets` reads
those parameters (decrypted) and sets each variable, so the settings classes go on reading
``os.environ`` as before and a local run without ``SSM_SECRETS`` is unaffected. The values
never pass through the function's configuration or Terraform state.

Call it once, at the entrypoint, before any settings are read. A variable that is already
set is left as it is. A name SSM doesn't know fails start-up rather than leaving the process
to run without its secret.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping, MutableMapping
from typing import Any

logger = logging.getLogger(__name__)

#: The environment variable carrying the name map.
SSM_SECRETS = "SSM_SECRETS"

#: GetParameters accepts at most this many names per call.
_BATCH = 10


def _parameter_map(raw: str) -> dict[str, str]:
    names = json.loads(raw)
    if not isinstance(names, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v for k, v in names.items()
    ):
        raise ValueError(f"{SSM_SECRETS} must be a JSON object of variable name to parameter name")
    return names


def load_ssm_secrets(
    environ: MutableMapping[str, str] | None = None, *, client: Any = None
) -> list[str]:
    """Set each variable ``SSM_SECRETS`` names from its SSM parameter; return the names set.

    ``environ`` defaults to ``os.environ``; ``client`` to a boto3 SSM client (boto3 is
    imported only when there is something to read).
    """
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    raw = env.get(SSM_SECRETS, "").strip()
    if not raw:
        return []
    wanted = {var: name for var, name in _parameter_map(raw).items() if not env.get(var)}
    if not wanted:
        return []
    if client is None:
        import boto3

        client = boto3.client("ssm")
    values = _get_parameters(client, sorted(set(wanted.values())))
    for var, name in wanted.items():
        env[var] = values[name]
    logger.info("loaded %d secret(s) from SSM", len(wanted))
    return sorted(wanted)


def _get_parameters(client: Any, names: list[str]) -> Mapping[str, str]:
    values: dict[str, str] = {}
    missing: list[str] = []
    for start in range(0, len(names), _BATCH):
        response = client.get_parameters(Names=names[start : start + _BATCH], WithDecryption=True)
        values.update({p["Name"]: p["Value"] for p in response.get("Parameters", [])})
        missing.extend(response.get("InvalidParameters", []))
    if missing:
        raise RuntimeError(f"SSM has no parameter named: {', '.join(sorted(missing))}")
    return values
