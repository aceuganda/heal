"""Tests for the self-hosted endpoint: catalogue entry, failover, probe."""
import pytest

from heal import config
from heal.llm import service
from heal.llm.models import ModelSpec
from heal.llm.registry import all_models
from heal.llm.registry import available_models
from heal.llm.registry import get_model
from heal.llm.registry import SELF_HOSTED_ID


@pytest.fixture
def self_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured internal endpoint. No network is ever touched."""
    monkeypatch.setattr(config, "SELF_HOSTED_URL", "http://internal.test:8000/v1")
    monkeypatch.setattr(config, "SELF_HOSTED_MODEL", "meta/Llama-3.3-70B")
    monkeypatch.setattr(config, "SELF_HOSTED_CONTEXT_TOKENS", 131_072)
    monkeypatch.setattr(config, "SELF_HOSTED_API_KEY", "not-needed")
    monkeypatch.setattr(config, "ENABLED_CHAT_MODELS", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


@pytest.fixture
def not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SELF_HOSTED_URL", "")
    monkeypatch.setattr(config, "SELF_HOSTED_MODEL", "")


class TestCatalogue:
    def test_absent_until_a_url_is_set(self, not_configured: None) -> None:
        assert SELF_HOSTED_ID not in {m.id for m in all_models()}

    def test_appears_once_configured(self, self_hosted: None) -> None:
        spec = get_model(SELF_HOSTED_ID)
        assert spec.base_url == "http://internal.test:8000/v1"
        assert spec.model_name == "meta/Llama-3.3-70B"
        assert spec.context_tokens == 131_072
        assert spec.self_hosted

    def test_offered_without_any_provider_key(
        self, self_hosted: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # We host it, so there is no third-party key to check. Reachability is
        # a runtime question, not a catalogue one.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEN_AI_API_KEY", raising=False)
        assert SELF_HOSTED_ID in {m.id for m in available_models()}


class FakeLLM:
    """Streams tokens, or raises before yielding any."""

    def __init__(self, tokens: list[str], error: Exception | None = None) -> None:
        self._tokens = tokens
        self._error = error
        self.calls = 0

    def stream(self, _messages: object) -> object:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return iter(self._tokens)


class TestFailover:
    def _patch_builds(
        self, monkeypatch: pytest.MonkeyPatch, by_id: dict[str, FakeLLM]
    ) -> None:
        def build(spec: ModelSpec, timeout: int | None = None) -> FakeLLM:
            return by_id[spec.id]

        monkeypatch.setattr(service, "build_llm", build)

    def test_uses_the_internal_model_when_it_answers(
        self, self_hosted: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        internal = FakeLLM(["all", " good"])
        self._patch_builds(monkeypatch, {SELF_HOSTED_ID: internal})

        tokens, generation = service.stream_with_failover(SELF_HOSTED_ID, [])

        assert "".join(tokens) == "all good"
        assert generation.model_id == SELF_HOSTED_ID
        assert generation.failed_over is False
        assert internal.calls == 1

    def test_retries_twice_before_giving_up(
        self, self_hosted: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        internal = FakeLLM([], error=ConnectionError("refused"))
        cloud = FakeLLM(["from", " the cloud"])
        self._patch_builds(
            monkeypatch, {SELF_HOSTED_ID: internal, config.CHAT_MODEL: cloud}
        )

        tokens, generation = service.stream_with_failover(SELF_HOSTED_ID, [])
        text = "".join(tokens)

        assert text == "from the cloud"
        assert internal.calls == service.SELF_HOSTED_ATTEMPTS == 2
        assert generation.failed_over is True
        # The model that answered, not the one that was asked for -- an audit
        # recording the request could not explain who wrote the answer.
        assert generation.model_id == config.CHAT_MODEL

    def test_a_cloud_model_never_falls_back(
        self, self_hosted: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cloud = FakeLLM([], error=ConnectionError("refused"))
        self._patch_builds(monkeypatch, {"gpt-4o": cloud})

        tokens, generation = service.stream_with_failover("gpt-4o", [])

        with pytest.raises(ConnectionError):
            list(tokens)
        assert cloud.calls == 1
        assert generation.failed_over is False


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class TestProbe:
    def test_reports_not_configured_without_a_url(self, not_configured: None) -> None:
        assert service.probe_self_hosted() == {
            "configured": False,
            "reachable": False,
            "models": [],
        }

    def test_reads_the_served_model(
        self, self_hosted: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import requests

        payload = {
            "object": "list",
            "data": [
                {
                    "id": "meta/Llama-3.3-70B",
                    "max_model_len": 131072,
                    "owned_by": "vllm",
                }
            ],
        }
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload))

        result = service.probe_self_hosted()

        assert result["reachable"] is True
        assert result["serves_configured_model"] is True
        assert result["models"][0]["context_tokens"] == 131072

    def test_a_mismatched_model_id_is_reported(
        self, self_hosted: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import requests

        payload = {"data": [{"id": "something/else", "max_model_len": 8192}]}
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload))

        # Reachable but serving something other than what is configured, which
        # is why every call would 404.
        result = service.probe_self_hosted()
        assert result["reachable"] is True
        assert result["serves_configured_model"] is False

    def test_unreachable_is_an_answer_not_an_error(
        self, self_hosted: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import requests

        def boom(*_a: object, **_k: object) -> None:
            raise ConnectionError("no route to host")

        monkeypatch.setattr(requests, "get", boom)

        result = service.probe_self_hosted()

        assert result == {
            "configured": True,
            "reachable": False,
            "error": "ConnectionError",
            "models": [],
        }
