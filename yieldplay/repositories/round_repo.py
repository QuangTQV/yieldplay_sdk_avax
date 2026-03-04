"""
yieldplay/repositories/round_repo.py
──────────────────────────────────────
DB operations for Round, Game, WinnerEvent and GameMetadata.

Public interface (all async):
  RoundRepository
    • upsert_round
    • get_round
    • list_rounds_for_game
    • get_active_rounds         ← all IN_PROGRESS rounds across all games
    • upsert_winner_event
    • get_round_winners

  GameRepository
    • upsert_game
    • get_game
    • list_games_by_owner
    • upsert_game_metadata
    • get_game_metadata

  IndexerStateRepository
    • get_last_block
    • set_last_block
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from yieldplay.db.models import Game, GameMetadata, IndexerState, Round, WinnerEvent


# ── DTOs ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RoundRow:
    game_id: str
    round_id: int
    payment_token: str
    vault: str
    deposit_fee_bps: int
    start_ts: int
    end_ts: int
    lock_time: int
    total_deposit: int
    bonus_prize_pool: int
    dev_fee: int
    total_win: int
    yield_amount: int
    status: int
    is_settled: bool
    is_withdrawn: bool
    initialized: bool
    participant_count: int = 0


@dataclass(frozen=True)
class GameRow:
    game_id: str
    owner: str
    game_name: str
    dev_fee_bps: int
    treasury: str
    round_counter: int


@dataclass(frozen=True)
class WinnerRow:
    game_id: str
    round_id: int
    winner_address: str
    prize_amount: int
    tx_hash: str
    log_index: int
    block_number: int
    block_ts: int


@dataclass
class GameMetadataRow:
    game_id: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    tags: Optional[str] = None
    is_active: bool = True


# ── Round repository ──────────────────────────────────────────────────────


class RoundRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert_round(self, row: RoundRow) -> None:
        """
        Insert or update a round snapshot.
        Uses (game_id, round_id) as the natural key.
        """
        stmt = (
            pg_insert(Round)
            .values(
                game_id=row.game_id,
                round_id=row.round_id,
                payment_token=row.payment_token.lower(),
                vault=row.vault.lower(),
                deposit_fee_bps=row.deposit_fee_bps,
                start_ts=row.start_ts,
                end_ts=row.end_ts,
                lock_time=row.lock_time,
                total_deposit=row.total_deposit,
                bonus_prize_pool=row.bonus_prize_pool,
                dev_fee=row.dev_fee,
                total_win=row.total_win,
                yield_amount=row.yield_amount,
                status=row.status,
                is_settled=row.is_settled,
                is_withdrawn=row.is_withdrawn,
                initialized=row.initialized,
                participant_count=row.participant_count,
            )
            .on_conflict_do_update(
                constraint="uq_rounds_game_round",
                set_={
                    "total_deposit": row.total_deposit,
                    "bonus_prize_pool": row.bonus_prize_pool,
                    "dev_fee": row.dev_fee,
                    "total_win": row.total_win,
                    "yield_amount": row.yield_amount,
                    "status": row.status,
                    "is_settled": row.is_settled,
                    "is_withdrawn": row.is_withdrawn,
                    "participant_count": row.participant_count,
                },
            )
        )
        await self._s.execute(stmt)

    async def get_round(self, game_id: str, round_id: int) -> Optional[Round]:
        result = await self._s.execute(
            select(Round).where(
                Round.game_id == game_id,
                Round.round_id == round_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_rounds_for_game(
        self,
        game_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Round]:
        result = await self._s.execute(
            select(Round)
            .where(Round.game_id == game_id)
            .order_by(Round.round_id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_active_rounds(self) -> list[Round]:
        """Return all rounds currently in IN_PROGRESS status (status=1)."""
        from yieldplay.types import RoundStatus

        result = await self._s.execute(
            select(Round).where(Round.status == int(RoundStatus.IN_PROGRESS))
        )
        return list(result.scalars().all())

    async def upsert_winner_event(self, row: WinnerRow) -> None:
        """Insert a WinnerChosen event; idempotent on (tx_hash, log_index)."""
        stmt = (
            pg_insert(WinnerEvent)
            .values(
                game_id=row.game_id,
                round_id=row.round_id,
                winner_address=row.winner_address.lower(),
                prize_amount=row.prize_amount,
                tx_hash=row.tx_hash,
                log_index=row.log_index,
                block_number=row.block_number,
                block_ts=row.block_ts,
            )
            .on_conflict_do_nothing(constraint="uq_winners_tx_log")
        )
        await self._s.execute(stmt)

    async def get_round_winners(
        self, game_id: str, round_id: int
    ) -> list[WinnerEvent]:
        result = await self._s.execute(
            select(WinnerEvent)
            .where(
                WinnerEvent.game_id == game_id,
                WinnerEvent.round_id == round_id,
            )
            .order_by(WinnerEvent.block_number.asc())
        )
        return list(result.scalars().all())


# ── Game repository ────────────────────────────────────────────────────────


class GameRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert_game(self, row: GameRow) -> None:
        stmt = (
            pg_insert(Game)
            .values(
                game_id=row.game_id,
                owner=row.owner.lower(),
                game_name=row.game_name,
                dev_fee_bps=row.dev_fee_bps,
                treasury=row.treasury.lower(),
                round_counter=row.round_counter,
            )
            .on_conflict_do_update(
                index_elements=["game_id"],
                set_={
                    "round_counter": row.round_counter,
                    "dev_fee_bps": row.dev_fee_bps,
                    "treasury": row.treasury.lower(),
                },
            )
        )
        await self._s.execute(stmt)

    async def get_game(self, game_id: str) -> Optional[Game]:
        result = await self._s.execute(
            select(Game).where(Game.game_id == game_id)
        )
        return result.scalar_one_or_none()

    async def list_games_by_owner(self, owner: str) -> list[Game]:
        result = await self._s.execute(
            select(Game)
            .where(Game.owner == owner.lower())
            .order_by(Game.created_at.desc())
        )
        return list(result.scalars().all())

    async def upsert_game_metadata(self, row: GameMetadataRow) -> None:
        stmt = (
            pg_insert(GameMetadata)
            .values(
                game_id=row.game_id,
                display_name=row.display_name,
                description=row.description,
                logo_url=row.logo_url,
                website_url=row.website_url,
                tags=row.tags,
                is_active=row.is_active,
            )
            .on_conflict_do_update(
                index_elements=["game_id"],
                set_={
                    "display_name": row.display_name,
                    "description": row.description,
                    "logo_url": row.logo_url,
                    "website_url": row.website_url,
                    "tags": row.tags,
                    "is_active": row.is_active,
                },
            )
        )
        await self._s.execute(stmt)

    async def get_game_metadata(self, game_id: str) -> Optional[GameMetadata]:
        result = await self._s.execute(
            select(GameMetadata).where(GameMetadata.game_id == game_id)
        )
        return result.scalar_one_or_none()


# ── Indexer state repository ───────────────────────────────────────────────


class IndexerStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_last_block(self, contract_address: str) -> int:
        """Return the last indexed block for *contract_address*, or 0 if never indexed."""
        result = await self._s.execute(
            select(IndexerState.last_block).where(
                IndexerState.contract_address == contract_address.lower()
            )
        )
        row = result.scalar_one_or_none()
        return int(row) if row is not None else 0

    async def set_last_block(self, contract_address: str, block: int) -> None:
        """Upsert the last indexed block for *contract_address*."""
        stmt = (
            pg_insert(IndexerState)
            .values(
                contract_address=contract_address.lower(),
                last_block=block,
            )
            .on_conflict_do_update(
                index_elements=["contract_address"],
                set_={"last_block": block},
            )
        )
        await self._s.execute(stmt)
