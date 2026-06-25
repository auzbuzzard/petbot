"""petbot.observability: the privacy + lifecycle guarantees of the telemetry setup.

The enabled exporter path exports collector-less to AWS's live OTLP endpoints (verified
out-of-band); here we lock the offline guarantees: disabled is a true no-op, the user id is
opaquely hashed, and flushing is always safe.
"""

from __future__ import annotations

import pytest

from petbot.observability import (
    ObservabilitySettings,
    _otlp_aws_kwargs,
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


def test_otlp_kwargs_signs_only_aws_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    # An AWS OTLP endpoint ⇒ pinned endpoint + a SigV4-signing session (collector-less).
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "https://xray.us-east-1.amazonaws.com/v1/traces"
    )
    traces = _otlp_aws_kwargs("TRACES")
    assert traces["endpoint"] == "https://xray.us-east-1.amazonaws.com/v1/traces"
    assert traces["session"] is not None

    # A non-AWS endpoint (a plain dev collector) is left to the exporter's unsigned default.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://localhost:4318")
    assert _otlp_aws_kwargs("METRICS") == {}

    # Unset ⇒ no override either.
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)
    assert _otlp_aws_kwargs("LOGS") == {}
