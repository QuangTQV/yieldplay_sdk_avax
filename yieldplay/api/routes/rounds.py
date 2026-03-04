"""
yieldplay/api/routes/rounds.py
────────────────────────────────
Layer 2 – Round lifecycle management (game-owner actions).

All write endpoints require the SDK to be configured with a signer.
Composite write sequences (settle, distribute) are handled by RoundService.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from yieldplay.api.deps import RoundServiceDep, SDKDep, handle_sdk_error
from yieldplay.types import (
    ChooseWinnerRequest,
    FeeBreakdown,
    TransactionResult,
    VaultActionRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rounds", tags=["Round Lifecycle"])


def _log(action: str, game_id: str, round_id: int, tx: TransactionResult) -> None:
    logger.info("%s game=%s round=%s hash=%s", action, game_id, round_id, tx.tx_hash)


# ── Individual vault steps ─────────────────────────────────────────────────


@router.post(
    "/vault/deposit",
    response_model=TransactionResult,
    summary="Deploy round deposits to vault",
)
async def deposit_to_vault(body: VaultActionRequest, sdk: SDKDep) -> TransactionResult:
    try:
        tx = sdk.deposit_to_vault(body.game_id, body.round_id)
        _log("depositToVault", body.game_id, body.round_id, tx)
        return tx
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/vault/withdraw",
    response_model=TransactionResult,
    summary="Withdraw principal + yield from vault",
)
async def withdraw_from_vault(
    body: VaultActionRequest, sdk: SDKDep
) -> TransactionResult:
    try:
        tx = sdk.withdraw_from_vault(body.game_id, body.round_id)
        _log("withdrawFromVault", body.game_id, body.round_id, tx)
        return tx
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/settlement", response_model=TransactionResult, summary="Run fee settlement"
)
async def settlement(body: VaultActionRequest, sdk: SDKDep) -> TransactionResult:
    try:
        tx = sdk.settlement(body.game_id, body.round_id)
        _log("settlement", body.game_id, body.round_id, tx)
        return tx
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/winner", response_model=TransactionResult, summary="Assign prize to a winner"
)
async def choose_winner(body: ChooseWinnerRequest, sdk: SDKDep) -> TransactionResult:
    try:
        tx = sdk.choose_winner(
            body.game_id, body.round_id, body.winner, int(body.amount_wei)
        )
        _log("chooseWinner", body.game_id, body.round_id, tx)
        return tx
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/finalize",
    response_model=TransactionResult,
    summary="Finalize round and open claim window",
)
async def finalize_round(body: VaultActionRequest, sdk: SDKDep) -> TransactionResult:
    try:
        tx = sdk.finalize_round(body.game_id, body.round_id)
        _log("finalizeRound", body.game_id, body.round_id, tx)
        return tx
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


# ── Composite sequence endpoints ──────────────────────────────────────────


@router.post(
    "/settle-sequence",
    summary="Settle in one call: withdrawFromVault → settlement",
    description=(
        "Convenience endpoint for game owners. Executes both steps in "
        "sequence, skipping any step that was already done. "
        "Returns a dict of completed steps."
    ),
)
async def settle_sequence(
    body: VaultActionRequest,
    svc: RoundServiceDep,
) -> dict[str, TransactionResult]:
    try:
        return svc.execute_settle_sequence(body.game_id, body.round_id)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


class DistributeAndFinalizeRequest(BaseModel):
    """Request body for the distribute-and-finalize composite endpoint."""

    game_id: str
    round_id: int = Field(ge=0)
    winners: list[dict[str, str]] = Field(
        description='List of {"address": "0x…", "amount_wei": "123"} entries'
    )


@router.post(
    "/distribute-and-finalize",
    summary="Choose winners + finalize in one call",
    description=(
        "Assigns prizes to all listed winners then calls finalizeRound. "
        "Returns { choose_winners: [tx, ...], finalize_round: tx }."
    ),
)
async def distribute_and_finalize(
    body: DistributeAndFinalizeRequest,
    svc: RoundServiceDep,
) -> dict[str, Any]:
    try:
        pairs: list[tuple[str, int]] = [
            (w["address"], int(w["amount_wei"])) for w in body.winners
        ]
        return svc.execute_distribute_and_finalize(body.game_id, body.round_id, pairs)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


# ── Fee preview ────────────────────────────────────────────────────────────


@router.get(
    "/{game_id}/{round_id}/fee-preview",
    response_model=FeeBreakdown,
    summary="Off-chain fee breakdown preview",
    description=(
        "Pure arithmetic – no transaction. "
        "Pass ?yield_wei=N to model a hypothetical yield amount, "
        "or omit to use the on-chain yield (only non-zero after settlement)."
    ),
)
async def fee_preview(
    game_id: str,
    round_id: int,
    svc: RoundServiceDep,
    yield_wei: int | None = None,
) -> FeeBreakdown:
    try:
        return await svc.get_fee_preview(game_id, round_id, yield_wei)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc
