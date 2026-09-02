"""In-memory fake chain client for indexer worker tests (not a test module)."""

from __future__ import annotations

from typing import Any


class FakeChain:
    """Serves canned logs by block range and canned block hashes for reorg tests."""

    def __init__(
        self,
        logs: list[dict[str, Any]],
        head: int,
        block_hashes: dict[int, str] | None = None,
        deployed_at: int | None = None,
    ) -> None:
        self.logs = logs
        self.head = head
        self.block_hashes = block_hashes or {}
        self.deployed_at = deployed_at
        self.get_logs_calls = 0

    def get_code(self, address: str, block: int | str = "latest") -> str:
        blk = self.head if block == "latest" else int(block)
        if self.deployed_at is not None and blk >= self.deployed_at:
            return "0x6080"
        return "0x"

    def get_logs(
        self, address: str, topics: list[Any], from_block: int, to_block: int
    ) -> list[dict[str, Any]]:
        self.get_logs_calls += 1
        return [
            log
            for log in self.logs
            if from_block <= int(log["blockNumber"], 16) <= to_block
            and log["address"].lower() == address.lower()
        ]

    def get_block_number(self) -> int:
        return self.head

    def get_block_by_number(
        self, block: int, include_transactions: bool = False
    ) -> dict[str, Any] | None:
        if block > self.head:
            return None
        return {"number": hex(block), "hash": self.block_hashes.get(block, f"0x{block:064x}")}
