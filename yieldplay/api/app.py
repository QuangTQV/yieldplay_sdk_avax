"""
yieldplay/api/app.py – FastAPI application factory with indexer lifecycle.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from yieldplay.api.routes import games, rounds, tx, users

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="YieldPlay API",
        description=(
            "REST API for the YieldPlay no-loss prize pool protocol.\n\n"
            "**Layer 1** (`contract.py`) – raw on-chain operations via web3.\n\n"
            "**Layer 2** (this API) – game-developer HTTP interface with "
            "DB-backed composite queries (portfolio, participants, winners) "
            "and contract-backed write operations."
        ),
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(games.router, prefix="/api/v1")
    app.include_router(rounds.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(tx.router, prefix="/api/v1")

    # ── Health ─────────────────────────────────────────────────────────────

    @app.get("/health", tags=["Meta"])
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/api/v1/protocol", tags=["Meta"])
    async def protocol_info() -> JSONResponse:
        from yieldplay.api.deps import get_sdk

        sdk = get_sdk()
        try:
            return JSONResponse(
                {
                    "contract_address": sdk._config.yield_play_address,
                    "rpc_url": sdk._config.rpc_url,
                    "is_paused": sdk.is_paused(),
                    "protocol_treasury": sdk.get_protocol_treasury(),
                    "performance_fee_bps": 2000,
                    "performance_fee_pct": "20%",
                }
            )
        except Exception as exc:
            logger.warning("protocol_info error: %s", exc)
            return JSONResponse({"contract_address": sdk._config.yield_play_address})

    # ── Startup / shutdown with indexer ───────────────────────────────────

    _indexer_task: asyncio.Task[None] | None = None

    @app.on_event("startup")
    async def on_startup() -> None:
        nonlocal _indexer_task
        logger.info("YieldPlay API v2 starting up …")

        # Initialise DB tables (idempotent – safe in production if using Alembic)
        try:
            from yieldplay.db.base import create_all_tables

            await create_all_tables()
            logger.info("DB tables ready")
        except Exception as exc:
            logger.warning(
                "Could not create DB tables (DB may not be available): %s", exc
            )
            return

        # Start event indexer as background task
        try:
            from yieldplay.api.deps import get_sdk, get_settings
            from yieldplay.db.base import get_session_factory
            from yieldplay.indexer.event_indexer import EventIndexer, IndexerConfig

            settings = get_settings()
            indexer = EventIndexer(
                contract_client=get_sdk(),
                session_factory=get_session_factory(),
                config=IndexerConfig(
                    contract_address=settings.yieldplay_address,
                    poll_interval=settings.indexer_poll_interval,
                    start_block=settings.indexer_start_block,
                    confirmations=settings.indexer_confirmations,
                ),
            )
            _indexer_task = asyncio.create_task(indexer.run(), name="event_indexer")
            logger.info("Event indexer started")
        except Exception as exc:
            logger.warning("Could not start event indexer: %s", exc)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        nonlocal _indexer_task
        if _indexer_task and not _indexer_task.done():
            _indexer_task.cancel()
            try:
                await _indexer_task
            except asyncio.CancelledError:
                pass
        logger.info("YieldPlay API shut down")

    return app
