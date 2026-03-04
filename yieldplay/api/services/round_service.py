"""
yieldplay/api/services/round_service.py
────────────────────────────────────────
Round-centric business logic with DB-first strategy.

DB-first strategy:
  • Round metadata, participant count, winners  → DB
  • Current status, deployed vault amounts      → contract (live)
  • Financial fields after settlement           → DB (updated by indexer)
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from yieldplay.contract import YieldPlayContract
from yieldplay.exceptions import RoundNotChoosingWinnersError
from yieldplay.repositories.deposit_repo import DepositRepository
from yieldplay.repositories.round_repo import GameRepository, RoundRepository
from yieldplay.types import (
    FeeBreakdown,
    GameInfo,
    RoundDashboard,
    RoundInfo,
    RoundStatus,
    RoundWinnerEntry,
    TransactionResult,
)

logger = logging.getLogger(__name__)

_PERF_FEE_BPS: int = 2_000


def _next_action(
    status: RoundStatus,
    is_settled: bool,
    is_withdrawn: bool,
    deployed_amount: int,
) -> str:
    if status == RoundStatus.NOT_STARTED:
        return "Wait for round to start (startTs)"
    if status == RoundStatus.IN_PROGRESS:
        return "Deposits open" + ("" if deployed_amount > 0 else " – call depositToVault to start earning yield")
    if status == RoundStatus.LOCKING:
        return "Lock period – waiting for end_ts + lock_time"
    if status == RoundStatus.CHOOSING_WINNERS:
        if not is_withdrawn:
            return "Call withdrawFromVault → settlement → chooseWinner(s)"
        if not is_settled:
            return "Call settlement → chooseWinner(s)"
        return "Call chooseWinner(s) → finalizeRound"
    if status == RoundStatus.DISTRIBUTING_REWARDS:
        return "Round finalized – users can claim"
    return "Unknown"


class RoundService:
    def __init__(self, contract: YieldPlayContract, session: AsyncSession) -> None:
        self._c = contract
        self._s = session
        self._round_repo = RoundRepository(session)
        self._game_repo = GameRepository(session)
        self._dep_repo = DepositRepository(session)

    # ── Round dashboard ───────────────────────────────────────────────────

    async def get_round_dashboard(
        self,
        game_id: str,
        round_id: int,
    ) -> RoundDashboard:
        """
        Full operational snapshot.

        Sources:
          • game metadata         → DB first, fallback contract
          • round metadata        → DB first, fallback contract
          • current status        → contract (authoritative)
          • deployed vault amt    → contract (live)
          • participant count     → DB (not available on-chain)
          • fee breakdown         → off-chain arithmetic
        """
        # Game: DB first
        db_game = await self._game_repo.get_game(game_id)
        if db_game:
            game_name = db_game.game_name
            game_owner = db_game.owner
            game_treasury = db_game.treasury
            dev_fee_bps = db_game.dev_fee_bps
        else:
            game_info: GameInfo = self._c.get_game(game_id)
            game_name = game_info.game_name
            game_owner = game_info.owner
            game_treasury = game_info.treasury
            dev_fee_bps = game_info.dev_fee_bps

        dev_fee_pct = dev_fee_bps / 100.0

        # Round: DB first
        db_round = await self._round_repo.get_round(game_id, round_id)
        if db_round:
            payment_token = db_round.payment_token
            vault_address = db_round.vault
            deposit_fee_bps = db_round.deposit_fee_bps
            start_ts = db_round.start_ts
            end_ts = db_round.end_ts
            lock_until_ts = db_round.end_ts + db_round.lock_time
            is_settled = db_round.is_settled
            is_withdrawn = db_round.is_withdrawn
            total_deposit = int(db_round.total_deposit)
            bonus_prize_pool = int(db_round.bonus_prize_pool)
            yield_amount = int(db_round.yield_amount)
            total_win = int(db_round.total_win)
            participant_count: Optional[int] = db_round.participant_count
        else:
            round_info: RoundInfo = self._c.get_round(game_id, round_id)
            payment_token = round_info.payment_token
            vault_address = round_info.vault
            deposit_fee_bps = round_info.deposit_fee_bps
            start_ts = round_info.start_ts
            end_ts = round_info.end_ts
            lock_until_ts = round_info.end_ts + round_info.lock_time
            is_settled = round_info.is_settled
            is_withdrawn = round_info.is_withdrawn
            total_deposit = round_info.total_deposit
            bonus_prize_pool = round_info.bonus_prize_pool
            yield_amount = round_info.yield_amount
            total_win = round_info.total_win
            participant_count = None

        # Always from contract (live, changes between blocks)
        status = self._c.get_current_status(game_id, round_id)
        deployed_amount = self._c.get_deployed_amounts(game_id, round_id)
        deployed_shares = self._c.get_deployed_shares(game_id, round_id)

        fee_breakdown = YieldPlayContract.calculate_fee_breakdown(
            total_deposit_gross=total_deposit,
            deposit_fee_bps=deposit_fee_bps,
            dev_fee_bps=dev_fee_bps,
            vault_yield=yield_amount if is_settled else 0,
        )

        return RoundDashboard(
            game_id=game_id,
            game_name=game_name,
            game_owner=game_owner,
            game_treasury=game_treasury,
            dev_fee_bps=dev_fee_bps,
            dev_fee_pct=dev_fee_pct,
            round_id=round_id,
            payment_token=payment_token,
            vault_address=vault_address,
            deposit_fee_bps=deposit_fee_bps,
            deposit_fee_pct=deposit_fee_bps / 100.0,
            start_ts=start_ts,
            end_ts=end_ts,
            lock_until_ts=lock_until_ts,
            status=status,
            status_label=status.label(),
            is_settled=is_settled,
            is_withdrawn=is_withdrawn,
            total_deposit_wei=str(total_deposit),
            bonus_prize_pool_wei=str(bonus_prize_pool),
            yield_amount_wei=str(yield_amount),
            total_win_wei=str(total_win),
            deployed_amount_wei=str(deployed_amount),
            deployed_shares_wei=str(deployed_shares),
            fee_breakdown=fee_breakdown,
            next_action=_next_action(status, is_settled, is_withdrawn, deployed_amount),
            participant_count=participant_count,
        )

    # ── List rounds ────────────────────────────────────────────────────────

    async def list_rounds(
        self,
        game_id: str,
        include_dashboard: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[RoundInfo] | list[RoundDashboard]:
        """
        DB-first: list rounds from DB, fall back to contract if DB is empty.
        """
        db_rounds = await self._round_repo.list_rounds_for_game(
            game_id, offset=offset, limit=limit
        )

        if not db_rounds:
            # DB not yet indexed — fall back to contract
            game_info = self._c.get_game(game_id)
            db_rounds_fallback: list[RoundInfo] = []
            for rid in range(int(game_info.round_counter)):
                try:
                    db_rounds_fallback.append(self._c.get_round(game_id, rid))
                except Exception as exc:
                    logger.warning("Skipping round %s: %s", rid, exc)
            if include_dashboard:
                return [await self.get_round_dashboard(game_id, r.round_id) for r in db_rounds_fallback]  # type: ignore[attr-defined]
            return db_rounds_fallback

        if include_dashboard:
            dashboards: list[RoundDashboard] = []
            for r in db_rounds:
                try:
                    dashboards.append(await self.get_round_dashboard(game_id, r.round_id))
                except Exception as exc:
                    logger.warning("Dashboard error for round %s: %s", r.round_id, exc)
            return dashboards

        # Map ORM → Pydantic RoundInfo
        return [
            RoundInfo(
                game_id=r.game_id,
                round_id=r.round_id,
                total_deposit=int(r.total_deposit),
                bonus_prize_pool=int(r.bonus_prize_pool),
                dev_fee=int(r.dev_fee),
                total_win=int(r.total_win),
                yield_amount=int(r.yield_amount),
                payment_token=r.payment_token,
                vault=r.vault,
                deposit_fee_bps=r.deposit_fee_bps,
                start_ts=r.start_ts,
                end_ts=r.end_ts,
                lock_time=r.lock_time,
                initialized=r.initialized,
                is_settled=r.is_settled,
                status=RoundStatus(r.status),
                is_withdrawn=r.is_withdrawn,
            )
            for r in db_rounds
        ]

    # ── Round winners (DB) ─────────────────────────────────────────────────

    async def get_round_winners(
        self, game_id: str, round_id: int
    ) -> list[RoundWinnerEntry]:
        """
        Return all winners for a round from the DB.
        Merges with deposit data to include each winner's original deposit.
        """
        winner_events = await self._round_repo.get_round_winners(game_id, round_id)
        result: list[RoundWinnerEntry] = []

        for w in winner_events:
            deposit = await self._dep_repo.get_user_deposit_in_round(
                game_id, round_id, w.winner_address
            )
            deposit_wei = int(deposit.net_amount) if deposit else 0

            # is_claimed: check contract for accuracy
            try:
                chain_deposit = self._c.get_user_deposit(
                    game_id, round_id, w.winner_address
                )
                is_claimed = chain_deposit.is_claimed
            except Exception:
                is_claimed = False

            result.append(
                RoundWinnerEntry(
                    winner_address=w.winner_address,
                    prize_wei=str(w.prize_amount),
                    deposit_wei=str(deposit_wei),
                    is_claimed=is_claimed,
                )
            )

        return result

    # ── Round participants (DB) ────────────────────────────────────────────

    async def get_round_participants(
        self,
        game_id: str,
        round_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, str | int | bool]]:
        """
        List all depositors in a round with their amounts.
        This is the key query enabled by DB indexing — impossible on-chain.
        """
        deposits = await self._dep_repo.get_round_participants(
            game_id, round_id, offset=offset, limit=limit
        )
        return [
            {
                "user_address": d.user_address,
                "gross_amount_wei": str(d.gross_amount),
                "net_amount_wei": str(d.net_amount),
                "deposit_fee_wei": str(d.deposit_fee),
                "block_number": d.block_number,
                "block_ts": d.block_ts,
                "tx_hash": d.tx_hash,
            }
            for d in deposits
        ]

    # ── Fee preview ────────────────────────────────────────────────────────

    async def get_fee_preview(
        self,
        game_id: str,
        round_id: int,
        hypothetical_yield_wei: Optional[int] = None,
    ) -> FeeBreakdown:
        """
        Fee breakdown using real vault yield when available.

        Priority for yield source:
          1. hypothetical_yield_wei (caller override — for simulations)
          2. On-chain yieldAmount (set after settlement)
          3. vault.previewRedeem(shares) - deployedAmount (live accrual mid-round)
          4. 0 (vault not yet deployed)
        """
        db_round = await self._round_repo.get_round(game_id, round_id)
        db_game = await self._game_repo.get_game(game_id)

        if db_round and db_game:
            deposit_fee_bps = db_round.deposit_fee_bps
            dev_fee_bps = db_game.dev_fee_bps
            total_deposit = int(db_round.total_deposit)
            settled_yield = int(db_round.yield_amount)
        else:
            round_info = self._c.get_round(game_id, round_id)
            game_info = self._c.get_game(game_id)
            deposit_fee_bps = round_info.deposit_fee_bps
            dev_fee_bps = game_info.dev_fee_bps
            total_deposit = round_info.total_deposit
            settled_yield = round_info.yield_amount

        if hypothetical_yield_wei is not None:
            yield_to_use = hypothetical_yield_wei
        elif settled_yield > 0:
            # Post-settlement: use the exact on-chain value
            yield_to_use = settled_yield
        else:
            # Mid-round: query vault directly for live accrued yield
            try:
                yield_to_use = self._c.get_projected_yield(game_id, round_id)
            except Exception:
                yield_to_use = 0  # vault not deployed yet

        return YieldPlayContract.calculate_fee_breakdown(
            total_deposit_gross=total_deposit,
            deposit_fee_bps=deposit_fee_bps,
            dev_fee_bps=dev_fee_bps,
            vault_yield=yield_to_use,
        )

    # ── Composite write sequences ──────────────────────────────────────────

    def execute_settle_sequence(
        self,
        game_id: str,
        round_id: int,
    ) -> dict[str, TransactionResult]:
        round_info = self._c.get_round(game_id, round_id)
        results: dict[str, TransactionResult] = {}
        if not round_info.is_withdrawn:
            results["withdraw_from_vault"] = self._c.withdraw_from_vault(game_id, round_id)
        if not round_info.is_settled:
            results["settlement"] = self._c.settlement(game_id, round_id)
        return results

    def execute_distribute_and_finalize(
        self,
        game_id: str,
        round_id: int,
        winners: list[tuple[str, int]],
    ) -> dict[str, TransactionResult | list[TransactionResult]]:
        status = self._c.get_current_status(game_id, round_id)
        if status != RoundStatus.CHOOSING_WINNERS:
            raise RoundNotChoosingWinnersError(
                f"Round must be in ChoosingWinners, got: {status.label()}"
            )
        round_info = self._c.get_round(game_id, round_id)
        total_allocated = sum(amt for _, amt in winners)
        if total_allocated > round_info.total_win:
            raise ValueError(
                f"Prize allocation {total_allocated} > available {round_info.total_win}"
            )
        winner_txs: list[TransactionResult] = [
            self._c.choose_winner(game_id, round_id, addr, amt)
            for addr, amt in winners
        ]
        return {
            "choose_winners": winner_txs,
            "finalize_round": self._c.finalize_round(game_id, round_id),
        }
