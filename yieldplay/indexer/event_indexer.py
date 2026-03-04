"""
yieldplay/indexer/event_indexer.py
────────────────────────────────────
Background event indexer.

Polls the YieldPlay contract for new events in a loop, decodes them and
persists them to the DB via the repository layer.

Events indexed:
  • GameCreated    (game_id, owner, gameName, devFeeBps, treasury)
  • RoundCreated   (game_id, round_id, paymentToken, vault, ...)
  • Deposit        (game_id, roundId, user, grossAmount, netAmount, fee)
  • Claim          (game_id, roundId, user, principal, prize)
  • WinnerChosen   (game_id, roundId, winner, amount)
  • RoundFinalized (game_id, roundId)    → triggers round status refresh
  • Settlement     (game_id, roundId)    → triggers round financial refresh

Design:
  • Stateless: resumes from last_block stored in DB on every startup
  • Idempotent: all upserts use ON CONFLICT DO NOTHING / DO UPDATE
  • Configurable poll interval and confirmation depth

Usage:
    indexer = EventIndexer(contract_client, session_factory, config)
    await indexer.run()   # runs forever; cancel to stop
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from web3 import Web3
from web3.types import EventData

from yieldplay.contract import YieldPlayContract
from yieldplay.repositories.deposit_repo import ClaimRow, DepositRepository, DepositRow
from yieldplay.repositories.round_repo import (
    GameRepository,
    GameRow,
    IndexerStateRepository,
    RoundRepository,
    RoundRow,
    WinnerRow,
)

logger = logging.getLogger(__name__)

# ── Extended ABI – events only ─────────────────────────────────────────────

_EVENT_ABI: list[dict[str, Any]] = [
    {
        "name": "GameCreated",
        "type": "event",
        "inputs": [
            {"name": "gameId", "type": "bytes32", "indexed": True},
            {"name": "owner", "type": "address", "indexed": True},
            {"name": "gameName", "type": "string", "indexed": False},
            {"name": "devFeeBps", "type": "uint256", "indexed": False},
            {"name": "treasury", "type": "address", "indexed": False},
        ],
    },
    {
        "name": "RoundCreated",
        "type": "event",
        "inputs": [
            {"name": "gameId", "type": "bytes32", "indexed": True},
            {"name": "roundId", "type": "uint256", "indexed": True},
            {"name": "paymentToken", "type": "address", "indexed": False},
            {"name": "vault", "type": "address", "indexed": False},
            {"name": "startTs", "type": "uint256", "indexed": False},
            {"name": "endTs", "type": "uint256", "indexed": False},
            {"name": "lockTime", "type": "uint256", "indexed": False},
            {"name": "depositFeeBps", "type": "uint256", "indexed": False},
        ],
    },
    {
        "name": "Deposited",
        "type": "event",
        "inputs": [
            {"name": "gameId", "type": "bytes32", "indexed": True},
            {"name": "roundId", "type": "uint256", "indexed": True},
            {"name": "user", "type": "address", "indexed": True},
            {"name": "grossAmount", "type": "uint256", "indexed": False},
            {"name": "netAmount", "type": "uint256", "indexed": False},
            {"name": "depositFee", "type": "uint256", "indexed": False},
        ],
    },
    {
        "name": "Claimed",
        "type": "event",
        "inputs": [
            {"name": "gameId", "type": "bytes32", "indexed": True},
            {"name": "roundId", "type": "uint256", "indexed": True},
            {"name": "user", "type": "address", "indexed": True},
            {"name": "principal", "type": "uint256", "indexed": False},
            {"name": "prize", "type": "uint256", "indexed": False},
        ],
    },
    {
        "name": "WinnerChosen",
        "type": "event",
        "inputs": [
            {"name": "gameId", "type": "bytes32", "indexed": True},
            {"name": "roundId", "type": "uint256", "indexed": True},
            {"name": "winner", "type": "address", "indexed": True},
            {"name": "amount", "type": "uint256", "indexed": False},
        ],
    },
    {
        "name": "RoundFinalized",
        "type": "event",
        "inputs": [
            {"name": "gameId", "type": "bytes32", "indexed": True},
            {"name": "roundId", "type": "uint256", "indexed": True},
        ],
    },
    {
        "name": "Settled",
        "type": "event",
        "inputs": [
            {"name": "gameId", "type": "bytes32", "indexed": True},
            {"name": "roundId", "type": "uint256", "indexed": True},
            {"name": "yieldAmount", "type": "uint256", "indexed": False},
            {"name": "performanceFee", "type": "uint256", "indexed": False},
            {"name": "devFee", "type": "uint256", "indexed": False},
        ],
    },
]


class IndexerConfig:
    def __init__(
        self,
        contract_address: str,
        poll_interval: float = 12.0,
        start_block: int = 0,
        confirmations: int = 2,
        batch_size: int = 2_000,
    ) -> None:
        self.contract_address = contract_address
        self.poll_interval = poll_interval
        self.start_block = start_block
        self.confirmations = confirmations
        self.batch_size = batch_size


class EventIndexer:
    """
    Polls the YieldPlay contract for events and persists them to the DB.

    Lifecycle:
      1. On startup, read last_block from DB (or use config.start_block).
      2. Loop: fetch events from last_block → current_block - confirmations.
      3. Handle each event and upsert to DB.
      4. Update last_block in DB.
      5. Sleep poll_interval seconds, repeat.
    """

    def __init__(
        self,
        contract_client: YieldPlayContract,
        session_factory: async_sessionmaker[AsyncSession],
        config: IndexerConfig,
    ) -> None:
        self._client = contract_client
        self._factory = session_factory
        self._config = config

        # Build a web3 contract with the event ABI for log decoding
        # AsyncHTTPProvider → dùng AsyncContract
        self._event_contract = contract_client.w3.eth.contract(
            address=Web3.to_checksum_address(config.contract_address),
            abi=_EVENT_ABI,
        )

        self._running = False

    # ── Public ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop – runs until cancelled."""
        self._running = True
        logger.info(
            "EventIndexer starting – contract=%s  poll=%.0fs  confirmations=%d",
            self._config.contract_address,
            self._config.poll_interval,
            self._config.confirmations,
        )

        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Indexer tick error: %s", exc, exc_info=True)

            await asyncio.sleep(self._config.poll_interval)

        logger.info("EventIndexer stopped")

    def stop(self) -> None:
        self._running = False

    # ── Internal ───────────────────────────────────────────────────────────

    async def _tick(self) -> None:
        async with self._factory() as session:
            state_repo = IndexerStateRepository(session)
            last_block = await state_repo.get_last_block(self._config.contract_address)
            from_block = max(last_block + 1, self._config.start_block)

            current_block: int = self._client.w3.eth.block_number
            to_block = current_block - self._config.confirmations

            if from_block > to_block:
                logger.debug("No new blocks (from=%d, to=%d)", from_block, to_block)
                return

            # Fetch in batches to avoid RPC limits
            cursor = from_block
            while cursor <= to_block:
                batch_end = min(cursor + self._config.batch_size - 1, to_block)
                logger.debug("Indexing blocks %d → %d", cursor, batch_end)
                await self._process_range(session, cursor, batch_end)
                cursor = batch_end + 1

            await state_repo.set_last_block(self._config.contract_address, to_block)
            await session.commit()

    async def _process_range(
        self,
        session: AsyncSession,
        from_block: int,
        to_block: int,
    ) -> None:
        """Fetch all known events in [from_block, to_block] and persist them."""
        event_names = [
            "GameCreated",
            "RoundCreated",
            "Deposited",
            "Claimed",
            "WinnerChosen",
            "RoundFinalized",
            "Settled",
        ]

        for event_name in event_names:
            try:
                event_obj = getattr(self._event_contract.events, event_name)
                # web3.py HTTPProvider is synchronous — run in thread pool
                loop = asyncio.get_event_loop()
                logs: list[EventData] = await loop.run_in_executor(
                    None,
                    lambda ev=event_obj: ev.get_logs(  # type: ignore[attr-defined]
                        from_block=from_block, to_block=to_block
                    ),
                )
                if logs:
                    logger.info(
                        "  %s: %d events in blocks %d–%d",
                        event_name,
                        len(logs),
                        from_block,
                        to_block,
                    )
                for log in logs:
                    await self._handle_event(session, event_name, log)
            except Exception as exc:
                logger.warning("Failed to fetch %s events: %s", event_name, exc)

    async def _handle_event(
        self,
        session: AsyncSession,
        event_name: str,
        log: EventData,
    ) -> None:
        args: dict[str, Any] = dict(log["args"])
        tx_hash: str = log["transactionHash"].hex()
        log_index: int = log["logIndex"]
        block_number: int = log["blockNumber"]

        # get_block is a sync call on HTTPProvider — run in thread pool
        # to avoid blocking the async event loop
        loop = asyncio.get_event_loop()
        block = await loop.run_in_executor(
            None, lambda: self._client.w3.eth.get_block(block_number)
        )
        block_ts: int = int(block["timestamp"])

        # bytes32 → hex string helper
        def b32hex(v: bytes) -> str:
            return "0x" + v.hex()

        deposit_repo = DepositRepository(session)
        round_repo = RoundRepository(session)
        game_repo = GameRepository(session)

        if event_name == "GameCreated":
            await game_repo.upsert_game(
                GameRow(
                    game_id=b32hex(args["gameId"]),
                    owner=args["owner"],
                    game_name=args["gameName"],
                    dev_fee_bps=int(args["devFeeBps"]),
                    treasury=args["treasury"],
                    round_counter=0,
                )
            )

        elif event_name == "RoundCreated":
            game_id = b32hex(args["gameId"])
            round_id = int(args["roundId"])
            # Pull full round info from chain to get all fields
            await self._sync_round(session, game_id, round_id)

        elif event_name == "Deposited":
            game_id = b32hex(args["gameId"])
            round_id = int(args["roundId"])
            gross = int(args["grossAmount"])
            net = int(args["netAmount"])
            fee = int(args["depositFee"])

            await deposit_repo.upsert_deposit(
                DepositRow(
                    game_id=game_id,
                    round_id=round_id,
                    user_address=args["user"],
                    gross_amount=gross,
                    net_amount=net,
                    deposit_fee=fee,
                    tx_hash=tx_hash,
                    log_index=log_index,
                    block_number=block_number,
                    block_ts=block_ts,
                )
            )
            # Refresh participant count in rounds table
            stats = await deposit_repo.get_round_deposit_stats(game_id, round_id)
            if stats:
                await self._sync_round(
                    session,
                    game_id,
                    round_id,
                    participant_count=stats.participant_count,
                )

        elif event_name == "Claimed":
            game_id = b32hex(args["gameId"])
            round_id = int(args["roundId"])
            principal = int(args["principal"])
            prize = int(args["prize"])

            await deposit_repo.upsert_claim(
                ClaimRow(
                    game_id=game_id,
                    round_id=round_id,
                    user_address=args["user"],
                    principal=principal,
                    prize=prize,
                    total_claimed=principal + prize,
                    tx_hash=tx_hash,
                    log_index=log_index,
                    block_number=block_number,
                    block_ts=block_ts,
                )
            )

        elif event_name == "WinnerChosen":
            await round_repo.upsert_winner_event(
                WinnerRow(
                    game_id=b32hex(args["gameId"]),
                    round_id=int(args["roundId"]),
                    winner_address=args["winner"],
                    prize_amount=int(args["amount"]),
                    tx_hash=tx_hash,
                    log_index=log_index,
                    block_number=block_number,
                    block_ts=block_ts,
                )
            )

        elif event_name in ("RoundFinalized", "Settled"):
            # Refresh the round snapshot from chain
            await self._sync_round(
                session,
                b32hex(args["gameId"]),
                int(args["roundId"]),
            )

    async def _sync_round(
        self,
        session: AsyncSession,
        game_id: str,
        round_id: int,
        participant_count: int = 0,
    ) -> None:
        """Pull latest round state from chain and upsert into DB."""
        try:
            info = self._client.get_round(game_id, round_id)
            repo = RoundRepository(session)
            await repo.upsert_round(
                RoundRow(
                    game_id=game_id,
                    round_id=round_id,
                    payment_token=info.payment_token,
                    vault=info.vault,
                    deposit_fee_bps=info.deposit_fee_bps,
                    start_ts=info.start_ts,
                    end_ts=info.end_ts,
                    lock_time=info.lock_time,
                    total_deposit=info.total_deposit,
                    bonus_prize_pool=info.bonus_prize_pool,
                    dev_fee=info.dev_fee,
                    total_win=info.total_win,
                    yield_amount=info.yield_amount,
                    status=int(info.status),
                    is_settled=info.is_settled,
                    is_withdrawn=info.is_withdrawn,
                    initialized=info.initialized,
                    participant_count=participant_count,
                )
            )
        except Exception as exc:
            logger.warning(
                "Could not sync round game=%s round=%s: %s", game_id, round_id, exc
            )
