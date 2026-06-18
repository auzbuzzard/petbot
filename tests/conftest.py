"""Shared test setup.

Provide a minimal chat LLM config so ``ChatSettings`` (which requires one) is
constructible offline — the agent is exercised with ``TestModel``, so the id is
never dialed. ``setdefault`` leaves a real environment untouched.
"""

from __future__ import annotations

import os

os.environ.setdefault("CHAT_LLM__KIND", "bedrock")
os.environ.setdefault("CHAT_LLM__MODEL", "test/model")
