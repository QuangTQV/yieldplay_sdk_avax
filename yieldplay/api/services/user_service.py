"""
yieldplay/api/services/user_service.py
────────────────────────────────────────
User-centric business logic.

DB-first strategy:
  1. Try to answer from DB (fast, no RPC call needed)
  2. Fall back to contract call if DB has no data yet (indexer lag)
  3. Always call contract for write-sensitive fields (is_claimed, amount_to_claim)
     to ensure freshness

This gives the best of both worlds:
  - Reverse-index queries (user portfolio) answered from DB
  - Read-heavy paths (balance, status) answered from DB cache
  - Claim / deposit eligibility always verified against chain
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from yieldplay.contract import YieldPlayContract
from yieldplay.db.models import Round
from yieldplay.repositories.deposit_repo import DepositRepository
from yieldplay.repositories.round_repo import GameRepository, RoundRepository
from yieldplay.types import (
    BatchRoundStatus,
    ClaimEligibility,
    DepositEligibility,
    RoundStatus,
    RoundStatusResponse,
    UserPortfolio,
    UserPortfolioEntry,
    UserRoundSummary,
)

logger = logging.getLogger(__name__)


class UserService:
    """
    User-centric service.  Requires both a DB session and the contract client
    so it can choose the fastest/most-accurate source per query.
    """

    def __init__(self, contract: YieldPlayContract, session: AsyncSession) -> None:
        self._c = contract
        self._s = session
        self._dep_repo = DepositRepository(session)
        self._round_repo = RoundRepository(session)
        self._game_repo = GameRepository(session)

    # ── User round summary ─────────────────────────────────────────────────

    async def get_user_round_summary(
        self,
        user_address: str,
        game_id: str,
        round_id: int,
    ) -> UserRoundSummary:
        """
        Full picture of a user's position in a single round.

        Sources:
          • round metadata   → DB first, fallback contract
          • status           → contract (authoritative, changes on-chain)
          • user deposit     → contract (must be fresh for claim checks)
          • token balance    → contract (live balance)
          • allowance        → contract (live allowance)
        """
        # Round metadata: DB first (avoids an RPC call on every page load)
        db_round: Optional[Round] = await self._round_repo.get_round(game_id, round_id)

        # Status and user deposit always from chain (safety-critical)
        status = self._c.get_current_status(game_id, round_id)
        user_deposit = self._c.get_user_deposit(game_id, round_id, user_address)

        # Token info: use DB round if available, otherwise fetch from contract
        if db_round:
            token = db_round.payment_token
            end_ts = db_round.end_ts
            start_ts = db_round.start_ts
            lock_until_ts = db_round.end_ts + db_round.lock_time
            total_deposit = int(db_round.total_deposit)
            total_win = int(db_round.total_win)
            bonus_prize_pool = int(db_round.bonus_prize_pool)
        else:
            round_info = self._c.get_round(game_id, round_id)
            token = round_info.payment_token
            end_ts = round_info.end_ts
            start_ts = round_info.start_ts
            lock_until_ts = round_info.end_ts + round_info.lock_time
            total_deposit = round_info.total_deposit
            total_win = round_info.total_win
            bonus_prize_pool = round_info.bonus_prize_pool

        balance_wei = self._c.get_token_balance(token, user_address)
        allowance_wei = self._c.get_token_allowance(token, user_address)

        # Derived flags
        can_deposit = (
            status == RoundStatus.IN_PROGRESS
            and not user_deposit.exists
            and balance_wei > 0
        )
        can_claim = (
            status == RoundStatus.DISTRIBUTING_REWARDS
            and user_deposit.exists
            and not user_deposit.is_claimed
        )
        needs_approval = (
            status == RoundStatus.IN_PROGRESS and allowance_wei < balance_wei
        )

        # Pool share percentage
        share_pct: Optional[float] = None
        if total_deposit > 0 and user_deposit.deposit_amount > 0:
            share_pct = round(user_deposit.deposit_amount / total_deposit * 100, 4)

        # DB participant count (not available from contract)
        stats = await self._dep_repo.get_round_deposit_stats(game_id, round_id)
        participant_count = stats.participant_count if stats else None

        return UserRoundSummary(
            user_address=user_address,
            game_id=game_id,
            round_id=round_id,
            status=status,
            status_label=status.label(),
            round_start_ts=start_ts,
            round_end_ts=end_ts,
            lock_until_ts=lock_until_ts,
            has_deposit=user_deposit.exists,
            deposit_amount_wei=str(user_deposit.deposit_amount),
            amount_to_claim_wei=str(user_deposit.amount_to_claim),
            is_claimed=user_deposit.is_claimed,
            can_deposit=can_deposit,
            can_claim=can_claim,
            needs_approval=needs_approval,
            payment_token=token,
            token_balance_wei=str(balance_wei),
            token_allowance_wei=str(allowance_wei),
            total_deposit_wei=str(total_deposit),
            total_participants_share_pct=share_pct,
            prize_pool_wei=str(total_win + bonus_prize_pool),
            participant_count=participant_count,
        )

    # ── Deposit eligibility ────────────────────────────────────────────────

    async def check_deposit_eligibility(
        self,
        user_address: str,
        game_id: str,
        round_id: int,
        amount_wei: int,
    ) -> DepositEligibility:
        """All checks done against contract (safety-critical)."""
        status = self._c.get_current_status(game_id, round_id)

        # Use DB for deposit_fee_bps to avoid an extra RPC call
        db_round = await self._round_repo.get_round(game_id, round_id)
        if db_round:
            token = db_round.payment_token
            deposit_fee_bps = db_round.deposit_fee_bps
        else:
            round_info = self._c.get_round(game_id, round_id)
            token = round_info.payment_token
            deposit_fee_bps = round_info.deposit_fee_bps

        user_deposit = self._c.get_user_deposit(game_id, round_id, user_address)
        balance_wei = self._c.get_token_balance(token, user_address)
        allowance_wei = self._c.get_token_allowance(token, user_address)

        round_is_active = status == RoundStatus.IN_PROGRESS
        has_balance = balance_wei >= amount_wei
        has_allowance = allowance_wei >= amount_wei
        already_deposited = user_deposit.exists

        fee = amount_wei * deposit_fee_bps // 10_000
        net_amount = amount_wei - fee

        blocked: list[str] = []
        if not round_is_active:
            blocked.append(f"Round is not accepting deposits (status: {status.label()})")
        if not has_balance:
            blocked.append(f"Insufficient balance – short by {amount_wei - balance_wei} wei")
        if not has_allowance:
            blocked.append(f"Insufficient allowance – approve at least {amount_wei} wei")
        if already_deposited:
            blocked.append("Already deposited in this round")

        return DepositEligibility(
            user_address=user_address,
            game_id=game_id,
            round_id=round_id,
            amount_wei=str(amount_wei),
            eligible=len(blocked) == 0,
            reasons_blocked=blocked,
            round_is_active=round_is_active,
            has_sufficient_balance=has_balance,
            has_sufficient_allowance=has_allowance,
            already_deposited=already_deposited,
            token_balance_wei=str(balance_wei),
            token_allowance_wei=str(allowance_wei),
            deposit_fee_bps=deposit_fee_bps,
            net_amount_after_fee_wei=str(net_amount),
        )

    # ── Claim eligibility ──────────────────────────────────────────────────

    async def check_claim_eligibility(
        self,
        user_address: str,
        game_id: str,
        round_id: int,
    ) -> ClaimEligibility:
        """Always contract-first (claim state is safety-critical)."""
        status = self._c.get_current_status(game_id, round_id)
        user_deposit = self._c.get_user_deposit(game_id, round_id, user_address)

        round_distributing = status == RoundStatus.DISTRIBUTING_REWARDS
        has_deposit = user_deposit.exists
        already_claimed = user_deposit.is_claimed

        blocked: list[str] = []
        if not round_distributing:
            blocked.append(f"Round not distributing rewards yet (status: {status.label()})")
        if not has_deposit:
            blocked.append("No deposit found for this user in this round")
        if already_claimed:
            blocked.append("Already claimed")

        return ClaimEligibility(
            user_address=user_address,
            game_id=game_id,
            round_id=round_id,
            eligible=len(blocked) == 0,
            reasons_blocked=blocked,
            round_is_distributing=round_distributing,
            has_deposit=has_deposit,
            already_claimed=already_claimed,
            principal_wei=str(user_deposit.deposit_amount),
            prize_wei=str(user_deposit.amount_to_claim),
            total_claimable_wei=str(user_deposit.deposit_amount + user_deposit.amount_to_claim),
        )

    # ── User portfolio (DB-powered reverse index) ──────────────────────────

    async def get_user_portfolio(
        self,
        user_address: str,
        game_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> UserPortfolio:
        """
        Aggregate all rounds a user has participated in.

        FULLY DB-DRIVEN – no contract calls needed.
        The DB join on deposits ← claims gives us claim status without
        calling getUserDeposit per round (which would be O(N) RPC calls).

        Game names are looked up from the games table.
        Status is read from the rounds table (updated by indexer).
        """
        entries_raw = await self._dep_repo.get_user_rounds(
            user_address, game_id=game_id, offset=offset, limit=limit
        )

        entries: list[UserPortfolioEntry] = []
        total_deposited = 0
        total_claimable = 0
        unclaimed_count = 0

        for entry in entries_raw:
            # Look up game name from DB
            db_game = await self._game_repo.get_game(entry.game_id)
            game_name = db_game.game_name if db_game else entry.game_id

            # Round status from DB (set by indexer on every status change)
            db_round = await self._round_repo.get_round(entry.game_id, entry.round_id)
            status = (
                RoundStatus(db_round.status)
                if db_round
                else RoundStatus.NOT_STARTED
            )

            can_claim = (
                status == RoundStatus.DISTRIBUTING_REWARDS and not entry.is_claimed
            )

            entries.append(
                UserPortfolioEntry(
                    game_id=entry.game_id,
                    game_name=game_name,
                    round_id=entry.round_id,
                    status=status,
                    status_label=status.label(),
                    deposit_amount_wei=str(entry.net_amount),
                    amount_to_claim_wei=str(entry.prize),
                    is_claimed=entry.is_claimed,
                    can_claim=can_claim,
                )
            )

            total_deposited += entry.net_amount
            if can_claim:
                total_claimable += entry.net_amount + entry.prize
                unclaimed_count += 1

        return UserPortfolio(
            user_address=user_address,
            entries=entries,
            total_deposited_wei=str(total_deposited),
            total_claimable_wei=str(total_claimable),
            unclaimed_count=unclaimed_count,
        )

    # ── Batch round status ─────────────────────────────────────────────────

    async def get_batch_round_status(
        self,
        game_id: str,
        round_ids: list[int],
    ) -> BatchRoundStatus:
        """
        DB-first: get status for many rounds without N RPC calls.
        Falls back to contract per-round if not in DB yet.
        """
        result: list[RoundStatusResponse] = []

        for round_id in round_ids:
            db_round = await self._round_repo.get_round(game_id, round_id)
            if db_round:
                status = RoundStatus(db_round.status)
            else:
                try:
                    status = self._c.get_current_status(game_id, round_id)
                except Exception as exc:
                    logger.warning("Cannot get status for round %s: %s", round_id, exc)
                    continue

            result.append(
                RoundStatusResponse(
                    game_id=game_id,
                    round_id=round_id,
                    status=status,
                    status_label=status.label(),
                )
            )

        return BatchRoundStatus(game_id=game_id, rounds=result)
