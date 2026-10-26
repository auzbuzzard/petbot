"""SigV4 signing for Bedrock's ``bedrock-mantle`` endpoint, checked offline.

The signature is recomputed here from the request as it left the client, by the published
SigV4 algorithm rather than by botocore, so a header or body that changes after signing, or
a wrong service or Region, fails the check.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest
import respx
from botocore.credentials import Credentials

from petbot.domain import Platform, SkillContext, TextInput, User
from petbot.platform import ToolRegistry
from petbot.process import ChatProcess
from petbot.process.model import build_model_from_config
from petbot.process.settings import BedrockMantleModel, ChatSettings
from petbot.process.sigv4 import MANTLE_SERVICE, SigV4Auth, mantle_region

_MANTLE = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
_CREDENTIALS = Credentials("AKIDEXAMPLE", "secret-access-key", "session-token")


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _expected_signature(request: httpx.Request, secret: str, region: str, service: str) -> str:
    auth = request.headers["Authorization"]
    signed_headers = auth.split("SignedHeaders=")[1].split(",")[0]
    amz_date = request.headers["X-Amz-Date"]
    date = amz_date[:8]
    canonical_headers = "".join(
        f"{name}:{request.headers[name].strip()}\n" for name in signed_headers.split(";")
    )
    canonical_request = "\n".join(
        [
            request.method,
            request.url.raw_path.decode().split("?")[0],
            request.url.query.decode(),
            canonical_headers,
            signed_headers,
            hashlib.sha256(request.content).hexdigest(),
        ]
    )
    scope = f"{date}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    key = _hmac(f"AWS4{secret}".encode(), date)
    for part in (region, service, "aws4_request"):
        key = _hmac(key, part)
    return hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()


def _assert_signed(request: httpx.Request, *, region: str = "us-east-1") -> None:
    auth = request.headers["Authorization"]
    assert auth.startswith(
        f"AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/{request.headers['X-Amz-Date'][:8]}"
        f"/{region}/{MANTLE_SERVICE}/aws4_request, "
    )
    assert request.headers["X-Amz-Security-Token"] == "session-token"
    signature = auth.split("Signature=")[1]
    assert signature == _expected_signature(
        request, _CREDENTIALS.secret_key, region, MANTLE_SERVICE
    )


def _completion(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "google.gemma-4-31b",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="Ann"),
        conversation_id="c",
    )


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambient credentials for botocore's default chain, as a Lambda role provides them."""
    for name in ("AWS_PROFILE", "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", _CREDENTIALS.access_key)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", _CREDENTIALS.secret_key)
    monkeypatch.setenv("AWS_SESSION_TOKEN", _CREDENTIALS.token)


def test_the_region_comes_from_the_mantle_host() -> None:
    assert mantle_region(_MANTLE) == "us-east-1"
    assert mantle_region("https://bedrock-mantle.eu-west-2.api.aws/v1") == "eu-west-2"
    for url in (
        "https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1",
        "https://bedrock-mantle.api.aws/v1",
        "https://bedrock-mantle.us-east-1.example.com/v1",
    ):
        with pytest.raises(ValueError, match="not a bedrock-mantle endpoint"):
            mantle_region(url)


@respx.mock
async def test_a_request_is_signed_in_place_of_the_bearer_key() -> None:
    route = respx.post(f"{_MANTLE}/chat/completions").mock(return_value=_completion("hi"))
    body = json.dumps({"model": "m", "messages": []}).encode()
    async with httpx.AsyncClient(auth=SigV4Auth(MANTLE_SERVICE, "us-east-1", _CREDENTIALS)) as c:
        await c.post(
            f"{_MANTLE}/chat/completions",
            content=body,
            headers={"Authorization": "Bearer sigv4", "Content-Type": "application/json"},
        )
    sent = route.calls.last.request
    assert "Bearer" not in sent.headers["Authorization"]
    assert sent.content == body
    _assert_signed(sent)


def test_the_sync_flow_signs_too() -> None:
    with respx.mock:
        route = respx.get(f"{_MANTLE}/models?x=1").mock(return_value=httpx.Response(200))
        with httpx.Client(auth=SigV4Auth(MANTLE_SERVICE, "us-east-1", _CREDENTIALS)) as client:
            client.get(f"{_MANTLE}/models", params={"x": "1"})
    _assert_signed(route.calls.last.request)


def test_headers_added_after_signing_are_not_signed() -> None:
    request = httpx.Request(
        "POST", f"{_MANTLE}/chat/completions", content=b"{}", headers={"User-Agent": "a"}
    )
    SigV4Auth(MANTLE_SERVICE, "us-east-1", _CREDENTIALS)._sign(request)
    signed = request.headers["Authorization"].split("SignedHeaders=")[1].split(",")[0]
    assert signed == "host;x-amz-date;x-amz-security-token"


def test_no_credentials_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NoCredentials:
        def get_credentials(self) -> Any:
            return None

    monkeypatch.setattr("botocore.session.Session", _NoCredentials)
    with pytest.raises(ValueError, match="no AWS credentials"):
        SigV4Auth(MANTLE_SERVICE, "us-east-1")


def test_the_variant_needs_only_a_model_and_an_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_LLM__KIND", "bedrock_mantle")
    monkeypatch.setenv("CHAT_LLM__MODEL", "google.gemma-4-31b")
    monkeypatch.setenv("CHAT_LLM__BASE_URL", _MANTLE)
    monkeypatch.delenv("CHAT_LLM__API_KEY", raising=False)
    llm = ChatSettings(_env_file=None).llm
    assert llm == BedrockMantleModel(model="google.gemma-4-31b", base_url=_MANTLE)


@respx.mock
@pytest.mark.usefixtures("aws_credentials")
async def test_the_chat_agent_calls_mantle_signed_with_the_runtimes_credentials() -> None:
    route = respx.post(f"{_MANTLE}/chat/completions").mock(return_value=_completion("hi there"))
    llm = BedrockMantleModel(model="google.gemma-4-31b", base_url=_MANTLE)
    chat = ChatProcess(
        ToolRegistry([]),
        model=build_model_from_config(llm),
        settings=ChatSettings(llm=llm, _env_file=None),
    )
    result = await chat.respond(TextInput(text="hi"), _ctx())
    assert result.text == "hi there"
    sent = route.calls.last.request
    assert json.loads(sent.content)["model"] == "google.gemma-4-31b"
    _assert_signed(sent)


@pytest.mark.usefixtures("aws_credentials")
def test_gemma_on_mantle_keeps_its_profile_with_sigv4() -> None:
    from petbot.process.model import _GeminiToolSchema

    model = build_model_from_config(
        BedrockMantleModel(model="google.gemma-4-31b", base_url=_MANTLE)
    )
    assert model.profile.json_schema_transformer is _GeminiToolSchema
