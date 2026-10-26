"""At-most-once handling of a platform event, however many frontend copies receive it.

A claim is a conditional create in DynamoDB (:class:`DynamoClaims`): atomic, so exactly one
of two concurrent copies wins, and expired by the table's TTL. The winner records which copy
it is; a loser adds itself to the item and bumps a counter, so the table shows whether a
second copy is still connected and where it runs.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from typing import Any, Protocol

from petbot.platform._aws import aws_error_code

logger = logging.getLogger(__name__)


class ClaimStore(Protocol):
    async def claim(self, event_id: str) -> bool: ...


class _DynamoClient(Protocol):
    def put_item(self, **kwargs: Any) -> Any: ...

    def update_item(self, **kwargs: Any) -> Any: ...


class DynamoClaims(ClaimStore):
    """Claims as items in a DynamoDB table keyed by ``id``, expiring via ``expires_at``.

    ``holder`` names this copy of the frontend (its hostname by default); it is written as
    ``claimed_by`` by a winner and added to ``also_delivered_to`` by a loser."""

    def __init__(
        self,
        table: str,
        client: _DynamoClient,
        *,
        holder: str | None = None,
        ttl_seconds: int = 3600,
    ) -> None:
        self._table = table
        self._client = client
        self._holder = holder or socket.gethostname()
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_table_name(cls, table: str) -> DynamoClaims:
        import boto3

        return cls(table, boto3.client("dynamodb"))

    async def claim(self, event_id: str) -> bool:
        expires_at = int(time.time()) + self._ttl_seconds
        try:
            await asyncio.to_thread(
                self._client.put_item,
                TableName=self._table,
                Item={
                    "id": {"S": event_id},
                    "claimed_by": {"S": self._holder},
                    "expires_at": {"N": str(expires_at)},
                },
                ConditionExpression="attribute_not_exists(id)",
            )
        except Exception as exc:
            if aws_error_code(exc) != "ConditionalCheckFailedException":
                raise
            await self._record_duplicate(event_id)
            return False
        return True

    async def _record_duplicate(self, event_id: str) -> None:
        logger.warning("%s was already claimed; %s stays silent", event_id, self._holder)
        try:
            await asyncio.to_thread(
                self._client.update_item,
                TableName=self._table,
                Key={"id": {"S": event_id}},
                UpdateExpression="ADD duplicate_deliveries :one, also_delivered_to :me",
                ExpressionAttributeValues={":one": {"N": "1"}, ":me": {"SS": [self._holder]}},
            )
        except Exception:
            logger.warning("couldn't record the duplicate delivery", exc_info=True)
