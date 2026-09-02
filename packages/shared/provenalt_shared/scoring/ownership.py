"""Pure ownership-history helpers.

Ownership transfer is a first-class scoring signal (proposal §5.2), and self-feedback must
be judged by who owned the agent *at the feedback's block height* — not the current owner —
so these functions operate over the full ``agent_owner_history``.
"""

from __future__ import annotations

from provenalt_shared.scoring.types import OwnerChange

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def owner_at_block(history: list[OwnerChange], block: int) -> str | None:
    """Return the owner (lowercased) as of ``block``, or ``None`` if before first ownership."""
    candidates = [h for h in history if h.block_number <= block]
    if not candidates:
        return None
    latest = max(candidates, key=lambda h: (h.block_number, h.log_index))
    return latest.to_address.lower()


def last_transfer_block(history: list[OwnerChange]) -> int | None:
    """Block of the most recent real ownership transfer (excluding the mint from 0x0)."""
    transfers = [h for h in history if h.from_address.lower() != ZERO_ADDRESS]
    if not transfers:
        return None
    return max(h.block_number for h in transfers)
