"""Minimal signed read client for the Kalshi trade API (v2).

Use this for quick auth smoke tests (`polybot read`). For the full trading stack
(retry, rate limits, normalized MarketState), use `kalshi_agent.transport` and
`kalshi_agent.datasource` instead.
"""

from __future__ import annotations

import base64
import time
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"


def load_private_key(path: str):
    """Load an unencrypted PEM RSA private key from disk."""
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


class KalshiClient:
    def __init__(self, key_id: str, private_key_path: str, base_url: str = PROD_BASE):
        self.key_id = key_id
        self.private_key = load_private_key(private_key_path)
        self.base_url = base_url.rstrip("/")
        self.path_prefix = urlparse(self.base_url).path
        self.session = requests.Session()

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

    def _auth_headers(self, method: str, endpoint: str) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        signed_path = self.path_prefix + endpoint
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": self._sign(timestamp_ms, method, signed_path),
            "accept": "application/json",
        }

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        headers = self._auth_headers("GET", endpoint)
        resp = self.session.get(self.base_url + endpoint, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def balance(self) -> dict:
        return self.get("/portfolio/balance")

    def markets(self, limit: int = 5, status: str = "open") -> dict:
        return self.get("/markets", params={"limit": limit, "status": status})

    def exchange_status(self) -> dict:
        return self.get("/exchange/status")
