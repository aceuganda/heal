"""Heal's private machine-translation services.

Two separate BentoML services, one per direction, with the same contract:

    POST {base}/translate/stream   {"text": "..."}

answering Server-Sent Events, one JSON object per `data:` line:

    {"event": "token", "token": "Nyirira "}
    ...
    {"event": "done", "full_text": "Nyirira amazzi amangi."}

Both directions use the streaming route. The services also offer a
non-streaming `/translate`, but the English one has answered it with a 500
while the stream worked, and one code path for both is less to go wrong.

This replaces `danswer/utils/translation.py`, which called two hard-coded public
IPs over plain HTTP with no timeout, no auth and no retry.
"""
import asyncio
import codecs
import json
import time
from collections.abc import AsyncIterator
from collections.abc import Iterable
from collections.abc import Iterator
from typing import Any

import aiohttp
import requests

from heal import config
from heal.language.errors import TranslationNotConfigured
from heal.language.errors import TranslationUnavailable
from heal.language.providers.base import TranslationProvider
from heal.logger import get_logger

logger = get_logger(__name__)

_SSE_PREFIX = "data:"
_ROUTE = "/translate/stream"


class _SseLines:
    """Turns arbitrary byte chunks into complete lines.

    A network chunk can end mid-line, or mid-character; both are carried over
    to the next chunk rather than parsed half-way.
    """

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buffer = ""

    def feed(self, chunk: bytes) -> list[str]:
        self._buffer += self._decoder.decode(chunk)
        *lines, self._buffer = self._buffer.split("\n")
        return [line.rstrip("\r") for line in lines]

    def close(self) -> list[str]:
        rest = self._buffer + self._decoder.decode(b"", final=True)
        self._buffer = ""
        return [rest] if rest.strip() else []


def _event(line: str) -> dict[str, Any] | None:
    """One SSE line as an event, or None for framing and blank lines.

    A `data:` line that is not JSON is treated as a bare token, so a service
    still on the old word-per-line framing does not lose its text.
    """
    if not line.startswith(_SSE_PREFIX):
        return None
    data = line[len(_SSE_PREFIX) :].strip()
    if not data:
        return None
    try:
        parsed = json.loads(data)
    except ValueError:
        return {"event": "token", "token": data + " "}
    return parsed if isinstance(parsed, dict) else None


class _Tokens:
    """Applies events: yields tokens, stops at done, raises on error."""

    def __init__(self) -> None:
        self.done = False
        self.full_text: str | None = None
        self.emitted = False

    def apply(self, event: dict[str, Any] | None) -> str | None:
        if event is None or self.done:
            return None
        kind = event.get("event")
        if kind == "token":
            token = str(event.get("token") or "")
            if token:
                self.emitted = True
                return token
            return None
        if kind == "done":
            self.done = True
            self.full_text = event.get("full_text")
            # A service that only sends the final text still gets read.
            if not self.emitted and self.full_text:
                self.emitted = True
                return str(self.full_text)
            return None
        if kind == "error":
            # The service's own message may echo the input; never surface it.
            raise TranslationUnavailable("Translation service reported an error")
        return None


def _tokens(chunks: Iterable[bytes]) -> Iterator[str]:
    lines = _SseLines()
    state = _Tokens()
    for chunk in chunks:
        for line in lines.feed(chunk):
            token = state.apply(_event(line))
            if token:
                yield token
        if state.done:
            return
    for line in lines.close():
        token = state.apply(_event(line))
        if token:
            yield token


