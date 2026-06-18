"""Shared test setup.

Provide a dummy ``CHAT_MODEL`` so ``ChatSettings`` (now a required field) is
constructible offline — the worker/agent are tested with ``TestModel``, so the id
itself is never dialed. ``setdefault`` leaves a real environment untouched.
"""

from __future__ import annotations

import os

os.environ.setdefault("CHAT_MODEL", "test/model")
