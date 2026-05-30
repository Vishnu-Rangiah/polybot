"""Minimal read client for the Kalshi trade API (v2).

Auth model: every request is signed with your RSA private key. The matching
public key was uploaded to Kalshi, which returns a Key ID. Each request sends
three headers and Kalshi verifies the signature against your stored public key:

  KALSHI-ACCESS-KEY        your Key ID (the UUID Kalshi showed you)
  KALSHI-ACCESS-TIMESTAMP  current Unix time in milliseconds
  KALSHI-ACCESS-SIGNATURE  base64(RSA-PSS-SHA256( timestamp + METHOD + path ))

The signed `path` includes the "/trade-api/v2" prefix but NOT the query string.
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
        # The path prefix Kalshi expects in the signed string, e.g. "/trade-api/v2"
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
        signed_path = self.path_prefix + endpoint  # query string excluded by design
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": self._sign(timestamp_ms, method, signed_path),
            "accept": "application/json",
        }

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        """GET an endpoint like '/portfolio/balance' (relative to base_url)."""
        headers = self._auth_headers("GET", endpoint)
        resp = self.session.get(self.base_url + endpoint, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    # --- convenience read calls ---

    def balance(self) -> dict:
        """Authenticated read — proves the key + signing work end to end."""
        return self.get("/portfolio/balance")

    def markets(self, limit: int = 5, status: str = "open") -> dict:
        """Market data (public, but signing it does no harm)."""
        return self.get("/markets", params={"limit": limit, "status": status})

    def exchange_status(self) -> dict:
        return self.get("/exchange/status")
