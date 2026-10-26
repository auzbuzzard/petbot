from __future__ import annotations

import json
import logging

import pytest

from petbot.frontends.discord.keyless import probe_container_identity, role_identity


def test_role_and_assumed_role_arns_name_the_same_role() -> None:
    role = "arn:aws:iam::111122223333:role/amazon/lightsail/us-east-1/containers/svc/abc"
    assumed = "arn:aws:sts::111122223333:assumed-role/abc/session-1"
    assert role_identity(role) == role_identity(assumed) == ("111122223333", "abc")
    assert role_identity("arn:aws:iam::111122223333:user/x") is None
    assert role_identity("not-an-arn") is None


def test_no_probe_without_its_setting(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("KEYLESS_PROBE", raising=False)
    with caplog.at_level(logging.INFO):
        probe_container_identity()
    assert "keyless-probe" not in caplog.text


def test_absent_container_credentials_are_reported(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("KEYLESS_PROBE", json.dumps({"service": "arn:aws:iam::1:role/r"}))
    monkeypatch.delenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", raising=False)
    monkeypatch.delenv("AWS_CONTAINER_CREDENTIALS_FULL_URI", raising=False)
    with caplog.at_level(logging.INFO):
        probe_container_identity()
    assert "keyless-probe: container credentials absent" in caplog.text
    assert "arn:aws" not in caplog.text
