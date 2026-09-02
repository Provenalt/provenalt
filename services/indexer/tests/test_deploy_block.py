"""Unit tests for deployment-block discovery (binary search on eth_getCode)."""

from __future__ import annotations

import pytest

from provenalt_indexer.deploy_block import find_deployment_block


class FakeChain:
    """A chain where `address` has code from `deployed_at` onward. Counts get_code calls."""

    def __init__(self, deployed_at: int | None, head: int) -> None:
        self._deployed_at = deployed_at
        self._head = head
        self.get_code_calls = 0

    def get_block_number(self) -> int:
        return self._head

    def get_code(self, address: str, block: int | str = "latest") -> str:
        self.get_code_calls += 1
        blk = self._head if block == "latest" else int(block)
        if self._deployed_at is not None and blk >= self._deployed_at:
            return "0x6080604052"  # some bytecode
        return "0x"


def test_finds_exact_deployment_block() -> None:
    chain = FakeChain(deployed_at=5_000_000, head=12_000_000)
    assert find_deployment_block(chain, "0xabc") == 5_000_000


def test_deployment_at_genesis() -> None:
    chain = FakeChain(deployed_at=0, head=1000)
    assert find_deployment_block(chain, "0xabc") == 0


def test_deployment_at_head() -> None:
    chain = FakeChain(deployed_at=1000, head=1000)
    assert find_deployment_block(chain, "0xabc") == 1000


def test_raises_when_not_deployed_at_head() -> None:
    chain = FakeChain(deployed_at=None, head=1000)
    with pytest.raises(ValueError):
        find_deployment_block(chain, "0xabc")


def test_binary_search_is_logarithmic() -> None:
    chain = FakeChain(deployed_at=7_777_777, head=20_000_000)
    assert find_deployment_block(chain, "0xabc") == 7_777_777
    # ~log2(20M) ≈ 25; allow generous headroom but assert it is not linear.
    assert chain.get_code_calls < 60
