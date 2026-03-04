"""
yieldplay/api/routes/games.py – Game & round management endpoints.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, status
from yieldplay.api.deps import RoundServiceDep, SDKDep, UserServiceDep, handle_sdk_error
from yieldplay.types import (
    BatchRoundStatus, CreateGameRequest, CreateGameResponse,
    CreateRoundRequest, CreateRoundResponse, GameInfo,
    RoundDashboard, RoundInfo, RoundStatusResponse, RoundWinnerEntry,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/games", tags=["Games"])


@router.post("", response_model=CreateGameResponse, status_code=status.HTTP_201_CREATED)
async def create_game(body: CreateGameRequest, sdk: SDKDep) -> CreateGameResponse:
    try:
        game_id, tx = sdk.create_game(body.game_name, body.dev_fee_bps, body.treasury)
        return CreateGameResponse(game_id=game_id, transaction=tx)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{game_id}", response_model=GameInfo)
async def get_game(game_id: str, sdk: SDKDep) -> GameInfo:
    try:
        return sdk.get_game(game_id)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/calculate-id", response_model=dict[str, str])
async def calculate_game_id(owner: str, game_name: str, sdk: SDKDep) -> dict[str, str]:
    try:
        return {"game_id": sdk.calculate_game_id(owner, game_name)}
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post("/{game_id}/rounds", response_model=CreateRoundResponse,
             status_code=status.HTTP_201_CREATED)
async def create_round(game_id: str, body: CreateRoundRequest, sdk: SDKDep) -> CreateRoundResponse:
    if body.game_id != game_id:
        raise HTTPException(422, detail="game_id in path and body must match")
    if body.end_ts <= body.start_ts:
        raise HTTPException(422, detail="end_ts must be greater than start_ts")
    try:
        round_id, tx = sdk.create_round(
            game_id=game_id, start_ts=body.start_ts, end_ts=body.end_ts,
            lock_time=body.lock_time, deposit_fee_bps=body.deposit_fee_bps,
            payment_token=body.payment_token,
        )
        return CreateRoundResponse(round_id=round_id, transaction=tx)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{game_id}/rounds", response_model=list[RoundInfo],
            description="Pass ?dashboard=true for full operational data per round.")
async def list_rounds(
    game_id: str,
    dashboard: bool = False,
    offset: int = 0,
    limit: int = 50,
    svc: RoundServiceDep = ...,  # type: ignore[assignment]
) -> list[RoundInfo] | list[RoundDashboard]:
    try:
        return await svc.list_rounds(game_id, include_dashboard=dashboard,  # type: ignore[return-value]
                                     offset=offset, limit=limit)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{game_id}/rounds/batch-status", response_model=BatchRoundStatus,
            description="?round_ids=0,1,2")
async def batch_round_status(
    game_id: str, round_ids: str,
    svc: UserServiceDep = ...,  # type: ignore[assignment]
) -> BatchRoundStatus:
    try:
        ids = [int(r.strip()) for r in round_ids.split(",") if r.strip().isdigit()]
        return await svc.get_batch_round_status(game_id, ids)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{game_id}/rounds/{round_id}", response_model=RoundInfo)
async def get_round(game_id: str, round_id: int, sdk: SDKDep) -> RoundInfo:
    try:
        return sdk.get_round(game_id, round_id)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{game_id}/rounds/{round_id}/status", response_model=RoundStatusResponse)
async def get_round_status(game_id: str, round_id: int, sdk: SDKDep) -> RoundStatusResponse:
    try:
        s = sdk.get_current_status(game_id, round_id)
        return RoundStatusResponse(game_id=game_id, round_id=round_id,
                                   status=s, status_label=s.label())
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{game_id}/rounds/{round_id}/dashboard", response_model=RoundDashboard,
            description=(
                "Full round dashboard: game info + round info + live vault state "
                "+ fee projection + participant count (from DB)."
            ))
async def get_round_dashboard(
    game_id: str, round_id: int,
    svc: RoundServiceDep = ...,  # type: ignore[assignment]
) -> RoundDashboard:
    try:
        return await svc.get_round_dashboard(game_id, round_id)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{game_id}/rounds/{round_id}/participants",
            description=(
                "List all depositors in a round (paginated). "
                "Powered by DB index — impossible to query on-chain."
            ))
async def get_round_participants(
    game_id: str, round_id: int,
    offset: int = 0, limit: int = 100,
    svc: RoundServiceDep = ...,  # type: ignore[assignment]
) -> list[dict[str, str | int | bool]]:
    try:
        return await svc.get_round_participants(game_id, round_id, offset=offset, limit=limit)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.get("/{game_id}/rounds/{round_id}/winners", response_model=list[RoundWinnerEntry],
            description="List all winners for a round with their deposit amounts.")
async def get_round_winners(
    game_id: str, round_id: int,
    svc: RoundServiceDep = ...,  # type: ignore[assignment]
) -> list[RoundWinnerEntry]:
    try:
        return await svc.get_round_winners(game_id, round_id)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc
