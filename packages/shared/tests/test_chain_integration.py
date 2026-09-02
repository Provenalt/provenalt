"""Integration tests that hit a REAL Base RPC endpoint.

Marked `integration` and EXCLUDED from default runs (see pyproject `addopts`). Run with:

    pytest -m integration

These exercise the full HttpxTransport + ChainClient path against live infrastructure,
so they are inherently slower and network-dependent. They skip (rather than fail) if the
public endpoint is unreachable, so a flaky network never breaks a deliberate run.
"""

from __future__ import annotations

import httpx
import pytest

from provenalt_shared.chain import ChainClient, HttpxTransport

pytestmark = pytest.mark.integration

# Verified on-chain facts (proposal §3).
IDENTITY_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
REGISTERED_TOPIC0 = "0xca52e62c367d81bb2e328eb795f7c7ba24afb478408a26c0e201d155c449bc4a"
BASE_RPC_URLS = ["https://mainnet.base.org", "https://base.publicnode.com"]


def _block_number(transport: HttpxTransport, url: str) -> int:
    response = transport(
        url, {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}
    )
    return int(response["result"], 16)


def test_get_registered_logs_from_live_base_rpc() -> None:
    transport = HttpxTransport(timeout=20.0)
    try:
        head = _block_number(transport, BASE_RPC_URLS[0])
    except (httpx.HTTPError, KeyError) as exc:  # network down / unexpected shape
        pytest.skip(f"Base RPC unreachable: {exc}")

    client = ChainClient(
        rpc_urls=BASE_RPC_URLS,
        transport=transport,
        initial_chunk=5_000,
        min_chunk=100,
        max_chunk=50_000,
    )

    # Scan a modest recent window for Registered events; adaptive chunking handles caps.
    from_block = max(0, head - 20_000)
    logs = client.get_logs(
        address=IDENTITY_REGISTRY,
        topics=[REGISTERED_TOPIC0],
        from_block=from_block,
        to_block=head,
    )

    # We can't assert a specific count, but the call must succeed and return log dicts.
    assert isinstance(logs, list)
    for log in logs:
        assert log["topics"][0].lower() == REGISTERED_TOPIC0
