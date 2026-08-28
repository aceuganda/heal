"""Tests for the private MT provider.

The behaviour that matters here is what the old `utils/translation.py` did not
have: bounded timeouts, bounded retries, typed failures, and configuration that
comes from the environment rather than the source.
"""
import pytest
import requests

from heal import config
from heal.language.errors import TranslationNotConfigured
from heal.language.errors import TranslationUnavailable
from heal.language.providers.heal_mt import _parse_sse_payload
from heal.language.providers.heal_mt import HealMtProvider


#####
# Response parsing
#####


class TestParseSsePayload:
    def test_plain_text_passes_through(self) -> None:
        assert _parse_sse_payload("  how much paracetamol  ") == "how much paracetamol"

    def test_sse_frames_are_unwrapped(self) -> None:
        body = "data: how\ndata: much\ndata: paracetamol\n"
        assert _parse_sse_payload(body) == "how much paracetamol"

    def test_blank_frames_are_dropped(self) -> None:
        assert _parse_sse_payload("data: how\ndata: \ndata: much\n") == "how much"

    def test_non_data_lines_are_ignored(self) -> None:
        body = "event: start\ndata: how\n\ndata: much\n"
        assert _parse_sse_payload(body) == "how much"


#####
# Configuration
#####


class TestEndpointResolution:
    def test_missing_english_url_names_the_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "TRANSLATION_EN_URL", "")
        with pytest.raises(TranslationNotConfigured, match="TRANSLATION_EN_URL"):
            HealMtProvider().to_english("ki kigambo")

    def test_missing_luganda_url_names_the_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "TRANSLATION_LUG_URL", "")
        with pytest.raises(TranslationNotConfigured, match="TRANSLATION_LUG_URL"):
            list(HealMtProvider().stream_to_luganda("take one tablet"))

    def test_no_network_address_is_hard_coded(self) -> None:
        provider = HealMtProvider()
        assert provider._endpoint("en").startswith("http://mt-en.test")
        assert provider._endpoint("lug").startswith("http://mt-lug.test")

    def test_api_key_becomes_a_bearer_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "TRANSLATION_API_KEY", "s3cret")
        assert HealMtProvider()._headers()["Authorization"] == "Bearer s3cret"

    def test_no_auth_header_when_unset(self) -> None:
        assert "Authorization" not in HealMtProvider()._headers()


#####
# Request behaviour
#####


class TestPostBehaviour:
    def test_timeout_is_always_supplied(
        self, monkeypatch: pytest.MonkeyPatch, fake_response
    ) -> None:
        """A missing timeout is what let a hung MT service hang the chat."""
        seen: dict = {}

        def capture(url, **kwargs):
            seen.update(kwargs)
            return fake_response(200, "hello")

        monkeypatch.setattr(requests, "post", capture)
        HealMtProvider().to_english("ki kigambo")

        assert seen["timeout"] == (
            config.TRANSLATION_CONNECT_TIMEOUT,
            config.TRANSLATION_READ_TIMEOUT,
        )

    def test_server_error_is_retried_then_reported(
        self, monkeypatch: pytest.MonkeyPatch, fake_response
    ) -> None:
        calls = []

        def always_502(url, **kwargs):
            calls.append(url)
            return fake_response(502)

        monkeypatch.setattr(requests, "post", always_502)
        with pytest.raises(TranslationUnavailable):
            HealMtProvider().to_english("ki kigambo")

        assert len(calls) == config.TRANSLATION_MAX_RETRIES + 1

    def test_client_error_is_not_retried(
        self, monkeypatch: pytest.MonkeyPatch, fake_response
    ) -> None:
        """A 401 or 400 is our bug or a bad key -- retrying only adds latency."""
        calls = []

        def always_401(url, **kwargs):
            calls.append(url)
            return fake_response(401)

        monkeypatch.setattr(requests, "post", always_401)
        with pytest.raises(TranslationUnavailable, match="401"):
            HealMtProvider().to_english("ki kigambo")

        assert len(calls) == 1

    def test_recovers_on_a_later_attempt(
        self, monkeypatch: pytest.MonkeyPatch, fake_response
    ) -> None:
        attempts = {"n": 0}

        def flaky(url, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise requests.ConnectionError("connection refused")
            return fake_response(200, "one tablet twice daily")

        monkeypatch.setattr(requests, "post", flaky)
        assert HealMtProvider().to_english("x") == "one tablet twice daily"
        assert attempts["n"] == 2

    def test_connection_failure_raises_a_typed_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(url, **kwargs):
            raise requests.ConnectionError("connection refused")

        monkeypatch.setattr(requests, "post", refuse)
        with pytest.raises(TranslationUnavailable):
            HealMtProvider().to_english("ki kigambo")

    def test_message_text_is_never_logged(
        self, monkeypatch: pytest.MonkeyPatch, caplog
    ) -> None:
        """Clinical questions are patient-adjacent; failures log the URL only."""

        def refuse(url, **kwargs):
            raise requests.ConnectionError("connection refused")

        monkeypatch.setattr(requests, "post", refuse)
        with caplog.at_level("ERROR"):
            with pytest.raises(TranslationUnavailable):
                HealMtProvider().to_english("omulwadde alina omusujja")

        assert "omulwadde" not in caplog.text


#####
# Streaming
#####


class TestStreaming:
    def test_tokens_are_yielded_in_order(
        self, monkeypatch: pytest.MonkeyPatch, fake_response
    ) -> None:
        chunks = [b"data: mira\ndata: eddagala\n", b"data: buli\ndata: lunaku\n"]
        monkeypatch.setattr(
            requests, "post", lambda url, **kw: fake_response(200, chunks=chunks)
        )
        assert list(HealMtProvider().stream_to_luganda("take the medicine daily")) == [
            "mira ",
            "eddagala ",
            "buli ",
            "lunaku ",
        ]

    def test_to_luganda_joins_the_stream(
        self, monkeypatch: pytest.MonkeyPatch, fake_response
    ) -> None:
        monkeypatch.setattr(
            requests,
            "post",
            lambda url, **kw: fake_response(
                200, chunks=[b"data: mira\ndata: eddagala\n"]
            ),
        )
        assert HealMtProvider().to_luganda("take the medicine") == "mira eddagala "

    def test_undecodable_bytes_do_not_kill_the_stream(
        self, monkeypatch: pytest.MonkeyPatch, fake_response
    ) -> None:
        monkeypatch.setattr(
            requests,
            "post",
            lambda url, **kw: fake_response(
                200, chunks=[b"data: mira\xff\ndata: ok\n"]
            ),
        )
        assert len(list(HealMtProvider().stream_to_luganda("x"))) == 2


#####
# Cheap paths
#####


class TestEmptyInput:
    def test_blank_text_makes_no_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def explode(url, **kwargs):
            raise AssertionError("should not call the MT service for blank text")

        monkeypatch.setattr(requests, "post", explode)
        provider = HealMtProvider()
        assert provider.to_english("   ") == "   "
        assert list(provider.stream_to_luganda("")) == []
