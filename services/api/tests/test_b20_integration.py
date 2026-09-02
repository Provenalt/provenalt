"""Integration test: exercise the B20 eligibility client against a REAL Base RPC.

Marked `integration`, excluded from default runs. Validates the researched ABI (selectors,
scope hashes, PolicyRegistry) against the live precompiles:

    pytest -m integration

Skips if the public endpoint is unreachable. Read-only.
"""

from __future__ import annotations

import httpx
import pytest
from provenalt_shared.chain import ChainClient, HttpxTransport

from provenalt_api.b20 import B20Client

pytestmark = pytest.mark.integration

BASE_RPC_URLS = ["https://mainnet.base.org", "https://base.publicnode.com"]
AAPLC = "0xb200000000000000000000C2e324d24d7eEcd1fb"  # live tokenized stock (proposal §3)
WALLET = "0x0000000000000000000000000000000000000001"


def test_b20_eligibility_live() -> None:
    client = ChainClient(
        rpc_urls=BASE_RPC_URLS,
        transport=HttpxTransport(timeout=20.0),
        initial_chunk=5_000,
        min_chunk=100,
        max_chunk=50_000,
    )
    try:
        result = B20Client(client).eligibility(AAPLC, WALLET)
    except httpx.HTTPError as exc:
        pytest.skip(f"Base RPC unreachable: {exc}")

    # The calls must decode cleanly (proves selectors/ABI are correct against the precompiles).
    assert isinstance(result.can_hold, bool)
    assert isinstance(result.can_send, bool)
    assert result.raw_balance >= 0
    assert result.adjusted_balance >= 0
    assert result.multiplier > 0  # WAD-scaled multiplier is always positive
