"""Transport: the only layer that knows about HTTP, signing, and `requests`.

It does exactly three jobs and nothing else:
  1. Sign every request with your RSA-PSS key (Kalshi's auth scheme).
  2. Speak HTTP (GET/POST/DELETE) and raise/parse cleanly.
  3. Be a good API citizen: retry transient failures with backoff, and
     self-throttle to stay under the rate limit.

Nothing above this layer should ever see a `requests` exception, a status code,
or an `Authorization` header. If it does, the abstraction has leaked.
"""

from __future__ import annotations

import base64
import threading
import time
from collections import deque
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"

# Retried on these transient conditions; everything else fails fast.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class TransportError(RuntimeError):
    """A request that failed after exhausting retries. Carries status + body so
    callers can decide, but they never have to touch `requests` directly."""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def load_private_key(path: str):
    """Load an unencrypted PEM RSA private key from disk."""
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


class _RateLimiter:
    """A tiny thread-safe sliding-window limiter. Blocks just long enough to
    keep us under `max_calls` per `period_s`. Cheap insurance against the 429s
    that would otherwise trigger retries (or a temp ban)."""

    def __init__(self, max_calls: int, period_s: float):
        self.max_calls = max_calls
        self.period_s = period_s
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] > self.period_s:
                self._calls.popleft()
            if len(self._calls) >= self.max_calls:
                sleep_for = self.period_s - (now - self._calls[0])
                if sleep_for > 0:
                    time.sleep(sleep_for)
            self._calls.append(time.monotonic())


class Transport:
    """Signed HTTP to one Kalshi base URL.

    Read-only endpoints don't strictly need signing, but signing them is
    harmless and keeps one code path. Write endpoints (orders) require it.
    """

    def __init__(
        self,
        key_id: str,
        private_key_path: str,
        base_url: str = PROD_BASE,
        *,
        max_retries: int = 3,
        rate_limit_per_s: int = 8,
        timeout_s: float = 15.0,
    ):
        self.key_id = key_id
        self.private_key = load_private_key(private_key_path)
        self.base_url = base_url.rstrip("/")
        # The path prefix Kalshi expects inside the signed string, e.g. "/trade-api/v2".
        self.path_prefix = urlparse(self.base_url).path
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self._session = requests.Session()
        self._limiter = _RateLimiter(rate_limit_per_s, 1.0)

    # --- signing -------------------------------------------------------------

    def _sign(self, timestamp_ms: str, method: str, signed_path: str) -> str:
        message = f"{timestamp_ms}{method}{signed_path}".encode("utf-8")
        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _headers(self, method: str, endpoint: str) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        signed_path = self.path_prefix + endpoint  # query string excluded by design
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": self._sign(timestamp_ms, method, signed_path),
            "accept": "application/json",
            "content-type": "application/json",
        }

    # --- requests ------------------------------------------------------------

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        """Signed request with rate-limiting + retry/backoff. Returns parsed JSON.

        `endpoint` is relative to the base, e.g. "/portfolio/balance". Retries
        are restricted to idempotent-ish transient failures; a 4xx like 400/401
        fails immediately because retrying a malformed/forbidden request is
        pointless and burns rate limit.
        """
        url = self.base_url + endpoint
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            self._limiter.acquire()
            try:
                resp = self._session.request(
                    method,
                    url,
                    headers=self._headers(method, endpoint),
                    params=params,
                    json=json,
                    timeout=self.timeout_s,
                )
            except requests.RequestException as exc:
                last_exc = exc  # network-level failure: retry
            else:
                if resp.status_code < 400:
                    return resp.json() if resp.content else {}
                if resp.status_code not in _RETRY_STATUS:
                    raise TransportError(
                        f"{method} {endpoint} -> {resp.status_code}",
                        status=resp.status_code,
                        body=resp.text[:500],
                    )
                last_exc = TransportError(
                    f"{method} {endpoint} -> {resp.status_code}",
                    status=resp.status_code,
                    body=resp.text[:500],
                )

            if attempt < self.max_retries:
                # Exponential backoff: 0.25, 0.5, 1.0, ... seconds.
                time.sleep(0.25 * (2**attempt))

        raise TransportError(f"{method} {endpoint} failed after retries: {last_exc}")

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        return self.request("GET", endpoint, params=params)

    def post(self, endpoint: str, json: dict) -> dict:
        return self.request("POST", endpoint, json=json)

    def delete(self, endpoint: str) -> dict:
        return self.request("DELETE", endpoint)

    # --- websocket handshake -------------------------------------------------
    # The WS feed lives at the same host under "/ws/v2" instead of "/v2", and is
    # authenticated by signing the handshake exactly like a REST GET of that path.

    def _ws_signed_path(self) -> str:
        head, _, tail = self.path_prefix.rpartition("/")  # "/trade-api", "/", "v2"
        return f"{head}/ws/{tail}"

    def ws_url(self) -> str:
        netloc = urlparse(self.base_url).netloc
        return f"wss://{netloc}{self._ws_signed_path()}"

    def ws_auth_headers(self) -> dict:
        """Headers that authenticate the WS handshake (signs GET of the ws path)."""
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": self._sign(timestamp_ms, "GET", self._ws_signed_path()),
        }
