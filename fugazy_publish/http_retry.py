"""Shared HTTP retry and pacing helpers for platform API calls."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import Any

import requests

from fugazy_publish.config import RetryConfig

ErrorCodeFn = Callable[[requests.Response], str]

TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
_last_request_at: dict[str, float] = {}


def throttle_requests(scope: str, min_interval_seconds: float) -> None:
    if min_interval_seconds <= 0:
        return
    last = _last_request_at.get(scope, 0.0)
    elapsed = time.time() - last
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)
    _last_request_at[scope] = time.time()


def retry_wait_seconds(
    resp: requests.Response | None,
    delay: float,
    *,
    max_seconds: float,
    min_wait_seconds: float = 0.0,
) -> float:
    if resp is not None:
        for header in ("Retry-After", "X-RateLimit-Reset", "x-ratelimit-reset"):
            raw = resp.headers.get(header)
            if not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if header.lower() == "retry-after":
                return min(max(value, delay, min_wait_seconds), max_seconds)
            return min(max(value - time.time(), delay, min_wait_seconds) + 1.0, max_seconds)
    return min(max(delay, min_wait_seconds), max_seconds)


def request_with_retry(
    method: str,
    url: str,
    *,
    retry: RetryConfig,
    operation: str,
    platform: str,
    scope: str,
    throttle: bool = False,
    error_code_fn: ErrorCodeFn | None = None,
    retryable_error_codes: set[str] | frozenset[str] | None = None,
    min_wait_by_code: dict[str, float] | None = None,
    timeout: float = 60.0,
    **kwargs: Any,
) -> requests.Response:
    delay = retry.initial_seconds
    retryable_error_codes = retryable_error_codes or set()
    min_wait_by_code = min_wait_by_code or {}
    last_error = f"{platform} {operation} failed before first attempt"

    for attempt in range(1, retry.max_attempts + 1):
        if throttle:
            throttle_requests(scope, retry.min_api_interval_seconds)
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt >= retry.max_attempts:
                raise RuntimeError(f"{platform} {operation} failed: {exc}") from exc
            wait = retry_wait_seconds(None, delay, max_seconds=retry.max_seconds)
            print(
                f"{platform} {operation}: request error — retry {attempt}/{retry.max_attempts} in {wait:.0f}s",
                file=sys.stderr,
            )
            time.sleep(wait)
            delay = min(delay * 2, retry.max_seconds)
            continue

        code = error_code_fn(resp) if error_code_fn else ""
        retryable = resp.status_code in TRANSIENT_STATUSES or code in retryable_error_codes
        if retryable and attempt < retry.max_attempts:
            wait = retry_wait_seconds(
                resp,
                delay,
                max_seconds=retry.max_seconds,
                min_wait_seconds=min_wait_by_code.get(code, 0.0),
            )
            print(
                f"{platform} {operation}: {code or resp.status_code} — "
                f"retry {attempt}/{retry.max_attempts} in {wait:.0f}s",
                file=sys.stderr,
            )
            time.sleep(wait)
            delay = min(delay * 2, retry.max_seconds)
            continue
        return resp

    raise RuntimeError(last_error)
