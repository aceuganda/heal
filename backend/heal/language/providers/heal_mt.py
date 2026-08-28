"""Heal's private machine-translation services.

Two separate HTTP services, one per direction. Both stream Server-Sent Events;
the English service also answers as plain text, so responses are parsed
defensively rather than assuming a framing.

This replaces `danswer/utils/translation.py`, which called two hard-coded public
IPs over plain HTTP with no timeout, no auth and no retry.
"""
import asyncio
import time
from collections.abc import AsyncIterator
from collections.abc import Iterator

import aiohttp
import requests

from heal import config
from heal.language.errors import TranslationNotConfigured
from heal.language.errors import TranslationUnavailable
from heal.language.providers.base import TranslationProvider
from heal.logger import get_logger

logger = get_logger(__name__)

_SSE_PREFIX = "data: "


def _parse_sse_payload(body: str) -> str:
    """Pull the text out of an SSE body, or return it unchanged if it is plain.

    The English service is declared as `text/event-stream` but has historically
    answered with a bare string. Handling both means a change on the service
    side does not silently leak `data:` framing into a clinician's question.
    """
    if _SSE_PREFIX not in body:
        return body.strip()
    words = [
        line[len(_SSE_PREFIX) :].strip()
        for line in body.splitlines()
        if line.startswith(_SSE_PREFIX)
    ]
    return " ".join(w for w in words if w)


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
            return f"{self._en_url}/translate"
        if not self._lug_url:
            raise TranslationNotConfigured(
                "TRANSLATION_LUG_URL is not set; cannot translate to Luganda"
            )
        return f"{self._lug_url}/generate"

    @staticmethod
    def _headers() -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if config.TRANSLATION_API_KEY:
            headers["Authorization"] = f"Bearer {config.TRANSLATION_API_KEY}"
        return headers

    @staticmethod
    def _timeout() -> tuple[float, float]:
        return (config.TRANSLATION_CONNECT_TIMEOUT, config.TRANSLATION_READ_TIMEOUT)

    def _post(self, url: str, text: str, stream: bool) -> requests.Response:
        """POST with bounded retries on connection-level failures.

        Only failures that happen before any bytes arrive are retried. A stream
        that dies mid-flight is not replayed -- the user would see the first
        half of the translation twice.
        """
        payload = {"prompt": text, "stream": stream}
        last_error: Exception | None = None

        for attempt in range(config.TRANSLATION_MAX_RETRIES + 1):
            try:
                response = requests.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    stream=stream,
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

    def to_english(self, text: str) -> str:
        if not text.strip():
            return text
        response = self._post(self._endpoint("en"), text, stream=False)
        return _parse_sse_payload(response.text)

    def to_luganda(self, text: str) -> str:
        return "".join(self.stream_to_luganda(text))

    def stream_to_luganda(self, text: str) -> Iterator[str]:
        if not text.strip():
            return
        response = self._post(self._endpoint("lug"), text, stream=True)
        delay = config.TRANSLATION_STREAM_DELAY

        for chunk in response.iter_content(chunk_size=1024):
            for line in chunk.decode("utf-8", errors="replace").splitlines():
                if not line.startswith(_SSE_PREFIX):
                    continue
                word = line[len(_SSE_PREFIX) :].strip()
                if not word:
                    continue
                yield word + " "
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
                    json={"prompt": text, "stream": True},
                ) as response:
                    if response.status != 200:
                        raise TranslationUnavailable(
                            f"Translation service error (HTTP {response.status})"
                        )
                    async for chunk in response.content.iter_chunked(1024):
                        for line in chunk.decode(
                            "utf-8", errors="replace"
                        ).splitlines():
                            if not line.startswith(_SSE_PREFIX):
                                continue
                            word = line[len(_SSE_PREFIX) :].strip()
                            if not word:
                                continue
                            yield word + " "
                            if delay:
                                await asyncio.sleep(delay)
        except aiohttp.ClientError as e:
            logger.error(f"Async translation request to {url} failed: {e}")
            raise TranslationUnavailable("Translation service is unreachable") from e
