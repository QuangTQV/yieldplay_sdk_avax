"""
main.py
────────
Entry point: starts the YieldPlay API server.

Usage:
    python main.py
    uvicorn main:app --reload

Environment variables (see .env.example):
    YIELDPLAY_ADDRESS  – contract address (default: Sepolia)
    RPC_URL            – JSON-RPC endpoint
    PRIVATE_KEY        – hex private key for signing (omit for read-only)
    API_HOST           – bind host (default: 0.0.0.0)
    API_PORT           – bind port (default: 8000)
"""

from __future__ import annotations

import logging

import uvicorn

from yieldplay.api.app import create_app
from yieldplay.api.deps import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
)

app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level="info",
    )
