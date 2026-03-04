"""
yieldplay/contract.py
──────────────────────
Layer 1 – Direct contract interaction.

This layer owns:
  • Web3 connection management
  • ABI encoding / decoding
  • Transaction signing & broadcasting
  • Mapping raw tuple returns → typed Pydantic models
  • ERC-20 utility helpers (balance, allowance, approve)

It does NOT own:
  • HTTP routing / API logic  (→ Layer 2)
  • Game-dev business rules   (→ Layer 2)
"""

from __future__ import annotations

import logging
from typing import Optional, cast

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.types import TxParams, TxReceipt

from yieldplay.abi import ERC20_ABI, YIELD_PLAY_ABI
from yieldplay.exceptions import (
    ContractCallError,
    SignerNotConfiguredError,
    TransactionError,
    TransactionRevertedError,
    map_revert_reason,
)
from yieldplay.types import (
    FeeBreakdown,
    GameInfo,
    RoundInfo,
    RoundStatus,
    SDKConfig,
    TransactionResult,
    UserDepositInfo,
)

logger = logging.getLogger(__name__)

# 20 % performance fee is hard-coded in the protocol
_PERFORMANCE_FEE_BPS: int = 2_000
_MAX_UINT256: int = 2**256 - 1


class YieldPlayContract:
    """
    Layer 1 – thin wrapper around the YieldPlay smart contract.

    All amounts are in **wei** (int).  Callers in Layer 2 are responsible
    for formatting values for human consumption.
    """

    def __init__(self, config: SDKConfig) -> None:
        self._config = config
        self._w3: Web3 = Web3(Web3.HTTPProvider(config.rpc_url))

        self._account: Optional[LocalAccount] = (
            Account.from_key(config.private_key) if config.private_key else None
        )

        self._contract: Contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(config.yield_play_address),
            abi=YIELD_PLAY_ABI,
        )

        logger.info(
            "YieldPlayContract initialised – address=%s  signer=%s",
            config.yield_play_address,
            self._account.address if self._account else "read-only",
        )

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def signer_address(self) -> Optional[str]:
        return self._account.address if self._account else None

    @property
    def w3(self) -> Web3:
        return self._w3

    # ── Internal helpers ──────────────────────────────────────────────────

    def _require_signer(self) -> LocalAccount:
        if self._account is None:
            raise SignerNotConfiguredError()
        return self._account

    @staticmethod
    def _to_bytes32(hex_str: str) -> bytes:
        """Convert a 0x-prefixed hex string to bytes32."""
        value = bytes.fromhex(hex_str.removeprefix("0x"))
        if len(value) > 32:  # pragma: no cover
            raise ValueError(f"Value too large for bytes32: {hex_str}")
        return value.rjust(32, b"\x00")

    @staticmethod
    def _bytes32_to_hex(raw: bytes) -> str:
        return "0x" + raw.hex()

    def _send_transaction(
        self,
        tx_params: TxParams,
        account: LocalAccount,
    ) -> TransactionResult:
        """Sign, broadcast and wait for a transaction receipt."""
        try:
            tx_params["nonce"] = self._w3.eth.get_transaction_count(
                cast(ChecksumAddress, account.address)
            )
            tx_params["chainId"] = self._w3.eth.chain_id

            # Estimate gas if not provided
            if "gas" not in tx_params:
                tx_params["gas"] = self._w3.eth.estimate_gas(tx_params)

            if "gasPrice" not in tx_params and "maxFeePerGas" not in tx_params:
                tx_params["gasPrice"] = self._w3.eth.gas_price

            signed = account.sign_transaction(tx_params)
            raw_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.debug("Transaction sent: %s", raw_hash.hex())

            receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(raw_hash)
            tx_hash_hex = receipt["transactionHash"].hex()

            if receipt["status"] == 0:
                raise TransactionRevertedError(
                    "Transaction reverted",
                    tx_hash=tx_hash_hex,
                )

            logger.info(
                "Transaction confirmed: hash=%s  block=%s  gas=%s",
                tx_hash_hex,
                receipt["blockNumber"],
                receipt["gasUsed"],
            )

            return TransactionResult(
                tx_hash=tx_hash_hex,
                block_number=receipt["blockNumber"],
                gas_used=receipt["gasUsed"],
                status=receipt["status"],
            )

        except (TransactionRevertedError, TransactionError):
            raise
        except ContractLogicError as exc:
            raise map_revert_reason(str(exc)) from exc
        except Exception as exc:
            raise TransactionError(
                "Failed to send transaction", details=str(exc)
            ) from exc

    # ── Read: game / round info ───────────────────────────────────────────

    def get_game(self, game_id: str) -> GameInfo:
        """Return GameInfo for *game_id*."""
        try:
            raw = self._contract.functions.getGame(self._to_bytes32(game_id)).call()
        except ContractLogicError as exc:
            raise ContractCallError("getGame failed", str(exc)) from exc

        # raw is a tuple: (owner, gameName, devFeeBps, treasury, roundCounter, initialized)
        tup = cast(tuple[str, str, int, str, int, bool], raw)
        return GameInfo(
            owner=tup[0],
            game_name=tup[1],
            dev_fee_bps=int(tup[2]),
            treasury=tup[3],
            round_counter=int(tup[4]),
            initialized=bool(tup[5]),
        )

    def get_round(self, game_id: str, round_id: int) -> RoundInfo:
        """Return RoundInfo for *game_id* / *round_id*."""
        try:
            raw = self._contract.functions.getRound(
                self._to_bytes32(game_id), round_id
            ).call()
        except ContractLogicError as exc:
            raise ContractCallError("getRound failed", str(exc)) from exc

        tup = cast(
            tuple[
                bytes,
                int,
                int,
                int,
                int,
                int,
                int,
                str,
                str,
                int,
                int,
                int,
                int,
                bool,
                bool,
                int,
                bool,
            ],
            raw,
        )
        return RoundInfo(
            game_id=self._bytes32_to_hex(tup[0]),
            round_id=int(tup[1]),
            total_deposit=int(tup[2]),
            bonus_prize_pool=int(tup[3]),
            dev_fee=int(tup[4]),
            total_win=int(tup[5]),
            yield_amount=int(tup[6]),
            payment_token=tup[7],
            vault=tup[8],
            deposit_fee_bps=int(tup[9]),
            start_ts=int(tup[10]),
            end_ts=int(tup[11]),
            lock_time=int(tup[12]),
            initialized=bool(tup[13]),
            is_settled=bool(tup[14]),
            status=RoundStatus(int(tup[15])),
            is_withdrawn=bool(tup[16]),
        )

    def get_user_deposit(
        self, game_id: str, round_id: int, user_address: str
    ) -> UserDepositInfo:
        """Return deposit info for a specific user in a round."""
        try:
            raw = self._contract.functions.getUserDeposit(
                self._to_bytes32(game_id),
                round_id,
                Web3.to_checksum_address(user_address),
            ).call()
        except ContractLogicError as exc:
            raise ContractCallError("getUserDeposit failed", str(exc)) from exc

        tup = cast(tuple[int, int, bool, bool], raw)
        return UserDepositInfo(
            deposit_amount=int(tup[0]),
            amount_to_claim=int(tup[1]),
            is_claimed=bool(tup[2]),
            exists=bool(tup[3]),
        )

    def get_current_status(self, game_id: str, round_id: int) -> RoundStatus:
        """Return the current RoundStatus enum value."""
        try:
            raw = cast(
                int,
                self._contract.functions.getCurrentStatus(
                    self._to_bytes32(game_id), round_id
                ).call(),
            )
        except ContractLogicError as exc:
            raise ContractCallError("getCurrentStatus failed", str(exc)) from exc
        return RoundStatus(raw)

    def calculate_game_id(self, owner: str, game_name: str) -> str:
        """Compute the deterministic game ID off-chain (view call)."""
        try:
            raw = cast(
                bytes,
                self._contract.functions.calculateGameId(
                    Web3.to_checksum_address(owner), game_name
                ).call(),
            )
        except ContractLogicError as exc:
            raise ContractCallError("calculateGameId failed", str(exc)) from exc
        return self._bytes32_to_hex(raw)

    def get_vault(self, token_address: str) -> str:
        """Return the ERC-4626 vault address for *token_address*."""
        try:
            return cast(
                str,
                self._contract.functions.getVault(
                    Web3.to_checksum_address(token_address)
                ).call(),
            )
        except ContractLogicError as exc:
            raise ContractCallError("getVault failed", str(exc)) from exc

    def is_paused(self) -> bool:
        """Return True if the contract is currently paused."""
        try:
            return cast(bool, self._contract.functions.isPaused().call())
        except ContractLogicError as exc:
            raise ContractCallError("isPaused failed", str(exc)) from exc

    def get_protocol_treasury(self) -> str:
        """Return the protocol treasury address."""
        try:
            return cast(str, self._contract.functions.getProtocolTreasury().call())
        except ContractLogicError as exc:
            raise ContractCallError("getProtocolTreasury failed", str(exc)) from exc

    def get_deployed_amounts(self, game_id: str, round_id: int) -> int:
        """Return the token amount currently deployed to the vault."""
        try:
            return cast(
                int,
                self._contract.functions.getDeployedAmounts(
                    self._to_bytes32(game_id), round_id
                ).call(),
            )
        except ContractLogicError as exc:
            raise ContractCallError("getDeployedAmounts failed", str(exc)) from exc

    def get_deployed_shares(self, game_id: str, round_id: int) -> int:
        """Return the vault shares held for this round."""
        try:
            return cast(
                int,
                self._contract.functions.getDeployedShares(
                    self._to_bytes32(game_id), round_id
                ).call(),
            )
        except ContractLogicError as exc:
            raise ContractCallError("getDeployedShares failed", str(exc)) from exc

    # ── Write: user actions ───────────────────────────────────────────────

    def deposit(
        self, game_id: str, round_id: int, amount_wei: int
    ) -> TransactionResult:
        """
        Deposit *amount_wei* tokens into a round.

        Auto-approves the token if the current allowance is insufficient.
        """
        account = self._require_signer()

        # Fetch token address and auto-approve if needed
        round_info = self.get_round(game_id, round_id)
        self._ensure_allowance(round_info.payment_token, amount_wei, account)

        tx = self._contract.functions.deposit(
            self._to_bytes32(game_id), round_id, amount_wei
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction(cast(TxParams, tx), account)

    def claim(self, game_id: str, round_id: int) -> TransactionResult:
        """Claim principal + prize for the calling user."""
        account = self._require_signer()
        tx = self._contract.functions.claim(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction(cast(TxParams, tx), account)

    # ── Write: game management ─────────────────────────────────────────────

    def create_game(
        self,
        game_name: str,
        dev_fee_bps: int,
        treasury: str,
    ) -> tuple[str, TransactionResult]:
        """
        Create a new game.

        Returns (game_id, TransactionResult).
        """
        account = self._require_signer()
        tx = self._contract.functions.createGame(
            game_name,
            dev_fee_bps,
            Web3.to_checksum_address(treasury),
        ).build_transaction(cast(TxParams, {"from": account.address}))
        result = self._send_transaction(cast(TxParams, tx), account)

        # Calculate game_id deterministically (no need to parse logs)
        game_id = self.calculate_game_id(account.address, game_name)
        logger.info(
            "Game created: id=%s  name=%s  tx=%s", game_id, game_name, result.tx_hash
        )
        return game_id, result

    def create_round(
        self,
        game_id: str,
        start_ts: int,
        end_ts: int,
        lock_time: int,
        deposit_fee_bps: int,
        payment_token: str,
    ) -> tuple[int, TransactionResult]:
        """
        Create a new round for *game_id*.

        Returns (round_id, TransactionResult).
        """
        account = self._require_signer()
        tx = self._contract.functions.createRound(
            self._to_bytes32(game_id),
            start_ts,
            end_ts,
            lock_time,
            deposit_fee_bps,
            Web3.to_checksum_address(payment_token),
        ).build_transaction(cast(TxParams, {"from": account.address}))
        result = self._send_transaction(cast(TxParams, tx), account)

        # round_id = current roundCounter (0-indexed)
        game_info = self.get_game(game_id)
        round_id = int(game_info.round_counter) - 1
        return round_id, result

    # ── Write: game-owner vault / lifecycle ────────────────────────────────

    def deposit_to_vault(self, game_id: str, round_id: int) -> TransactionResult:
        """Deploy this round's deposits into the ERC-4626 vault."""
        account = self._require_signer()
        tx = self._contract.functions.depositToVault(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction(cast(TxParams, tx), account)

    def withdraw_from_vault(self, game_id: str, round_id: int) -> TransactionResult:
        """Withdraw principal + yield from the vault back to the contract."""
        account = self._require_signer()
        tx = self._contract.functions.withdrawFromVault(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction(cast(TxParams, tx), account)

    def settlement(self, game_id: str, round_id: int) -> TransactionResult:
        """Calculate and distribute protocol / dev fees."""
        account = self._require_signer()
        tx = self._contract.functions.settlement(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction(cast(TxParams, tx), account)

    def choose_winner(
        self,
        game_id: str,
        round_id: int,
        winner: str,
        amount_wei: int,
    ) -> TransactionResult:
        """Assign *amount_wei* prize to *winner*."""
        account = self._require_signer()
        tx = self._contract.functions.chooseWinner(
            self._to_bytes32(game_id),
            round_id,
            Web3.to_checksum_address(winner),
            amount_wei,
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction(cast(TxParams, tx), account)

    def finalize_round(self, game_id: str, round_id: int) -> TransactionResult:
        """
        Finalize the round.

        Enables user claims; any remaining prize is returned to treasury.
        """
        account = self._require_signer()
        tx = self._contract.functions.finalizeRound(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction(cast(TxParams, tx), account)

    # ── Token utilities ────────────────────────────────────────────────────

    def get_token_balance(self, token_address: str, user_address: str) -> int:
        """Return ERC-20 token balance in wei."""
        token = self._w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
        )
        try:
            return cast(
                int,
                token.functions.balanceOf(
                    Web3.to_checksum_address(user_address)
                ).call(),
            )
        except ContractLogicError as exc:
            raise ContractCallError("balanceOf failed", str(exc)) from exc

    def get_token_allowance(self, token_address: str, owner_address: str) -> int:
        """Return the current ERC-20 allowance for the YieldPlay contract."""
        token = self._w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
        )
        try:
            return cast(
                int,
                token.functions.allowance(
                    Web3.to_checksum_address(owner_address),
                    Web3.to_checksum_address(self._config.yield_play_address),
                ).call(),
            )
        except ContractLogicError as exc:
            raise ContractCallError("allowance failed", str(exc)) from exc

    def approve_token(
        self, token_address: str, amount_wei: Optional[int] = None
    ) -> TransactionResult:
        """
        Approve the YieldPlay contract to spend *amount_wei* of *token_address*.

        If *amount_wei* is None, approve MaxUint256 (unlimited).
        """
        account = self._require_signer()
        spender_amount = amount_wei if amount_wei is not None else _MAX_UINT256

        token = self._w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
        )
        tx = token.functions.approve(
            Web3.to_checksum_address(self._config.yield_play_address),
            spender_amount,
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction(cast(TxParams, tx), account)

    def get_token_decimals(self, token_address: str) -> int:
        """Return the ERC-20 token decimal places."""
        token = self._w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
        )
        try:
            return cast(int, token.functions.decimals().call())
        except ContractLogicError as exc:
            raise ContractCallError("decimals failed", str(exc)) from exc

    # ── Fee calculation (pure / off-chain) ─────────────────────────────────

    @staticmethod
    def calculate_fee_breakdown(
        total_deposit_gross: int,
        deposit_fee_bps: int,
        dev_fee_bps: int,
        vault_yield: int,
    ) -> FeeBreakdown:
        """
        Reproduce the protocol's fee calculation off-chain.

        All values in wei.  Useful for UIs and pre-flight estimates.
        """
        deposit_fee = total_deposit_gross * deposit_fee_bps // 10_000
        net_deposits = total_deposit_gross - deposit_fee

        performance_fee = vault_yield * _PERFORMANCE_FEE_BPS // 10_000
        yield_after_perf = vault_yield - performance_fee

        dev_fee = yield_after_perf * dev_fee_bps // 10_000
        yield_prize = yield_after_perf - dev_fee

        total_prize_pool = yield_prize + deposit_fee

        return FeeBreakdown(
            total_deposit_gross=total_deposit_gross,
            deposit_fee_collected=deposit_fee,
            net_deposits=net_deposits,
            vault_yield=vault_yield,
            performance_fee=performance_fee,
            dev_fee=dev_fee,
            yield_prize=yield_prize,
            total_prize_pool=total_prize_pool,
        )

    # ── Private helpers ────────────────────────────────────────────────────

    def _ensure_allowance(
        self,
        token_address: str,
        required_amount: int,
        account: LocalAccount,
    ) -> None:
        """Auto-approve if current allowance < required_amount."""
        current = self.get_token_allowance(token_address, account.address)
        if current < required_amount:
            logger.info(
                "Allowance insufficient (%s < %s) – auto-approving MaxUint256",
                current,
                required_amount,
            )
            self.approve_token(token_address)  # approve unlimited
