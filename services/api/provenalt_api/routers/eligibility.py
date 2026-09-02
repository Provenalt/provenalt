"""B20 eligibility endpoint (proposal §7.2).

``GET /v1/eligibility?wallet=&token=`` — for a known B20 tokenized stock, reports whether a
wallet may hold/transfer it (native PolicyRegistry ``isAuthorized``) plus multiplier-aware
raw + adjusted balances. Per §7 this is an x402-gated tier; x402 gating arrives in Group 9,
so for now it is per-IP rate limited like the free tier.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from provenalt_shared.db import repository as repo

from provenalt_api.b20 import B20Client
from provenalt_api.deps import ChainDep, SessionDep
from provenalt_api.schemas import EligibilityResponse

router = APIRouter(prefix="/v1", tags=["eligibility"])

_ADDRESS = r"^0x[0-9a-fA-F]{40}$"


@router.get(
    "/eligibility",
    response_model=EligibilityResponse,
    summary="B20 stock eligibility + multiplier-aware balances for a wallet",
)
def get_eligibility(
    session: SessionDep,
    chain: ChainDep,
    wallet: Annotated[str, Query(pattern=_ADDRESS, description="Wallet address (0x…40 hex)")],
    token: Annotated[str, Query(description="B20 token contract address or symbol")],
) -> EligibilityResponse:
    known = repo.get_b20_token(session, token)
    if known is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="unknown B20 token (not in the registry)",
        )

    result = B20Client(chain).eligibility(known.address, wallet.lower())
    return EligibilityResponse(
        token_address=known.address,
        symbol=known.symbol,
        decimals=known.decimals,
        wallet=wallet.lower(),
        can_hold=result.can_hold,
        can_send=result.can_send,
        eligible=result.eligible,
        receiver_policy_id=str(result.receiver_policy_id),
        sender_policy_id=str(result.sender_policy_id),
        raw_balance=str(result.raw_balance),
        adjusted_balance=str(result.adjusted_balance),
        multiplier=str(result.multiplier),
    )
