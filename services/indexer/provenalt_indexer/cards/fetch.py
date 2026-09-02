"""Fetch agent-card content from an ``agentURI`` (proposal §4.1).

Supported URI schemes (per ERC8004SPEC.md):

* ``ipfs://<cid>[/path]`` — tried across ≥2 public gateways with fallback.
* ``https://`` / ``http://`` — fetched directly.
* ``data:[<mediatype>][;base64],<data>`` — decoded inline, no network.

Returns a :class:`FetchResult` with the content, its sha256 hash, the HTTP status, and the
source that produced it. The httpx client is injectable so this is unit-testable offline.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import urllib.parse
from dataclasses import dataclass

import httpx

# Public IPFS gateways (≥2 for fallback). Overridable via settings/constructor.
DEFAULT_IPFS_GATEWAYS = [
    "https://ipfs.io/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
    "https://dweb.link/ipfs/",
]

# Fetch status values.
OK = "ok"
FETCH_ERROR = "fetch_error"
UNSUPPORTED_SCHEME = "unsupported_scheme"
EMPTY = "empty"


@dataclass(frozen=True)
class FetchResult:
    status: str
    content: str | None = None
    content_hash: str | None = None
    http_status: int | None = None
    source: str | None = None


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class CardFetcher:
    def __init__(
        self,
        client: httpx.Client | None = None,
        ipfs_gateways: list[str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = client if client is not None else httpx.Client(timeout=timeout)
        self._gateways = ipfs_gateways if ipfs_gateways is not None else DEFAULT_IPFS_GATEWAYS

    def fetch(self, token_uri: str) -> FetchResult:
        uri = token_uri.strip()
        if uri.startswith("data:"):
            return self._fetch_data_uri(uri)
        if uri.startswith("ipfs://"):
            return self._fetch_ipfs(uri)
        if uri.startswith("https://") or uri.startswith("http://"):
            return self._fetch_http(uri)
        return FetchResult(status=UNSUPPORTED_SCHEME, source=uri)

    # ── scheme handlers ──────────────────────────────────────────────────────

    def _fetch_data_uri(self, uri: str) -> FetchResult:
        header, _, payload = uri[len("data:") :].partition(",")
        try:
            if header.endswith(";base64") or ";base64" in header:
                raw = base64.b64decode(payload)
            else:
                raw = urllib.parse.unquote_to_bytes(payload)
        except (ValueError, binascii.Error):
            return FetchResult(status=FETCH_ERROR, source="data:")
        return self._result_from_bytes(raw, http_status=None, source="data:")

    def _fetch_ipfs(self, uri: str) -> FetchResult:
        cid_path = uri[len("ipfs://") :]
        last_status: int | None = None
        for gateway in self._gateways:
            url = gateway + cid_path
            outcome = self._get(url)
            if isinstance(outcome, FetchResult):  # transport error → try next gateway
                continue
            status_code, raw = outcome
            last_status = status_code
            if status_code == 200:
                return self._result_from_bytes(raw, http_status=200, source=url)
        return FetchResult(status=FETCH_ERROR, http_status=last_status)

    def _fetch_http(self, uri: str) -> FetchResult:
        outcome = self._get(uri)
        if isinstance(outcome, FetchResult):
            return outcome
        status_code, raw = outcome
        if status_code == 200:
            return self._result_from_bytes(raw, http_status=200, source=uri)
        return FetchResult(status=FETCH_ERROR, http_status=status_code, source=uri)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get(self, url: str) -> tuple[int, bytes] | FetchResult:
        """GET a URL. Returns (status_code, body) or a FETCH_ERROR result on transport failure."""
        try:
            response = self._client.get(url, follow_redirects=True)
        except httpx.HTTPError:
            return FetchResult(status=FETCH_ERROR, source=url)
        return response.status_code, response.content

    def _result_from_bytes(self, raw: bytes, http_status: int | None, source: str) -> FetchResult:
        if not raw:
            return FetchResult(status=EMPTY, http_status=http_status, source=source)
        return FetchResult(
            status=OK,
            content=raw.decode("utf-8", errors="replace"),
            content_hash=_hash(raw),
            http_status=http_status,
            source=source,
        )
