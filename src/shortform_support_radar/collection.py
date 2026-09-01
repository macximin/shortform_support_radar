"""Collection service: fetch a source's public pages and assemble one receipt."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .boards import read_candidates
from .notice import KEYWORDS, Candidate
from .policy import (
    HOST_PENALTY_SECONDS,
    MAX_HOST_INTERVAL_SECONDS,
    MAX_RESPONSE_BYTES,
    REQUEST_ATTEMPTS,
    REQUEST_INTERVAL_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_SECONDS,
    USER_AGENT,
    PolicyViolation,
    PublicUrl,
    enforce_response_cap,
)
from .receipts import Fetch, Receipt
from .registry import Source

KST = dt.timezone(dt.timedelta(hours=9))


class HostRateLimiter:
    """Space out requests per host.

    Two sources can point at the same board, so pacing inside one source is not
    enough: without this, back-to-back sources hit the same host with no gap.
    """

    def __init__(self, interval: float = REQUEST_INTERVAL_SECONDS, sleep=time.sleep, clock=time.monotonic) -> None:
        self._interval = interval
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self._penalty: dict[str, float] = {}

    def interval_for(self, url: PublicUrl) -> float:
        return min(self._interval + self._penalty.get(self._host(url), 0.0), MAX_HOST_INTERVAL_SECONDS)

    def penalise(self, url: PublicUrl) -> None:
        """Widen this host's pacing after it failed to answer."""
        host = self._host(url)
        self._penalty[host] = self._penalty.get(host, 0.0) + HOST_PENALTY_SECONDS

    def wait_for(self, url: PublicUrl) -> None:
        host = self._host(url)
        previous = self._last.get(host)
        now = self._clock()
        if previous is not None:
            remaining = self.interval_for(url) - (now - previous)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last[host] = now

    @staticmethod
    def _host(url: PublicUrl) -> str:
        return urlparse(str(url)).netloc


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def today_kst() -> dt.date:
    return dt.datetime.now(KST).date()


def decode_body(body: bytes, content_type: str | None) -> str:
    """Decode using the charset the board declares, not an assumed one."""
    charset = "utf-8"
    if content_type:
        match = re.search(r"charset=([\w\-]+)", content_type, re.IGNORECASE)
        if match:
            charset = match.group(1)
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _read_once(url: PublicUrl, timeout: float) -> tuple[int, PublicUrl, bytes, str]:
    request = Request(
        str(url),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    with urlopen(request, timeout=timeout) as response:
        body = enforce_response_cap(response.read(MAX_RESPONSE_BYTES + 1))
        final_url = PublicUrl.parse(response.geturl()) or url
        return response.status, final_url, body, decode_body(body, response.headers.get("Content-Type"))


def fetch_public_page(
    url: PublicUrl,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
    attempts: int = REQUEST_ATTEMPTS,
    sleep=time.sleep,
) -> tuple[int, PublicUrl, bytes, str]:
    """Read one public page anonymously. No cookies, no credentials, no session.

    A timeout or connection reset is retried: these are public boards reached over
    a long link, and one slow response should not drop a whole source. A policy
    violation is not retried - it will not become allowed on a second try.
    """
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _read_once(url, timeout)
        except PolicyViolation:
            raise
        except (OSError, TimeoutError) as error:
            last = error
            if attempt < attempts:
                sleep(RETRY_BACKOFF_SECONDS * attempt)
    assert last is not None
    raise last


def collect(source: Source, observed_on: dt.date | None = None, limiter: HostRateLimiter | None = None) -> Receipt:
    observed_at = utc_now()
    observed_on = observed_on or today_kst()
    limiter = limiter or HostRateLimiter()
    fetches: list[Fetch] = []
    candidates: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    for query, url in source.requests():
        limiter.wait_for(url)
        try:
            status, final_url, body, page = fetch_public_page(url)
        except (OSError, TimeoutError):
            limiter.penalise(url)
            raise
        fetches.append(
            Fetch(
                query=query,
                requested_url=str(url),
                final_url=str(final_url),
                http_status=status,
                page_sha256=hashlib.sha256(body).hexdigest(),
                page_bytes=len(body),
            )
        )
        for candidate in read_candidates(
            page,
            final_url,
            matched_query=query,
            all_rows_in_scope=source.all_rows_in_scope,
            search_param_names=source.search_param_names,
        ):
            if candidate.key() in seen:
                continue
            seen.add(candidate.key())
            candidates.append(candidate)

    candidates.sort(key=Candidate.sort_key)
    return Receipt(
        source=source,
        observed_at=observed_at,
        observed_on=observed_on,
        fetches=tuple(fetches),
        candidates=tuple(candidates),
        keyword_set=KEYWORDS,
    )
