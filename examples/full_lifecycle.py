"""
examples/full_lifecycle.py
───────────────────────────
Demonstrates the complete YieldPlay round lifecycle using Layer 1 directly.

Steps:
  1.  Create game
  2.  Create round
  3.  Deposit tokens
  4.  Deploy deposits to vault  (game owner)
  5.  [wait for lock to expire]
  6.  Withdraw from vault       (game owner)
  7.  Settlement                (game owner)
  8.  Choose winner             (game owner)
  9.  Finalize round            (game owner)
  10. Claim principal + prize   (user)
"""

from __future__ import annotations

import os
import time
import logging

from dotenv import load_dotenv
from web3 import Web3

from yieldplay import YieldPlayContract, RoundStatus, SDKConfig

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ── Constants (Sepolia) ────────────────────────────────────────────────────

YIELDPLAY_ADDRESS = "0x02AA158dc37f4E1128CeE3E69e9E59920E799F90"
TOKEN_ADDRESS = "0xdd13E55209Fd76AfE204dBda4007C227904f0a81"
RPC_URL = "https://ethereum-sepolia-rpc.publicnode.com"
PRIVATE_KEY = os.environ["PRIVATE_KEY"]  # must be set in .env


def main() -> None:
    # ── Initialise SDK ─────────────────────────────────────────────────────
    sdk = YieldPlayContract(
        SDKConfig(
            yield_play_address=YIELDPLAY_ADDRESS,
            rpc_url=RPC_URL,
            private_key=PRIVATE_KEY,
        )
    )

    owner_address = sdk.signer_address
    assert owner_address is not None, "Signer not configured"

    logger.info("Signer: %s", owner_address)
    logger.info(
        "Contract paused: %s  |  Treasury: %s",
        sdk.is_paused(),
        sdk.get_protocol_treasury(),
    )

    # ── 1. Create game ─────────────────────────────────────────────────────
    game_name = f"Demo Game {int(time.time())}"
    game_id, tx = sdk.create_game(
        game_name=game_name,
        dev_fee_bps=500,          # 5 %
        treasury=owner_address,
    )
    logger.info("Game created  id=%s  tx=%s", game_id, tx.tx_hash)

    # Verify
    game_info = sdk.get_game(game_id)
    logger.info("Game info: %s", game_info.model_dump())

    # ── 2. Create round ────────────────────────────────────────────────────
    now = int(time.time())
    round_id, tx = sdk.create_round(
        game_id=game_id,
        start_ts=now,
        end_ts=now + 120,       # 2 min deposit window (demo)
        lock_time=300,          # 5 min lock (demo)
        deposit_fee_bps=100,    # 1 %
        payment_token=TOKEN_ADDRESS,
    )
    logger.info("Round created  id=%s  tx=%s", round_id, tx.tx_hash)

    # ── 3. Deposit tokens ──────────────────────────────────────────────────
    deposit_amount = Web3.to_wei(100, "ether")  # 100 tokens (18 decimals)

    balance = sdk.get_token_balance(TOKEN_ADDRESS, owner_address)
    logger.info("Token balance: %s wei", balance)

    if balance < deposit_amount:
        logger.warning("Balance too low – skipping deposit step")
    else:
        tx = sdk.deposit(game_id, round_id, deposit_amount)
        logger.info("Deposited  amount=%s wei  tx=%s", deposit_amount, tx.tx_hash)

    # ── 4. Check status ────────────────────────────────────────────────────
    status = sdk.get_current_status(game_id, round_id)
    logger.info("Round status: %s (%s)", status, status.label())

    # ── 5. Fee preview (off-chain) ─────────────────────────────────────────
    round_info = sdk.get_round(game_id, round_id)
    hypothetical_yield = Web3.to_wei(10, "ether")  # 10 token yield estimate
    breakdown = YieldPlayContract.calculate_fee_breakdown(
        total_deposit_gross=int(round_info.total_deposit),
        deposit_fee_bps=int(round_info.deposit_fee_bps),
        dev_fee_bps=int(game_info.dev_fee_bps),
        vault_yield=hypothetical_yield,
    )
    logger.info("Fee breakdown (estimate):")
    logger.info("  Net deposits      : %s wei", breakdown.net_deposits)
    logger.info("  Performance fee   : %s wei", breakdown.performance_fee)
    logger.info("  Dev fee           : %s wei", breakdown.dev_fee)
    logger.info("  Yield prize       : %s wei", breakdown.yield_prize)
    logger.info("  Total prize pool  : %s wei", breakdown.total_prize_pool)

    # ── 6–9. Game-owner lifecycle (requires waiting for lock) ─────────────
    # In production you'd wait for status changes.  Shown here for reference:
    if status in (RoundStatus.LOCKING, RoundStatus.IN_PROGRESS):
        logger.info("Deploying to vault …")
        tx = sdk.deposit_to_vault(game_id, round_id)
        logger.info("depositToVault  tx=%s", tx.tx_hash)

    if status == RoundStatus.CHOOSING_WINNERS:
        tx = sdk.withdraw_from_vault(game_id, round_id)
        logger.info("withdrawFromVault  tx=%s", tx.tx_hash)

        tx = sdk.settlement(game_id, round_id)
        logger.info("settlement  tx=%s", tx.tx_hash)

        refreshed = sdk.get_round(game_id, round_id)
        tx = sdk.choose_winner(
            game_id=game_id,
            round_id=round_id,
            winner=owner_address,
            amount_wei=int(refreshed.total_win),
        )
        logger.info("chooseWinner  tx=%s", tx.tx_hash)

        tx = sdk.finalize_round(game_id, round_id)
        logger.info("finalizeRound  tx=%s", tx.tx_hash)

    # ── 10. Claim ──────────────────────────────────────────────────────────
    if status == RoundStatus.DISTRIBUTING_REWARDS:
        user_deposit = sdk.get_user_deposit(game_id, round_id, owner_address)
        logger.info(
            "User deposit: amount=%s  prize=%s  claimed=%s",
            user_deposit.deposit_amount,
            user_deposit.amount_to_claim,
            user_deposit.is_claimed,
        )
        if not user_deposit.is_claimed and user_deposit.exists:
            tx = sdk.claim(game_id, round_id)
            logger.info("Claimed  tx=%s", tx.tx_hash)

    logger.info("Done.")


if __name__ == "__main__":
    main()
