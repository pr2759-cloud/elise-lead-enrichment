"""HTTP client with exponential backoff. Used by every enrichment module.

Centralizes retry logic so each API module doesn't reinvent it. Also gives us
a single place to add metrics, circuit breakers, etc. later.
"""
from __future__ import annotations
import logging
import random
import time
from typing import Optional

import requests

from .config import HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT

log = logging.getLogger(__name__)

# Default retry policy: 3 attempts, exponential backoff starting at 1s with jitter.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 8.0

# Status codes worth retrying — transient server or rate-limit errors.
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class HTTPError(Exception):
    """Wraps any HTTP failure that survived retries."""


def _sleep_with_jitter(base: float, attempt: int, maximum: float) -> None:
    delay = min(base * (2 ** attempt), maximum)
    # Full jitter: random between 0 and the capped exponential
    actual = random.uniform(0, delay)
    log.debug("HTTP retry backoff: attempt=%d delay=%.2fs", attempt, actual)
    time.sleep(actual)


def get_json(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = HTTP_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    accept_404: bool = False,
):
    """GET a URL and parse the JSON body. Retries transient failures.

    - Non-retryable 4xx responses raise immediately (no point in retrying a 401/403).
    - Retryable status codes (408, 429, 5xx) are retried with exponential backoff.
    - Network errors (timeout, connection reset) are retried.
    - If accept_404 is True and the server returns 404, returns None instead
      of raising (used by Wikipedia summary endpoint which legitimately 404s).
    """
    combined_headers = {"User-Agent": HTTP_USER_AGENT}
    if headers:
        combined_headers.update(headers)

    last_error: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            response = requests.get(
                url, params=params, headers=combined_headers, timeout=timeout,
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
            log.debug("HTTP network error on attempt %d for %s: %s", attempt + 1, url, e)
            if attempt + 1 < max_attempts:
                _sleep_with_jitter(base_delay, attempt, max_delay)
                continue
            raise HTTPError(f"network error after {max_attempts} attempts: {e}") from e

        # 404 with accept_404 → explicit None, no retry
        if accept_404 and response.status_code == 404:
            return None

        if response.status_code in RETRYABLE_STATUS_CODES:
            last_error = HTTPError(f"HTTP {response.status_code} on {url}")
            log.debug("HTTP retryable status %d on attempt %d for %s",
                      response.status_code, attempt + 1, url)
            if attempt + 1 < max_attempts:
                # Honor Retry-After on 429 if provided
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        time.sleep(min(float(retry_after), max_delay))
                        continue
                    except ValueError:
                        pass
                _sleep_with_jitter(base_delay, attempt, max_delay)
                continue
            raise HTTPError(
                f"HTTP {response.status_code} after {max_attempts} attempts on {url}"
            )

        # Non-retryable error — fail fast
        if not response.ok:
            raise HTTPError(f"HTTP {response.status_code} on {url}: {response.text[:200]}")

        # Success
        try:
            return response.json()
        except ValueError as e:
            raise HTTPError(f"invalid JSON from {url}: {e}") from e

    # Shouldn't reach here, but just in case
    raise HTTPError(f"exhausted attempts; last error: {last_error}")
