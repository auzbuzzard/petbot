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
    assert ObservabilitySettings(_env_file=None).enabled is False


def test_hash_user_id_is_stable_salted_and_opaque() -> None:
    h = hash_user_id("123456789", "salt")
    assert h == hash_user_id("123456789", "salt")
    assert h != hash_user_id("123456789", "other-salt")
    assert h != hash_user_id("987654321", "salt")
    assert h != "123456789" and len(h) == 16


def test_flush_is_safe_without_a_provider() -> None:
    flush_observability()


def test_otlp_kwargs_signs_only_aws_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "https://xray.us-east-1.amazonaws.com/v1/traces"
    )
    traces = _otlp_aws_kwargs("TRACES")
    assert traces["endpoint"] == "https://xray.us-east-1.amazonaws.com/v1/traces"
    assert traces["session"] is not None

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://localhost:4318")
    assert _otlp_aws_kwargs("METRICS") == {}

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)
    assert _otlp_aws_kwargs("LOGS") == {}
