"""
yieldplay/types.py
──────────────────
All domain types, Pydantic models and enums for YieldPlay SDK.
No business logic here – pure data definitions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import IntEnum
from typing import Optional

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class RoundStatus(IntEnum):
    NOT_STARTED = 0  # Round chưa bắt đầu
    IN_PROGRESS = 1  # Đang nhận deposit
    LOCKING = 2  # Đang khóa, không nhận deposit
    CHOOSING_WINNERS = 3  # Game owner chọn người thắng
    DISTRIBUTING_REWARDS = 4  # Người dùng có thể claim

    def label(self) -> str:
        return {
            RoundStatus.NOT_STARTED: "Not Started",
            RoundStatus.IN_PROGRESS: "In Progress",
            RoundStatus.LOCKING: "Locking",
            RoundStatus.CHOOSING_WINNERS: "Choosing Winners",
            RoundStatus.DISTRIBUTING_REWARDS: "Distributing Rewards",
        }[self]


# ──────────────────────────────────────────────
# On-chain data models (Layer 1 outputs)
# ──────────────────────────────────────────────


class GameInfo(BaseModel):
    """Mapped from contract getGame() tuple return."""

    owner: str
    game_name: str
    dev_fee_bps: int = Field(ge=0, le=10_000)
    treasury: str
    round_counter: int = Field(ge=0)
    initialized: bool

    @property
    def dev_fee_pct(self) -> float:
        return self.dev_fee_bps / 100.0


class RoundInfo(BaseModel):
    """Mapped from contract getRound() tuple return."""

    game_id: str
    round_id: int = Field(ge=0)
    total_deposit: int = Field(ge=0)
    bonus_prize_pool: int = Field(ge=0)
    dev_fee: int = Field(ge=0)
    total_win: int = Field(ge=0)
    yield_amount: int = Field(ge=0)
    payment_token: str
    vault: str
    deposit_fee_bps: int = Field(ge=0, le=1_000)
    start_ts: int = Field(ge=0)
    end_ts: int = Field(ge=0)
    lock_time: int = Field(ge=0)
    initialized: bool
    is_settled: bool
    status: RoundStatus
    is_withdrawn: bool

    @property
    def deposit_fee_pct(self) -> float:
        return self.deposit_fee_bps / 100.0

    @property
    def total_prize_pool(self) -> int:
        """Prize pool = yield prize + bonus prize pool."""
        return self.total_win + self.bonus_prize_pool


class UserDepositInfo(BaseModel):
    """Mapped from contract getUserDeposit() tuple return."""

    deposit_amount: int = Field(ge=0)
    amount_to_claim: int = Field(ge=0)
    is_claimed: bool
    exists: bool


class TransactionResult(BaseModel):
    """Result of a state-changing contract call."""

    tx_hash: str
    block_number: Optional[int] = None
    gas_used: Optional[int] = None
    status: int = Field(default=1, description="1 = success, 0 = reverted")

    @property
    def succeeded(self) -> bool:
        return self.status == 1


class FeeBreakdown(BaseModel):
    """Human-readable fee calculation for a round."""

    total_deposit_gross: int  # Wei: raw deposits before deposit fee
    deposit_fee_collected: int  # Wei: deposit fee → bonus prize pool
    net_deposits: int  # Wei: principal returned to users
    vault_yield: int  # Wei: raw yield from vault
    performance_fee: int  # Wei: 20% of yield → protocol treasury
    dev_fee: int  # Wei: devFeeBps% of yield after perf fee → game treasury
    yield_prize: int  # Wei: yield after both fees → winners
    total_prize_pool: int  # Wei: yield_prize + deposit_fee_collected


# ──────────────────────────────────────────────
# SDK Config
# ──────────────────────────────────────────────


class SDKConfig(BaseModel):
    """Initialisation config for Layer 1 contract client."""

    model_config = {"arbitrary_types_allowed": True}

    yield_play_address: str = Field(description="YieldPlay contract address (0x…)")
    rpc_url: str = Field(description="JSON-RPC endpoint URL")
    private_key: Optional[str] = Field(
        default=None,
        description="Hex private key for signing; None = read-only mode",
    )


# ──────────────────────────────────────────────
# API Request / Response models (Layer 2)
# ──────────────────────────────────────────────


class CreateGameRequest(BaseModel):
    game_name: str = Field(min_length=1, max_length=100)
    dev_fee_bps: int = Field(
        ge=0, le=10_000, description="Developer fee in basis points (0–10 000)"
    )
    treasury: str = Field(description="Address that receives dev fee")


class CreateGameResponse(BaseModel):
    game_id: str
    transaction: TransactionResult


def now_ts() -> int:
    return int(datetime.utcnow().timestamp())


def end_ts_30_days() -> int:
    return int((datetime.utcnow() + timedelta(days=30)).timestamp())


class CreateRoundRequest(BaseModel):
    game_id: str
    start_ts: int = Field(
        default_factory=now_ts, ge=0, description="Unix timestamp – round opens"
    )
    end_ts: int = Field(
        default_factory=end_ts_30_days,
        ge=0,
        description="Unix timestamp – deposit window closes",
    )
    lock_time: int = Field(
        default=0, ge=0, description="Lock duration in seconds after end_ts"
    )
    deposit_fee_bps: int = Field(
        default=0, ge=0, le=1_000, description="Deposit fee in basis points (0–1 000)"
    )
    payment_token: str = Field(description="ERC-20 token address accepted for deposits")


class CreateRoundResponse(BaseModel):
    round_id: int
    transaction: TransactionResult


class DepositRequest(BaseModel):
    game_id: str
    round_id: int = Field(ge=0)
    amount_wei: str = Field(
        description="Amount in wei (string to avoid precision loss)"
    )


class ClaimRequest(BaseModel):
    game_id: str
    round_id: int = Field(ge=0)


class ChooseWinnerRequest(BaseModel):
    game_id: str
    round_id: int = Field(ge=0)
    winner: str = Field(description="Winner wallet address")
    amount_wei: str = Field(description="Prize amount in wei")


class ApproveTokenRequest(BaseModel):
    token_address: str
    amount_wei: Optional[str] = Field(
        default=None,
        description="Amount in wei; None = approve unlimited (MaxUint256)",
    )


class TokenBalanceResponse(BaseModel):
    address: str
    token: str
    balance_wei: str
    balance_formatted: str


class RoundStatusResponse(BaseModel):
    game_id: str
    round_id: int
    status: RoundStatus
    status_label: str


class VaultActionRequest(BaseModel):
    game_id: str
    round_id: int = Field(ge=0)


class DeployedAmountsResponse(BaseModel):
    game_id: str
    round_id: int
    deployed_amount_wei: str
    deployed_shares_wei: str


# ──────────────────────────────────────────────
# Composite / aggregated response models (Layer 2 service outputs)
# ──────────────────────────────────────────────


class UserRoundSummary(BaseModel):
    """
    One-stop view of a user's position in a round.

    Aggregates: getUserDeposit + getRound + getCurrentStatus
                + getTokenBalance + getTokenAllowance
    """

    # Identity
    user_address: str
    game_id: str
    round_id: int

    # Round state
    status: RoundStatus
    status_label: str
    round_start_ts: int
    round_end_ts: int
    lock_until_ts: int  # end_ts + lock_time

    # User deposit position
    has_deposit: bool
    deposit_amount_wei: str
    amount_to_claim_wei: str
    is_claimed: bool

    # Actionability flags (derived)
    can_deposit: bool  # status == IN_PROGRESS and has balance and not already deposited
    can_claim: bool  # status == DISTRIBUTING_REWARDS and not is_claimed and has_deposit
    needs_approval: bool  # allowance < deposit_amount (only meaningful pre-deposit)

    # Token context
    payment_token: str
    token_balance_wei: str
    token_allowance_wei: str

    # Round aggregate context
    total_deposit_wei: str
    total_participants_share_pct: Optional[float] = Field(
        default=None,
        description="User deposit as % of total round deposit",
    )
    prize_pool_wei: str  # total_win + bonus_prize_pool at current moment
    participant_count: Optional[int] = Field(
        default=None,
        description="Number of unique depositors (from DB index, None if not yet indexed)",
    )


class RoundDashboard(BaseModel):
    """
    Full operational view of a round for game owners / dashboards.

    Aggregates: getGame + getRound + getCurrentStatus
                + getDeployedAmounts + getDeployedShares
                + calculateFeeBreakdown (projected)
    """

    # Game metadata
    game_id: str
    game_name: str
    game_owner: str
    game_treasury: str
    dev_fee_bps: int
    dev_fee_pct: float

    # Round metadata
    round_id: int
    payment_token: str
    vault_address: str
    deposit_fee_bps: int
    deposit_fee_pct: float
    start_ts: int
    end_ts: int
    lock_until_ts: int

    # Live state
    status: RoundStatus
    status_label: str
    is_settled: bool
    is_withdrawn: bool

    # Financials (wei as str)
    total_deposit_wei: str
    bonus_prize_pool_wei: str
    yield_amount_wei: str
    total_win_wei: str
    deployed_amount_wei: str
    deployed_shares_wei: str

    # Projected fee breakdown (uses actual yield if settled, else 0)
    fee_breakdown: FeeBreakdown

    # Lifecycle checklist for game owners
    next_action: str  # human-readable next step
    participant_count: Optional[int] = Field(
        default=None,
        description="Number of unique depositors (from DB, None if not yet indexed)",
    )


class UserPortfolioEntry(BaseModel):
    """Summary of a user's participation in one (game, round) pair."""

    game_id: str
    game_name: str
    round_id: int
    status: RoundStatus
    status_label: str
    deposit_amount_wei: str
    amount_to_claim_wei: str
    is_claimed: bool
    can_claim: bool