class HealMtProvider(TranslationProvider):
    name = "heal_mt"

    def __init__(self) -> None:
        self._en_url = config.TRANSLATION_EN_URL
        self._lug_url = config.TRANSLATION_LUG_URL

    #####
    # Plumbing
    #####

    def _endpoint(self, direction: str) -> str:
        """Resolve a direction to a full URL, failing with the var to set."""
        if direction == "en":
            if not self._en_url:
                raise TranslationNotConfigured(
                    "TRANSLATION_EN_URL is not set; cannot translate to English"
                )
            return f"{self._en_url}{_ROUTE}"
        if not self._lug_url:
            raise TranslationNotConfigured(
                "TRANSLATION_LUG_URL is not set; cannot translate to Luganda"
            )
        return f"{self._lug_url}{_ROUTE}"

    @staticmethod
    def _headers() -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if config.TRANSLATION_API_KEY:
            headers["Authorization"] = f"Bearer {config.TRANSLATION_API_KEY}"
        return headers

    @staticmethod
    def _timeout() -> tuple[float, float]:
        return (config.TRANSLATION_CONNECT_TIMEOUT, config.TRANSLATION_READ_TIMEOUT)

    def _post(self, url: str, text: str) -> requests.Response:
        """POST with bounded retries on connection-level failures.

        Only failures that happen before any bytes arrive are retried. A stream
        that dies mid-flight is not replayed -- the user would see the first
        half of the translation twice.
        """
        payload = {"text": text}
        last_error: Exception | None = None

        for attempt in range(config.TRANSLATION_MAX_RETRIES + 1):
            try:
                response = requests.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    stream=True,
                    timeout=self._timeout(),
                )
            except requests.RequestException as e:
                last_error = e
            else:
                if response.status_code == 200:
                    return response
                # 4xx is our bug or a bad key; retrying will not help.
                if response.status_code < 500:
                    raise TranslationUnavailable(
                        f"Translation service rejected the request "
                        f"(HTTP {response.status_code})"
                    )
                last_error = TranslationUnavailable(
                    f"Translation service error (HTTP {response.status_code})"
                )

            if attempt < config.TRANSLATION_MAX_RETRIES:
                time.sleep(config.TRANSLATION_RETRY_BACKOFF * (2**attempt))

        # Log the failure, never the text being translated.
        logger.error(f"Translation request to {url} failed: {last_error}")
        raise TranslationUnavailable(
            "Translation service is unreachable"
        ) from last_error

    #####
    # Provider interface
    #####

    def _stream(self, direction: str, text: str) -> Iterator[str]:
        response = self._post(self._endpoint(direction), text)
        try:
            yield from _tokens(response.iter_content(chunk_size=1024))
        except requests.RequestException as e:
            # The stream died after it started; not retried (see _post).
            raise TranslationUnavailable("Translation stream was interrupted") from e

    def to_english(self, text: str) -> str:
        if not text.strip():
            return text
        return "".join(self._stream("en", text)).strip()

    def to_luganda(self, text: str) -> str:
        return "".join(self.stream_to_luganda(text)).strip()

    def stream_to_luganda(self, text: str) -> Iterator[str]:
        if not text.strip():
            return
        delay = config.TRANSLATION_STREAM_DELAY
        for token in self._stream("lug", text):
            yield token
            if delay:
                time.sleep(delay)

    async def astream_to_luganda(self, text: str) -> AsyncIterator[str]:
        if not text.strip():
            return
        url = self._endpoint("lug")
        timeout = aiohttp.ClientTimeout(
            connect=config.TRANSLATION_CONNECT_TIMEOUT,
            total=config.TRANSLATION_READ_TIMEOUT,
        )
        delay = config.TRANSLATION_STREAM_DELAY

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    headers=self._headers(),
                    json={"text": text},
                ) as response:
                    if response.status != 200:
                        raise TranslationUnavailable(
                            f"Translation service error (HTTP {response.status})"
                        )
                    lines = _SseLines()
                    state = _Tokens()
                    async for chunk in response.content.iter_chunked(1024):
                        for line in lines.feed(chunk):
                            token = state.apply(_event(line))
                            if token:
                                yield token
                                if delay:
                                    await asyncio.sleep(delay)
                        if state.done:
                            return
                    for line in lines.close():
                        token = state.apply(_event(line))
                        if token:
                            yield token
        except aiohttp.ClientError as e:
            logger.error(f"Async translation request to {url} failed: {e}")
            raise TranslationUnavailable("Translation service is unreachable") from e
