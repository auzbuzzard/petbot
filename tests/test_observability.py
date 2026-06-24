"""petbot.observability: the privacy + lifecycle guarantees of the telemetry setup.

The enabled exporter path needs a live OTLP collector and is exercised by the manual
trace check in the plan's verification; here we lock the offline guarantees: disabled is a
true no-op, the user id is opaquely hashed, and flushing is always safe.
"""

from __future__ import annotations

from petbot.observability import (
    ObservabilitySettings,
    configure_observability,
    flush_observability,
    hash_user_id,
)


def test_disabled_is_a_noop() -> None:
    assert configure_observability(ObservabilitySettings(enabled=False)) is False


def test_default_is_disabled() -> None:
    # Off by default ⇒ a process emits nothing until an operator opts in.
    assert ObservabilitySettings(_env_file=None).enabled is False


def test_hash_user_id_is_stable_salted_and_opaque() -> None:
    h = hash_user_id("123456789", "salt")
    assert h == hash_user_id("123456789", "salt")  # stable
    assert h != hash_user_id("123456789", "other-salt")  # salt matters
    assert h != hash_user_id("987654321", "salt")  # id matters
    assert h != "123456789" and len(h) == 16  # opaque, short


def test_flush_is_safe_without_a_provider() -> None:
    flush_observability()  # no SDK provider installed → must not raise
