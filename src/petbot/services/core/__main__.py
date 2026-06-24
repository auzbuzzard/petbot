"""A minimal dev HTTP server for the core service: ``python -m petbot.services.core``.

Serves the same dispatch -> ``SkillResult`` contract as the Lambda handler at
``POST /dispatch``, so the frontend (``transport=http``) can talk to a local service.
A single persistent event loop runs in a background thread, so skills' async clients
(the booru ``httpx.AsyncClient``) stay bound to one loop across requests. A dev
convenience; production uses the Lambda handler.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from petbot.logging_setup import configure_logging
from petbot.observability import ObservabilitySettings, configure_observability
from petbot.platform import serve
from petbot.services.core import build_process

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    configure_observability(ObservabilitySettings())
    process = build_process()

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length)
            future = asyncio.run_coroutine_threadsafe(serve(process, body), loop)
            out = future.result().encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args: object) -> None:
            logger.debug("core-service: %s", args)

    host = os.environ.get("SERVICE_HOST", "127.0.0.1")
    port = int(os.environ.get("SERVICE_PORT", "8000"))
    logger.info("core service listening on http://%s:%d/dispatch", host, port)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
