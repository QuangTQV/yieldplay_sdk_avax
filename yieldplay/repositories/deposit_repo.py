"""
yieldplay/repositories/deposit_repo.py
────────────────────────────────────────
All DB operations related to Deposit and Claim records.

Public interface (all async):
  • upsert_deposit
  • upsert_claim
  • get_user_deposit_in_round
  • get_round_participants
  • get_user_rounds            ← reverse index (the main reason for DB)
  • get_round_deposit_stats
  • get_user_claim_history
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from yieldplay.db.models import Claim, Deposit


# ── Data transfer objects (lightweight, no Pydantic overhead) ─────────────


@dataclass(frozen=True)
class DepositRow:
    game_id: str
    round_id: int
    user_address: str
    gross_amount: int
    net_amount: int
    deposit_fee: int
    tx_hash: str
    log_index: int
    block_number: int
    block_ts: int


@dataclass(frozen=True)
class ClaimRow:
    game_id: str
    round_id: int
    user_address: str
    principal: int
    prize: int
    total_claimed: int
    tx_hash: str
    log_index: int
    block_number: int
    block_ts: int


@dataclass(frozen=True)
class RoundDepositStats:
    """Aggregate stats for one round derived from indexed deposits."""

    game_id: str
    round_id: int
    participant_count: int
    total_gross_wei: int
    total_net_wei: int
    total_fee_wei: int


@dataclass(frozen=True)
class UserRoundEntry:
    """One row in a user's participation history."""

    game_id: str
    round_id: int
    net_amount: int
    deposit_block_ts: int
    is_claimed: bool
    prize: int


# ── Repository ─────────────────────────────────────────────────────────────


class DepositRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── Writes ────────────────────────────────────────────────────────────

    async def upsert_deposit(self, row: DepositRow) -> None:
        """
        Insert a deposit; silently ignore if (tx_hash, log_index) already exists.
        Safe to call multiple times for the same event (idempotent).
        """
        stmt = (
            pg_insert(Deposit)
            .values(
                game_id=row.game_id,
                round_id=row.round_id,
                user_address=row.user_address.lower(),
                gross_amount=row.gross_amount,
                net_amount=row.net_amount,
                deposit_fee=row.deposit_fee,
                tx_hash=row.tx_hash,
                log_index=row.log_index,
                block_number=row.block_number,
                block_ts=row.block_ts,
            )
            .on_conflict_do_nothing(constraint="uq_deposits_tx_log")
        )
        await self._s.execute(stmt)

    async def upsert_claim(self, row: ClaimRow) -> None:
        """Insert a claim; idempotent on (tx_hash, log_index)."""
        stmt = (
            pg_insert(Claim)
            .values(
                game_id=row.game_id,
                round_id=row.round_id,
                user_address=row.user_address.lower(),
                principal=row.principal,
                prize=row.prize,
                total_claimed=row.total_claimed,
                tx_hash=row.tx_hash,
                log_index=row.log_index,
                block_number=row.block_number,
                block_ts=row.block_ts,
            )
            .on_conflict_do_nothing(constraint="uq_claims_tx_log")
        )
        await self._s.execute(stmt)

    # ── Reads ─────────────────────────────────────────────────────────────

    async def get_user_deposit_in_round(
        self,
        game_id: str,
        round_id: int,
        user_address: str,
    ) -> Optional[Deposit]:
        """Return the deposit row for a specific user in a specific round."""
        result = await self._s.execute(
            select(Deposit).where(
                Deposit.game_id == game_id,
                Deposit.round_id == round_id,
                Deposit.user_address == user_address.lower(),
            )
        )
        return result.scalar_one_or_none()

    async def get_round_participants(
        self,
        game_id: str,
        round_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Deposit]:
        """
        Return all depositors for a round, paginated.

        This is the *reverse index* query: impossible on-chain
        but trivial with DB.
        """
        result = await self._s.execute(
            select(Deposit)
            .where(Deposit.game_id == game_id, Deposit.round_id == round_id)
            .order_by(Deposit.block_number.asc(), Deposit.log_index.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_user_rounds(
        self,
        user_address: str,
        game_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[UserRoundEntry]:
        """
        All rounds a user has participated in, with claim status merged.

        This is the core reverse-index query driving the portfolio endpoint.
        Joins deposits ← claims on (game_id, round_id, user_address).
        """
        addr = user_address.lower()

        # Left join: not all deposits have a corresponding claim yet
        stmt = (
            select(
                Deposit.game_id,
                Deposit.round_id,
                Deposit.net_amount,
                Deposit.block_ts.label("deposit_block_ts"),
                (Claim.id.isnot(None)).label("is_claimed"),
                func.coalesce(Claim.prize, 0).label("prize"),
            )
            .outerjoin(
                Claim,
                (Claim.game_id == Deposit.game_id)
                & (Claim.round_id == Deposit.round_id)
                & (Claim.user_address == Deposit.user_address),
            )
            .where(Deposit.user_address == addr)
        )

        if game_id is not None:
            stmt = stmt.where(Deposit.game_id == game_id)

        stmt = stmt.order_by(Deposit.block_number.desc()).offset(offset).limit(limit)

        rows = await self._s.execute(stmt)
        return [
            UserRoundEntry(
                game_id=str(r.game_id),
                round_id=int(r.round_id),
                net_amount=int(r.net_amount),
                deposit_block_ts=int(r.deposit_block_ts),
                is_claimed=bool(r.is_claimed),
                prize=int(r.prize),
            )
            for r in rows
        ]

    async def get_round_deposit_stats(
        self, game_id: str, round_id: int
    ) -> Optional[RoundDepositStats]:
        """Aggregate deposit statistics for a round from the DB."""
        result = await self._s.execute(
            select(
                func.count(Deposit.id).label("participant_count"),
                func.coalesce(func.sum(Deposit.gross_amount), 0).label("total_gross"),
                func.coalesce(func.sum(Deposit.net_amount), 0).label("total_net"),
                func.coalesce(func.sum(Deposit.deposit_fee), 0).label("total_fee"),
            ).where(
                Deposit.game_id == game_id,
                Deposit.round_id == round_id,
            )
        )
        row = result.one_or_none()
        if row is None or row.participant_count == 0:
            return None
        return RoundDepositStats(
            game_id=game_id,
            round_id=round_id,
            participant_count=int(row.participant_count),
            total_gross_wei=int(row.total_gross),
            total_net_wei=int(row.total_net),
            total_fee_wei=int(row.total_fee),
        )

    async def get_user_claim_history(
        self,
        user_address: str,
        game_id: Optional[str] = None,
    ) -> list[Claim]:
        """Return all claim records for a user, optionally filtered by game."""
        stmt = select(Claim).where(Claim.user_address == user_address.lower())
        if game_id is not None:
            stmt = stmt.where(Claim.game_id == game_id)
        stmt = stmt.order_by(Claim.block_number.desc())
        result = await self._s.execute(stmt)
        return list(result.scalars().all())