class UserPortfolio(BaseModel):
    """All rounds a user has participated in across multiple games."""

    user_address: str
    entries: list[UserPortfolioEntry]
    total_deposited_wei: str
    total_claimable_wei: str
    unclaimed_count: int


class DepositEligibility(BaseModel):
    """
    Pre-flight check before a user attempts to deposit.

    Answers: can this user deposit *amount_wei* into this round right now?
    """

    user_address: str
    game_id: str
    round_id: int
    amount_wei: str

    eligible: bool
    reasons_blocked: list[str]  # empty when eligible == True

    # Breakdown of each check
    round_is_active: bool
    has_sufficient_balance: bool
    has_sufficient_allowance: bool
    already_deposited: bool  # True = user already has a position (re-deposit check)

    # Context
    token_balance_wei: str
    token_allowance_wei: str
    deposit_fee_bps: int
    net_amount_after_fee_wei: str  # what user actually gets credited


class ClaimEligibility(BaseModel):
    """Pre-flight check before a user attempts to claim."""

    user_address: str
    game_id: str
    round_id: int

    eligible: bool
    reasons_blocked: list[str]

    round_is_distributing: bool
    has_deposit: bool
    already_claimed: bool

    principal_wei: str
    prize_wei: str
    total_claimable_wei: str


class RoundWinnerEntry(BaseModel):
    """One winner's allocation in a round."""

    winner_address: str
    prize_wei: str
    deposit_wei: str
    is_claimed: bool


class BatchRoundStatus(BaseModel):
    """Status of multiple rounds in one response."""

    game_id: str
    rounds: list[RoundStatusResponse]


# Re-export RoundStatusResponse here so services can import from one place
__all__ = [
    "RoundStatus",
    "GameInfo",
    "RoundInfo",
    "UserDepositInfo",
    "TransactionResult",
    "FeeBreakdown",
    "SDKConfig",
    "CreateGameRequest",
    "CreateGameResponse",
    "CreateRoundRequest",
    "CreateRoundResponse",
    "DepositRequest",
    "ClaimRequest",
    "ChooseWinnerRequest",
    "ApproveTokenRequest",
    "TokenBalanceResponse",
    "RoundStatusResponse",
    "VaultActionRequest",
    "DeployedAmountsResponse",
    "UserRoundSummary",
    "RoundDashboard",
    "UserPortfolioEntry",
    "UserPortfolio",
    "DepositEligibility",
    "ClaimEligibility",
    "RoundWinnerEntry",
    "BatchRoundStatus",
]
