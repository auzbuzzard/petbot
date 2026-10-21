"""Reading a process's secrets from SSM at start (boto3 stubbed, no AWS)."""

from __future__ import annotations

import json
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

from petbot.platform.secrets import SSM_SECRETS, load_ssm_secrets


def _ssm() -> tuple[Any, Stubber]:
    client = boto3.client(
        "ssm", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x"
    )
    return client, Stubber(client)


def _found(*names: str) -> dict[str, Any]:
    # SSM leaves InvalidParameters out when every name is found.
    return {"Parameters": [{"Name": n, "Value": f"value of {n}"} for n in names]}


def test_nothing_to_load_reads_nothing() -> None:
    env: dict[str, str] = {}
    assert load_ssm_secrets(env, client=object()) == []
    assert env == {}


def test_each_named_variable_is_set_from_its_parameter() -> None:
    client, stub = _ssm()
    stub.add_response(
        "get_parameters",
        _found("/petbot/core/a", "/petbot/core/b"),
        {"Names": ["/petbot/core/a", "/petbot/core/b"], "WithDecryption": True},
    )
    env = {SSM_SECRETS: json.dumps({"API_KEY": "/petbot/core/a", "SALT": "/petbot/core/b"})}
    with stub:
        assert load_ssm_secrets(env, client=client) == ["API_KEY", "SALT"]
    assert env["API_KEY"] == "value of /petbot/core/a"
    assert env["SALT"] == "value of /petbot/core/b"


def test_a_variable_already_set_is_kept_and_not_read() -> None:
    client, stub = _ssm()
    stub.add_response(
        "get_parameters",
        _found("/petbot/core/b"),
        {"Names": ["/petbot/core/b"], "WithDecryption": True},
    )
    env = {
        SSM_SECRETS: json.dumps({"API_KEY": "/petbot/core/a", "SALT": "/petbot/core/b"}),
        "API_KEY": "from the environment",
    }
    with stub:
        assert load_ssm_secrets(env, client=client) == ["SALT"]
    assert env["API_KEY"] == "from the environment"


def test_more_than_ten_names_are_read_in_batches() -> None:
    client, stub = _ssm()
    names = [f"/petbot/core/p{i:02d}" for i in range(12)]
    stub.add_response(
        "get_parameters", _found(*names[:10]), {"Names": names[:10], "WithDecryption": True}
    )
    stub.add_response(
        "get_parameters", _found(*names[10:]), {"Names": names[10:], "WithDecryption": True}
    )
    env = {SSM_SECRETS: json.dumps({f"V{i:02d}": n for i, n in enumerate(names)})}
    with stub:
        assert len(load_ssm_secrets(env, client=client)) == 12
    stub.assert_no_pending_responses()


def test_an_unknown_parameter_fails_start_up() -> None:
    client, stub = _ssm()
    stub.add_response(
        "get_parameters",
        {"Parameters": [], "InvalidParameters": ["/petbot/core/missing"]},
        {"Names": ["/petbot/core/missing"], "WithDecryption": True},
    )
    env = {SSM_SECRETS: json.dumps({"API_KEY": "/petbot/core/missing"})}
    with stub, pytest.raises(RuntimeError, match="/petbot/core/missing"):
        load_ssm_secrets(env, client=client)
    assert "API_KEY" not in env


@pytest.mark.parametrize("raw", ['["/petbot/core/a"]', '{"API_KEY": ""}', '{"API_KEY": 1}'])
def test_a_malformed_name_map_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match=SSM_SECRETS):
        load_ssm_secrets({SSM_SECRETS: raw}, client=object())
