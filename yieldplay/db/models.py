"""
yieldplay/db/models.py
───────────────────────
SQLAlchemy ORM models.

Tables:
  indexer_state   – tracks last indexed block per contract
  games           – on-chain game metadata snapshot
  rounds          – on-chain round metadata snapshot
  deposits        – Deposit events indexed from chain
  claims          – Claim events indexed from chain
  winner_events   – WinnerChosen events indexed from chain
  game_metadata   – off-chain game metadata managed by game devs

Design principles:
  • amount / wei values stored as NUMERIC(78,0) — exact, no float rounding
  • all addresses stored lowercase for consistent comparisons
  • indexed = True on every column used in WHERE / JOIN clauses
  • tx_hash + log_index as unique key guards against duplicate indexing
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from yieldplay.db.base import Base

# Reusable column type for wei amounts (up to 2^256 − 1)
Wei = Numeric(78, 0)

# ── Indexer state ──────────────────────────────────────────────────────────


class IndexerState(Base):
    """
    Tracks the last processed block number for each watched contract.
    Used by the event indexer to know where to resume after a restart.
    """

    __tablename__ = "indexer_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_address: Mapped[str] = mapped_column(
        String(42), nullable=False, unique=True, index=True
    )
    last_block: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ── Game snapshot ──────────────────────────────────────────────────────────


class Game(Base):
    """
    Snapshot of on-chain GameInfo, upserted whenever a CreateGame event
    is indexed or the API explicitly syncs a game.
    """

    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(String(66), primary_key=True)  # bytes32 hex
    owner: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    game_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dev_fee_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    treasury: Mapped[str] = mapped_column(String(42), nullable=False)
    round_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ── Round snapshot ─────────────────────────────────────────────────────────


class Round(Base):
    """
    Snapshot of on-chain RoundInfo, upserted whenever a RoundCreated event
    is indexed or a status change is detected.
    """

    __tablename__ = "rounds"
    __table_args__ = (
        UniqueConstraint("game_id", "round_id", name="uq_rounds_game_round"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(66), nullable=False, index=True)
    round_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    payment_token: Mapped[str] = mapped_column(String(42), nullable=False)
    vault: Mapped[str] = mapped_column(String(42), nullable=False)
    deposit_fee_bps: Mapped[int] = mapped_column(Integer, nullable=False)

    start_ts: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ts: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lock_time: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Financial fields – updated as events arrive
    total_deposit: Mapped[int] = mapped_column(Wei, nullable=False, default=0)
    bonus_prize_pool: Mapped[int] = mapped_column(Wei, nullable=False, default=0)
    dev_fee: Mapped[int] = mapped_column(Wei, nullable=False, default=0)
    total_win: Mapped[int] = mapped_column(Wei, nullable=False, default=0)
    yield_amount: Mapped[int] = mapped_column(Wei, nullable=False, default=0)

    # State flags
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_settled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_withdrawn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    initialized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Participant count (derived from Deposit events)
    participant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("game_id", "round_id", name="uq_rounds_game_round"),
        Index("ix_rounds_status", "status"),
        Index("ix_rounds_payment_token", "payment_token"),
    )


# ── Deposit events ─────────────────────────────────────────────────────────


class Deposit(Base):
    """
    Indexed from the on-chain Deposit event.

    One row per deposit transaction.  A user may deposit multiple times
    across different rounds (but not twice in the same round — enforced by contract).
    """

    __tablename__ = "deposits"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_deposits_tx_log"),
        Index("ix_deposits_user_game", "user_address", "game_id"),
        Index("ix_deposits_game_round", "game_id", "round_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(66), nullable=False)
    round_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)

    gross_amount: Mapped[int] = mapped_column(
        Wei, nullable=False, comment="Amount before deposit fee"
    )
    net_amount: Mapped[int] = mapped_column(
        Wei, nullable=False, comment="Amount credited to user (after fee)"
    )
    deposit_fee: Mapped[int] = mapped_column(
        Wei, nullable=False, comment="Fee added to bonus prize pool"
    )

    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    block_ts: Mapped[int] = mapped_column(BigInteger, nullable=False)


# ── Claim events ───────────────────────────────────────────────────────────


class Claim(Base):
    """
    Indexed from the on-chain Claim event.

    One row per claim transaction.
    """

    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_claims_tx_log"),
        Index("ix_claims_user_game", "user_address", "game_id"),
        Index("ix_claims_game_round", "game_id", "round_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(66), nullable=False)
    round_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)

    principal: Mapped[int] = mapped_column(Wei, nullable=False)
    prize: Mapped[int] = mapped_column(Wei, nullable=False)
    total_claimed: Mapped[int] = mapped_column(Wei, nullable=False)

    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    block_ts: Mapped[int] = mapped_column(BigInteger, nullable=False)


# ── Winner events ──────────────────────────────────────────────────────────


class WinnerEvent(Base):
    """
    Indexed from the on-chain WinnerChosen event.

    A round may have multiple winners (chooseWinner can be called N times).
    """

    __tablename__ = "winner_events"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_winners_tx_log"),
        Index("ix_winners_game_round", "game_id", "round_id"),
        Index("ix_winners_address", "winner_address"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(66), nullable=False)
    round_id: Mapped[int] = mapped_column(Integer, nullable=False)
    winner_address: Mapped[str] = mapped_column(String(42), nullable=False)
    prize_amount: Mapped[int] = mapped_column(Wei, nullable=False)

    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    block_ts: Mapped[int] = mapped_column(BigInteger, nullable=False)


# ── Off-chain game metadata ────────────────────────────────────────────────


class GameMetadata(Base):
    """
    Off-chain metadata for a game, managed by game developers via the API.

    Not sourced from the chain – purely application-layer data.
    """

    __tablename__ = "game_metadata"

    game_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tags: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="Comma-separated tags"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
