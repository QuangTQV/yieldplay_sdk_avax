"""
yieldplay/api/routes/users.py – User-facing endpoints.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from yieldplay.api.deps import SDKDep, UserServiceDep, handle_sdk_error
from yieldplay.types import (
    ApproveTokenRequest, ClaimEligibility, ClaimRequest,
    DepositEligibility, DepositRequest, TokenBalanceResponse,
    TransactionResult, UserDepositInfo, UserPortfolio, UserRoundSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["User Actions"])


# ── Writes (always direct contract) ───────────────────────────────────────

@router.post("/deposit", response_model=TransactionResult)
async def deposit(body: DepositRequest, sdk: SDKDep) -> TransactionResult:
    try:
        return sdk.deposit(body.game_id, body.round_id, int(body.amount_wei))
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post("/claim", response_model=TransactionResult)
async def claim(body: ClaimRequest, sdk: SDKDep) -> TransactionResult:
    try:
        return sdk.claim(body.game_id, body.round_id)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post("/approve", response_model=TransactionResult)
async def approve_token(body: ApproveTokenRequest, sdk: SDKDep) -> TransactionResult:
    try:
        return sdk.approve_token(body.token_address,
                                 int(body.amount_wei) if body.amount_wei else None)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


# ── Simple reads (direct contract) ────────────────────────────────────────

@router.get("/{user_address}/deposits/{game_id}/{round_id}",
            response_model=UserDepositInfo, summary="Raw user deposit from contract")
async def get_user_deposit(user_address: str, game_id: str,
                           round_id: int, sdk: SDKDep) -> UserDepositInfo:
    try:
        return sdk.get_user_deposit(game_id, round_id, user_address)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{user_address}/balance/{token_address}", response_model=TokenBalanceResponse)
async def get_token_balance(user_address: str, token_address: str,
                            sdk: SDKDep) -> TokenBalanceResponse:
    try:
        balance_wei = sdk.get_token_balance(token_address, user_address)
        decimals = sdk.get_token_decimals(token_address)
        return TokenBalanceResponse(
            address=user_address, token=token_address,
            balance_wei=str(balance_wei),
            balance_formatted=str(balance_wei / (10 ** decimals)),
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{user_address}/allowance/{token_address}",
            response_model=dict[str, str])
async def get_token_allowance(user_address: str, token_address: str,
                              sdk: SDKDep) -> dict[str, str]:
    try:
        return {"allowance_wei": str(sdk.get_token_allowance(token_address, user_address))}
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


# ── Composite: DB-powered queries ──────────────────────────────────────────

@router.get("/{user_address}/rounds/{game_id}/{round_id}/summary",
            response_model=UserRoundSummary,
            summary="Full user round summary",
            description=(
                "Aggregates: round metadata (DB) + status (contract) + "
                "user deposit (contract) + token balance/allowance (contract) + "
                "participant count (DB). Returns actionability flags: "
                "can_deposit, can_claim, needs_approval, share %."
            ))
async def get_user_round_summary(
    user_address: str, game_id: str, round_id: int,
    svc: UserServiceDep,
) -> UserRoundSummary:
    try:
        return await svc.get_user_round_summary(user_address, game_id, round_id)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{user_address}/eligibility/deposit/{game_id}/{round_id}",
            response_model=DepositEligibility,
            summary="Pre-flight deposit eligibility check",
            description=(
                "Returns eligible=true/false with per-check breakdown. "
                "Use this to power deposit buttons in game UIs."
            ))
async def check_deposit_eligibility(
    user_address: str, game_id: str, round_id: int,
    amount_wei: int,
    svc: UserServiceDep,
) -> DepositEligibility:
    try:
        return await svc.check_deposit_eligibility(user_address, game_id, round_id, amount_wei)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{user_address}/eligibility/claim/{game_id}/{round_id}",
            response_model=ClaimEligibility,
            summary="Pre-flight claim eligibility check")
async def check_claim_eligibility(
    user_address: str, game_id: str, round_id: int,
    svc: UserServiceDep,
) -> ClaimEligibility:
    try:
        return await svc.check_claim_eligibility(user_address, game_id, round_id)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{user_address}/portfolio",
            response_model=UserPortfolio,
            summary="User portfolio (DB-powered reverse index)",
            description=(
                "Returns ALL rounds a user has ever participated in across all games, "
                "with claim status, prize amounts and round status. "
                "Powered by the event index — O(1) DB query, no O(N) RPC calls."
            ))
async def get_user_portfolio(
    user_address: str,
    game_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
    svc: UserServiceDep = ...,  # type: ignore[assignment]
) -> UserPortfolio:
    try:
        return await svc.get_user_portfolio(user_address, game_id=game_id,
                                            offset=offset, limit=limit)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc
