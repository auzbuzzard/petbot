"""A minimal dev HTTP server for the core worker: ``python -m petbot.workers.core``.

Serves the same ``SkillCall`` -> ``SkillResult`` contract as the Lambda handler at
``POST /dispatch``, so the edge (``transport=http``) can talk to a local worker.
A single persistent event loop runs in a background thread, so skills' async
clients (the booru ``httpx.AsyncClient``) stay bound to one loop across requests.
A dev convenience; production uses the Lambda handler.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from petbot.logging import configure_logging
from petbot.workers.core.worker import build_worker

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    worker = build_worker()

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length)
            future = asyncio.run_coroutine_threadsafe(worker.serve(body), loop)
            out = future.result().encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args: object) -> None:
            logger.debug("core-worker: %s", args)

    host = os.environ.get("WORKER_HOST", "127.0.0.1")
    port = int(os.environ.get("WORKER_PORT", "8000"))
    logger.info("core worker listening on http://%s:%d/dispatch", host, port)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
