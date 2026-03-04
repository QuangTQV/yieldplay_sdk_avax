"""
yieldplay/api/routes/tx.py
───────────────────────────
Non-custodial transaction endpoints.

Architecture
────────────
                                ┌─────────────┐
  Frontend wallet               │  YieldPlay  │
  (MetaMask / WalletConnect)    │     API     │
  ─────────────────────────     └──────┬──────┘
                                       │
  1. POST /tx/build/deposit            │  build_unsigned_tx()
     { from, game_id, ... }   ────────►│  → {to, data, gas, nonce, chainId, gasPrice}
     ◄─ unsigned tx ──────────         │
                                       │
  2. user signs in wallet              │
     (no server involvement)           │
                                       │
  3. POST /tx/broadcast                │  broadcast_signed_tx()
     { signed_tx: "0x..." }   ────────►│  → {tx_hash: "0x..."}
     ◄─ tx_hash ─────────────          │

The server NEVER sees or stores the user's private key.

Endpoints
─────────
  POST /api/v1/tx/build/deposit      → UnsignedTxResponse
  POST /api/v1/tx/build/claim        → UnsignedTxResponse
  POST /api/v1/tx/build/approve      → UnsignedTxResponse
  POST /api/v1/tx/build/game         → UnsignedTxResponse  (game owner)
  POST /api/v1/tx/build/round        → UnsignedTxResponse  (game owner)
  POST /api/v1/tx/build/deposit-to-vault    → UnsignedTxResponse
  POST /api/v1/tx/build/withdraw-from-vault → UnsignedTxResponse
  POST /api/v1/tx/build/settlement   → UnsignedTxResponse
  POST /api/v1/tx/build/choose-winner → UnsignedTxResponse
  POST /api/v1/tx/build/finalize-round → UnsignedTxResponse
  POST /api/v1/tx/broadcast          → BroadcastResponse
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field
from web3 import Web3

from yieldplay.api.deps import SDKDep, handle_sdk_error

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tx", tags=["Transactions (Non-Custodial)"])

_MAX_UINT256 = 2**256 - 1


# ── Request / Response models ──────────────────────────────────────────────


class UnsignedTxResponse(BaseModel):
    """
    An unsigned transaction ready to be signed by the user's wallet.

    Frontend usage (ethers.js v6):
        const provider = new BrowserProvider(window.ethereum)
        const signer   = await provider.getSigner()
        const txHash   = await signer.sendTransaction(unsignedTx)

    Frontend usage (viem):
        const hash = await walletClient.sendTransaction(unsignedTx)
    """

    # Use camelCase field names directly so FastAPI serialises them correctly
    # without needing alias (which confuses Pydantic v2 schema generation when
    # combined with from __future__ import annotations).
    to: str = Field(description="Contract address")
    data: str = Field(description="Encoded calldata (0x…)")
    gas: int = Field(description="Gas limit")
    nonce: int = Field(description="Sender nonce")
    chainId: int = Field(description="EIP-155 chain ID")
    value: int = Field(default=0, description="ETH value in wei")
    gasPrice: Optional[int] = Field(default=None, description="Legacy gas price (wei)")
    maxFeePerGas: Optional[int] = Field(default=None)
    maxPriorityFeePerGas: Optional[int] = Field(default=None)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UnsignedTxResponse":
        return cls(
            to=d["to"],
            data=d["data"],
            gas=d["gas"],
            nonce=d["nonce"],
            chainId=d["chainId"],
            value=d.get("value", 0),
            gasPrice=d.get("gasPrice"),
            maxFeePerGas=d.get("maxFeePerGas"),
            maxPriorityFeePerGas=d.get("maxPriorityFeePerGas"),
        )


class BroadcastRequest(BaseModel):
    signed_tx: str = Field(
        description="Raw signed transaction hex string (0x-prefixed) "
        "produced by the frontend wallet after signing the unsigned tx."
    )


class BroadcastResponse(BaseModel):
    tx_hash: str = Field(description="Transaction hash (0x-prefixed)")


# ── Build request bodies ───────────────────────────────────────────────────


class BuildDepositRequest(BaseModel):
    from_address: str = Field(
        description="User's wallet address (not stored, just for nonce/gas)"
    )
    game_id: str
    round_id: int = Field(ge=0)
    amount_wei: str = Field(
        description="Deposit amount in wei (string to avoid precision loss)"
    )


class BuildClaimRequest(BaseModel):
    from_address: str
    game_id: str
    round_id: int = Field(ge=0)


class BuildApproveRequest(BaseModel):
    from_address: str
    token_address: str
    amount_wei: Optional[str] = Field(
        default=None, description="Wei amount to approve; null = MaxUint256 (unlimited)"
    )


class BuildGameRequest(BaseModel):
    from_address: str = Field(description="Game owner wallet address")
    game_name: str = Field(min_length=1, max_length=100)
    dev_fee_bps: int = Field(
        ge=0, le=5_000, description="Dev fee in bps, max 5000 = 50%"
    )
    treasury: str = Field(description="Address that receives dev fees")


class BuildRoundRequest(BaseModel):
    from_address: str
    game_id: str
    start_ts: int = Field(ge=0)
    end_ts: int = Field(ge=0)
    lock_time: int = Field(ge=0)
    deposit_fee_bps: int = Field(ge=0, le=1_000)
    payment_token: str


class BuildVaultActionRequest(BaseModel):
    from_address: str
    game_id: str
    round_id: int = Field(ge=0)


class BuildChooseWinnerRequest(BaseModel):
    from_address: str
    game_id: str
    round_id: int = Field(ge=0)
    winner: str = Field(description="Winner wallet address")
    amount_wei: str = Field(description="Prize amount in wei")


# ── Helpers ────────────────────────────────────────────────────────────────


def _build(sdk: Any, contract_fn: Any, from_address: str) -> UnsignedTxResponse:
    """Delegate to sdk.build_unsigned_tx and wrap in UnsignedTxResponse."""
    raw = sdk.build_unsigned_tx(contract_fn, from_address)
    return UnsignedTxResponse.from_dict(raw)


# ══════════════════════════════════════════════════════════════════════════
# BUILD endpoints — return unsigned tx for frontend to sign
# ══════════════════════════════════════════════════════════════════════════


@router.post(
    "/build/deposit",
    response_model=UnsignedTxResponse,
    summary="Build unsigned deposit tx",
    description=(
        "Returns an unsigned transaction that the user signs in their wallet. "
        "Validates round status and token balance **before** building — "
        "returns 400 immediately if the deposit would fail."
    ),
)
async def build_deposit(body: BuildDepositRequest, sdk: SDKDep) -> UnsignedTxResponse:
    try:
        amount = int(body.amount_wei)
        # Pre-flight: status + balance check (raises typed error, not 0x revert)
        sdk._preflight_deposit(body.game_id, body.round_id, amount, body.from_address)

        # Ensure allowance — if insufficient, caller must first sign an approve tx
        # We check here and raise InsufficientAllowanceError so frontend knows
        round_info = sdk.get_round(body.game_id, body.round_id)
        allowance = sdk.get_token_allowance(round_info.payment_token, body.from_address)
        if allowance < amount:
            from yieldplay.exceptions import InsufficientAllowanceError

            raise InsufficientAllowanceError(
                f"Allowance too low: have {allowance}, need {amount}. "
                "Call /tx/build/approve first.",
                f"token={round_info.payment_token}",
            )

        return _build(
            sdk,
            sdk._contract.functions.deposit(
                sdk._to_bytes32(body.game_id), body.round_id, amount
            ),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/build/claim",
    response_model=UnsignedTxResponse,
    summary="Build unsigned claim tx",
)
async def build_claim(body: BuildClaimRequest, sdk: SDKDep) -> UnsignedTxResponse:
    try:
        sdk._preflight_claim(body.game_id, body.round_id, body.from_address)
        return _build(
            sdk,
            sdk._contract.functions.claim(sdk._to_bytes32(body.game_id), body.round_id),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/build/approve",
    response_model=UnsignedTxResponse,
    summary="Build unsigned ERC-20 approve tx",
    description=(
        "Build an approve tx for the YieldPlay contract to spend tokens on the user's behalf. "
        "amount_wei=null approves MaxUint256 (unlimited, one-time approval)."
    ),
)
async def build_approve(body: BuildApproveRequest, sdk: SDKDep) -> UnsignedTxResponse:
    try:
        from yieldplay.abi import ERC20_ABI

        spender_amount = int(body.amount_wei) if body.amount_wei else _MAX_UINT256
        token = sdk.w3.eth.contract(
            address=Web3.to_checksum_address(body.token_address),
            abi=ERC20_ABI,
        )
        return _build(
            sdk,
            token.functions.approve(
                Web3.to_checksum_address(sdk._config.yield_play_address),
                spender_amount,
            ),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/build/game",
    response_model=UnsignedTxResponse,
    summary="Build unsigned createGame tx (game owner)",
)
async def build_create_game(body: BuildGameRequest, sdk: SDKDep) -> UnsignedTxResponse:
    try:
        # Validate before building
        from yieldplay.exceptions import InvalidAmountError, InvalidDevFeeBpsError

        if not (0 <= body.dev_fee_bps <= 5_000):
            raise InvalidDevFeeBpsError(
                f"dev_fee_bps must be 0–5000 (got {body.dev_fee_bps})", "max 50%"
            )
        if not Web3.is_address(body.treasury):
            raise InvalidAmountError("Invalid treasury address", body.treasury)

        return _build(
            sdk,
            sdk._contract.functions.createGame(
                body.game_name,
                body.dev_fee_bps,
                Web3.to_checksum_address(body.treasury),
            ),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/build/game/{game_id}/preview-id",
    response_model=dict[str, str],
    summary="Preview game_id before creating (offline, no gas)",
    description="Returns the game_id that will be assigned — computed offline, no RPC call.",
)
async def preview_game_id(
    game_id: str, owner: str, game_name: str, sdk: SDKDep
) -> dict[str, str]:
    return {"game_id": sdk.calculate_game_id(owner, game_name)}


@router.post(
    "/build/round",
    response_model=UnsignedTxResponse,
    summary="Build unsigned createRound tx (game owner)",
)
async def build_create_round(
    body: BuildRoundRequest, sdk: SDKDep
) -> UnsignedTxResponse:
    try:
        import time as _time

        from yieldplay.exceptions import InvalidAmountError

        now = int(_time.time())
        if body.end_ts <= body.start_ts:
            raise InvalidAmountError(
                "end_ts must be > start_ts", f"start={body.start_ts} end={body.end_ts}"
            )
        if body.end_ts <= now:
            raise InvalidAmountError(
                "end_ts is in the past", f"end_ts={body.end_ts} now={now}"
            )

        return _build(
            sdk,
            sdk._contract.functions.createRound(
                sdk._to_bytes32(body.game_id),
                body.start_ts,
                body.end_ts,
                body.lock_time,
                body.deposit_fee_bps,
                Web3.to_checksum_address(body.payment_token),
            ),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/build/deposit-to-vault",
    response_model=UnsignedTxResponse,
    summary="Build unsigned depositToVault tx (game owner)",
)
async def build_deposit_to_vault(
    body: BuildVaultActionRequest, sdk: SDKDep
) -> UnsignedTxResponse:
    try:
        return _build(
            sdk,
            sdk._contract.functions.depositToVault(
                sdk._to_bytes32(body.game_id), body.round_id
            ),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/build/withdraw-from-vault",
    response_model=UnsignedTxResponse,
    summary="Build unsigned withdrawFromVault tx (game owner)",
)
async def build_withdraw_from_vault(
    body: BuildVaultActionRequest, sdk: SDKDep
) -> UnsignedTxResponse:
    try:
        return _build(
            sdk,
            sdk._contract.functions.withdrawFromVault(
                sdk._to_bytes32(body.game_id), body.round_id
            ),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/build/settlement",
    response_model=UnsignedTxResponse,
    summary="Build unsigned settlement tx (game owner)",
)
async def build_settlement(
    body: BuildVaultActionRequest, sdk: SDKDep
) -> UnsignedTxResponse:
    try:
        return _build(
            sdk,
            sdk._contract.functions.settlement(
                sdk._to_bytes32(body.game_id), body.round_id
            ),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/build/choose-winner",
    response_model=UnsignedTxResponse,
    summary="Build unsigned chooseWinner tx (game owner)",
)
async def build_choose_winner(
    body: BuildChooseWinnerRequest, sdk: SDKDep
) -> UnsignedTxResponse:
    try:
        return _build(
            sdk,
            sdk._contract.functions.chooseWinner(
                sdk._to_bytes32(body.game_id),
                body.round_id,
                Web3.to_checksum_address(body.winner),
                int(body.amount_wei),
            ),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


@router.post(
    "/build/finalize-round",
    response_model=UnsignedTxResponse,
    summary="Build unsigned finalizeRound tx (game owner)",
)
async def build_finalize_round(
    body: BuildVaultActionRequest, sdk: SDKDep
) -> UnsignedTxResponse:
    try:
        return _build(
            sdk,
            sdk._contract.functions.finalizeRound(
                sdk._to_bytes32(body.game_id), body.round_id
            ),
            body.from_address,
        )
    except Exception as exc:
        raise handle_sdk_error(exc) from exc


# ══════════════════════════════════════════════════════════════════════════
# BROADCAST — accept signed tx, push to chain
# ══════════════════════════════════════════════════════════════════════════


@router.post(
    "/broadcast",
    response_model=BroadcastResponse,
    summary="Broadcast a signed transaction",
    description=(
        "Push a raw signed transaction to the network. "
        "The signed_tx must be produced by the user's wallet after signing "
        "an unsigned tx from one of the /build/* endpoints. "
        "Returns {tx_hash} immediately — does NOT wait for confirmation."
    ),
)
async def broadcast(body: BroadcastRequest, sdk: SDKDep) -> BroadcastResponse:
    try:
        tx_hash = sdk.broadcast_signed_tx(body.signed_tx)
        logger.info("broadcast | hash=%s", tx_hash)
        return BroadcastResponse(tx_hash=tx_hash)
    except Exception as exc:
        raise handle_sdk_error(exc) from exc
