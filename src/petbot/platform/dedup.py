"""At-most-once turns: one answer per request, however many frontends deliver it.

The Discord frontend is a gateway client, and Discord delivers every event to every session
connected with the bot's token. Two sessions exist whenever a Lightsail deployment rolls
over (the new container connects before the old one stops) or a second copy runs anywhere
with the same token, and each would answer the same message. A frontend tags each request
with the platform's id for the event (:attr:`~petbot.domain.SkillContext.request_id`);
:class:`ClaimingProcess` lets the first delivery of an id through and answers every later
one with an empty result, which a frontend renders as nothing.

A claim is a conditional create in DynamoDB (:class:`DynamoClaims`): atomic, so exactly
one of two concurrent deliveries wins, and expired by the table's TTL. If the store fails,
the request is answered anyway: a rare duplicate beats a dropped message.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol

from petbot.domain import Input, Process, SkillContext, SkillResult
from petbot.platform._aws import aws_error_code

logger = logging.getLogger(__name__)


class ClaimStore(Protocol):
    """Records which requests have already been taken."""

    async def claim(self, request_id: str) -> bool:
        """Take ``request_id``: ``True`` for the first caller, ``False`` for every later one."""
        ...


class _DynamoClient(Protocol):
    """The slice of a boto3 DynamoDB client this store uses."""

    def put_item(self, **kwargs: Any) -> Any: ...


class DynamoClaims(ClaimStore):
    """Claims as items in a DynamoDB table keyed by ``id``, with a ``expires_at`` TTL."""

    def __init__(self, table: str, client: _DynamoClient, *, ttl_seconds: int = 3600) -> None:
        self._table = table
        self._client = client
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_table_name(cls, table: str) -> DynamoClaims:
        """Build a store with a default ``boto3`` DynamoDB client (lazy import)."""
        import boto3

        return cls(table, boto3.client("dynamodb"))

    async def claim(self, request_id: str) -> bool:
        expires_at = int(time.time()) + self._ttl_seconds
        try:
            await asyncio.to_thread(
                self._client.put_item,
                TableName=self._table,
                Item={"id": {"S": request_id}, "expires_at": {"N": str(expires_at)}},
                ConditionExpression="attribute_not_exists(id)",
            )
        except Exception as exc:
            if aws_error_code(exc) == "ConditionalCheckFailedException":
                return False
            raise
        return True


class ClaimingProcess(Process):
    """Answers each request id once: a later delivery of a claimed id gets an empty result."""

    def __init__(self, inner: Process, claims: ClaimStore) -> None:
        self._inner = inner
        self._claims = claims

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        if ctx.request_id is not None:
            try:
                first = await self._claims.claim(ctx.request_id)
            except Exception:
                logger.warning("claim store failed; answering anyway", exc_info=True)
                first = True
            if not first:
                logger.info("duplicate delivery of a request; another frontend answers it")
                return SkillResult()
        return await self._inner.respond(inp, ctx)
