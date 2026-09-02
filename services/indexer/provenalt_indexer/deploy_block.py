"""Discover a contract's deployment block via binary search on ``eth_getCode`` (proposal §2.2).

``eth_getCode`` returns empty (``0x``) for blocks before deployment and the runtime bytecode
at or after it. Binary-searching for the first block with code finds the deployment block in
O(log n) RPC calls — far cheaper than scanning, and it becomes the backfill anchor.
"""

from __future__ import annotations

from typing import Protocol

_EMPTY_CODE = {"0x", "0x0", ""}


class SupportsGetCode(Protocol):
    def get_block_number(self) -> int: ...
    def get_code(self, address: str, block: int | str = "latest") -> str: ...


def _has_code(chain: SupportsGetCode, address: str, block: int) -> bool:
    return chain.get_code(address, block) not in _EMPTY_CODE


def find_deployment_block(
    chain: SupportsGetCode,
    address: str,
    low: int = 0,
    high: int | None = None,
) -> int:
    """Return the first block at which ``address`` has code.

    Raises ``ValueError`` if the address has no code at ``high`` (not deployed in range).
    """
    if high is None:
        high = chain.get_block_number()

    if not _has_code(chain, address, high):
        raise ValueError(f"{address} has no code at block {high}; not deployed in [{low}, {high}]")

    # Invariant: no code at (low-1), code at high. Narrow to the first block with code.
    while low < high:
        mid = (low + high) // 2
        if _has_code(chain, address, mid):
            high = mid
        else:
            low = mid + 1
    return low
