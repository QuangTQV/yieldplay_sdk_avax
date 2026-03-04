"""
yieldplay/api/deps.py
─────────────────────
FastAPI dependency injection for Layer 2.

Provides:
  • get_sdk()           → YieldPlayContract (Layer 1 singleton)
  • get_session()       → AsyncSession (per-request DB session)
  • get_user_service()  → UserService(contract, session)
  • get_round_service() → RoundService(contract, session)
  • handle_sdk_error()  → maps domain exceptions → HTTPException
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, AsyncIterator

from fastapi import Depends, HTTPException, status
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from web3.exceptions import BadFunctionCallOutput, ContractCustomError

from yieldplay.api.services.round_service import RoundService
from yieldplay.api.services.user_service import UserService
from yieldplay.contract import YieldPlayContract
from yieldplay.db.base import get_session
from yieldplay.exceptions import (
    ContractCallError,
    SignerNotConfiguredError,
    TransactionError,
    YieldPlayError,
)
from yieldplay.types import SDKConfig

# ── Settings ───────────────────────────────────────────────────────────────


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    yieldplay_address: str = "0x02AA158dc37f4E1128CeE3E69e9E59920E799F90"
    rpc_url: str = "https://ethereum-sepolia-rpc.publicnode.com"
    private_key: str = ""
    database_url: str = (
        "postgresql+asyncpg://yieldplay:password@localhost:5432/yieldplay"
    )
    indexer_poll_interval: float = 12.0
    indexer_start_block: int = 0
    indexer_confirmations: int = 2
    api_host: str = "0.0.0.0"
    api_port: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# ── SDK singleton ──────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _build_sdk() -> YieldPlayContract:
    settings = get_settings()
    return YieldPlayContract(
        SDKConfig(
            yield_play_address=settings.yieldplay_address,
            rpc_url=settings.rpc_url,
            private_key=settings.private_key if settings.private_key else None,
        )
    )


def get_sdk() -> YieldPlayContract:
    return _build_sdk()


# ── Per-request service factories ─────────────────────────────────────────


async def get_user_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[UserService]:  # type: ignore[misc]
    yield UserService(_build_sdk(), session)


async def get_round_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[RoundService]:  # type: ignore[misc]
    yield RoundService(_build_sdk(), session)


# ── Type aliases ───────────────────────────────────────────────────────────

SDKDep = Annotated[YieldPlayContract, Depends(get_sdk)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
RoundServiceDep = Annotated[RoundService, Depends(get_round_service)]


# ── Error translation ──────────────────────────────────────────────────────


def handle_sdk_error(exc: Exception) -> HTTPException:
    import logging

    _log = logging.getLogger(__name__)
    _log.error("SDK error [%s]: %s", type(exc).__name__, exc, exc_info=True)

    # web3 decode failure — usually means contract reverted with custom error
    if isinstance(exc, (BadFunctionCallOutput, ContractCustomError)):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Contract call failed: {exc}"
        )
    if isinstance(exc, SignerNotConfiguredError):
        return HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
    if isinstance(exc, ContractCallError):
        return HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Contract read error: {exc.details or str(exc)}",
        )
    if isinstance(exc, TransactionError):
        # TransactionRevertedError is a subclass — detail shows the revert reason
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, YieldPlayError):
        # All other business errors (InvalidDevFeeBps, AlreadyClaimed, etc.)
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    # Unexpected — log full traceback, return 500
    _log.error("Unhandled exception in route", exc_info=True)
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Internal error: {type(exc).__name__}: {exc}",
    )
