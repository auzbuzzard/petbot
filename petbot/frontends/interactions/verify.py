"""Verify Discord's Ed25519 request signatures.

Every interaction POST carries ``X-Signature-Ed25519`` and
``X-Signature-Timestamp`` headers; Discord signs ``timestamp + body`` with the
application's private key. We verify against the application *public* key
(``DISCORD_PUBLIC_KEY``). Discord rejects an endpoint at registration time
unless it both verifies signatures and answers the ``PING`` it sends.
"""

from __future__ import annotations

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


def verify_signature(public_key: str, timestamp: str, body: bytes, signature: str) -> bool:
    """Return whether ``signature`` is a valid Ed25519 signature for the request.

    ``public_key`` and ``signature`` are hex strings; ``timestamp`` is the raw
    header value; ``body`` is the raw request body. Returns ``False`` (never
    raises) on any malformed input or signature mismatch.
    """
    try:
        verify_key = VerifyKey(bytes.fromhex(public_key))
        verify_key.verify(timestamp.encode() + body, bytes.fromhex(signature))
    except (BadSignatureError, ValueError):
        return False
    return True
