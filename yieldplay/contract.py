"""
yieldplay/contract.py
──────────────────────
Layer 1 – Direct contract interaction.
"""

from __future__ import annotations

import logging
from typing import Optional, cast

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import (
    BadFunctionCallOutput,
    ContractCustomError,
    ContractLogicError,
    ContractPanicError,
)
from web3.types import TxParams, TxReceipt

from yieldplay.abi import ERC20_ABI, ERC4626_ABI, YIELD_PLAY_ABI
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

_PERFORMANCE_FEE_BPS: int = 2_000
_MAX_UINT256: int = 2**256 - 1


class YieldPlayContract:
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
            "YieldPlayContract init | address=%s signer=%s",
            config.yield_play_address,
            self._account.address if self._account else "read-only",
        )

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
        value = bytes.fromhex(hex_str.removeprefix("0x"))
        if len(value) > 32:
            raise ValueError(f"Value too large for bytes32: {hex_str}")
        return value.rjust(32, b"\x00")

    @staticmethod
    def _bytes32_to_hex(raw: bytes) -> str:
        return "0x" + raw.hex()

    def _send_transaction(
        self,
        fn_name: str,
        tx_params: TxParams,
        account: LocalAccount,
    ) -> TransactionResult:
        """Sign, broadcast and wait for a transaction receipt."""
        try:
            nonce = self._w3.eth.get_transaction_count(
                cast(ChecksumAddress, account.address)
            )
            tx_params["nonce"] = nonce
            tx_params["chainId"] = self._w3.eth.chain_id

            if "gas" not in tx_params:
                estimated = self._w3.eth.estimate_gas(tx_params)
                tx_params["gas"] = estimated
                logger.debug("[%s] gas estimated=%s", fn_name, estimated)

            if "gasPrice" not in tx_params and "maxFeePerGas" not in tx_params:
                tx_params["gasPrice"] = self._w3.eth.gas_price

            logger.info(
                "[%s] sending | from=%s nonce=%s gas=%s",
                fn_name,
                account.address,
                nonce,
                tx_params.get("gas"),
            )

            signed = account.sign_transaction(tx_params)
            raw_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info("[%s] broadcast | hash=%s", fn_name, raw_hash.hex())

            receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(raw_hash)
            tx_hash_hex = receipt["transactionHash"].hex()

            if receipt["status"] == 0:
                logger.error(
                    "[%s] REVERTED | hash=%s block=%s gas_used=%s",
                    fn_name,
                    tx_hash_hex,
                    receipt["blockNumber"],
                    receipt["gasUsed"],
                )
                raise TransactionRevertedError(
                    "Transaction reverted", tx_hash=tx_hash_hex
                )

            logger.info(
                "[%s] confirmed | hash=%s block=%s gas_used=%s",
                fn_name,
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
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            logger.error("[%s] contract error: %s", fn_name, exc)
            raise map_revert_reason(str(exc)) from exc
        except Exception as exc:
            logger.error("[%s] unexpected error: %s", fn_name, exc, exc_info=True)
            raise TransactionError(
                "Failed to send transaction", details=str(exc)
            ) from exc

    # ── Read: game / round info ───────────────────────────────────────────

    def get_game(self, game_id: str) -> GameInfo:
        logger.debug("get_game | game_id=%s", game_id)
        try:
            raw = self._contract.functions.getGame(self._to_bytes32(game_id)).call()
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            logger.error("get_game failed | game_id=%s error=%s", game_id, exc)
            raise ContractCallError("getGame failed", str(exc)) from exc

        tup = cast(tuple[str, str, int, str, int, bool], raw)
        info = GameInfo(
            owner=tup[0],
            game_name=tup[1],
            dev_fee_bps=int(tup[2]),
            treasury=tup[3],
            round_counter=int(tup[4]),
            initialized=bool(tup[5]),
        )
        logger.debug(
            "get_game OK | game_id=%s name=%r owner=%s rounds=%s",
            game_id,
            info.game_name,
            info.owner,
            info.round_counter,
        )
        return info

    def get_round(self, game_id: str, round_id: int) -> RoundInfo:
        logger.debug("get_round | game_id=%s round_id=%s", game_id, round_id)
        try:
            raw = self._contract.functions.getRound(
                self._to_bytes32(game_id), round_id
            ).call()
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            logger.error(
                "get_round failed | game_id=%s round_id=%s error=%s",
                game_id,
                round_id,
                exc,
            )
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
        info = RoundInfo(
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
        logger.debug(
            "get_round OK | game_id=%s round_id=%s status=%s total_deposit=%s settled=%s",
            game_id,
            round_id,
            info.status.label(),
            info.total_deposit,
            info.is_settled,
        )
        return info

    def get_user_deposit(
        self, game_id: str, round_id: int, user_address: str
    ) -> UserDepositInfo:
        logger.debug(
            "get_user_deposit | game_id=%s round_id=%s user=%s",
            game_id,
            round_id,
            user_address,
        )
        try:
            raw = self._contract.functions.getUserDeposit(
                self._to_bytes32(game_id),
                round_id,
                Web3.to_checksum_address(user_address),
            ).call()
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            logger.error(
                "get_user_deposit failed | game_id=%s round_id=%s user=%s error=%s",
                game_id,
                round_id,
                user_address,
                exc,
            )
            raise ContractCallError("getUserDeposit failed", str(exc)) from exc

        tup = cast(tuple[int, int, bool, bool], raw)
        info = UserDepositInfo(
            deposit_amount=int(tup[0]),
            amount_to_claim=int(tup[1]),
            is_claimed=bool(tup[2]),
            exists=bool(tup[3]),
        )
        logger.debug(
            "get_user_deposit OK | user=%s exists=%s deposit=%s claimed=%s",
            user_address,
            info.exists,
            info.deposit_amount,
            info.is_claimed,
        )
        return info

    def get_current_status(self, game_id: str, round_id: int) -> RoundStatus:
        logger.debug("get_current_status | game_id=%s round_id=%s", game_id, round_id)
        try:
            raw = cast(
                int,
                self._contract.functions.getCurrentStatus(
                    self._to_bytes32(game_id), round_id
                ).call(),
            )
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            logger.error(
                "get_current_status failed | game_id=%s round_id=%s error=%s",
                game_id,
                round_id,
                exc,
            )
            raise ContractCallError("getCurrentStatus failed", str(exc)) from exc
        status = RoundStatus(raw)
        logger.debug(
            "get_current_status OK | game_id=%s round_id=%s status=%s(%s)",
            game_id,
            round_id,
            status.value,
            status.label(),
        )
        return status

    def calculate_game_id(self, owner: str, game_name: str) -> str:
        logger.debug("calculate_game_id | owner=%s name=%r", owner, game_name)
        try:
            raw = cast(
                bytes,
                self._contract.functions.calculateGameId(
                    Web3.to_checksum_address(owner), game_name
                ).call(),
            )
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("calculateGameId failed", str(exc)) from exc
        return self._bytes32_to_hex(raw)

    def get_vault(self, token_address: str) -> str:
        logger.debug("get_vault | token=%s", token_address)
        try:
            result = cast(
                str,
                self._contract.functions.vaults(
                    Web3.to_checksum_address(token_address)
                ).call(),
            )
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("vaults failed", str(exc)) from exc
        logger.debug("get_vault OK | token=%s vault=%s", token_address, result)
        return result

    def is_paused(self) -> bool:
        try:
            return cast(bool, self._contract.functions.paused().call())
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("paused failed", str(exc)) from exc

    def get_protocol_treasury(self) -> str:
        try:
            return cast(str, self._contract.functions.protocolTreasury().call())
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("protocolTreasury failed", str(exc)) from exc

    def get_deployed_amounts(self, game_id: str, round_id: int) -> int:
        try:
            return cast(
                int,
                self._contract.functions.deployedAmounts(
                    self._to_bytes32(game_id), round_id
                ).call(),
            )
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("deployedAmounts failed", str(exc)) from exc

    def get_deployed_shares(self, game_id: str, round_id: int) -> int:
        try:
            return cast(
                int,
                self._contract.functions.deployedShares(
                    self._to_bytes32(game_id), round_id
                ).call(),
            )
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("deployedShares failed", str(exc)) from exc

    # ── Write: user ───────────────────────────────────────────────────────

    def deposit(
        self, game_id: str, round_id: int, amount_wei: int
    ) -> TransactionResult:
        account = self._require_signer()
        logger.info(
            "deposit | game_id=%s round_id=%s amount_wei=%s from=%s",
            game_id,
            round_id,
            amount_wei,
            account.address,
        )
        round_info = self.get_round(game_id, round_id)
        self._ensure_allowance(round_info.payment_token, amount_wei, account)
        tx = self._contract.functions.deposit(
            self._to_bytes32(game_id), round_id, amount_wei
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction("deposit", cast(TxParams, tx), account)

    def claim(self, game_id: str, round_id: int) -> TransactionResult:
        account = self._require_signer()
        logger.info(
            "claim | game_id=%s round_id=%s from=%s",
            game_id,
            round_id,
            account.address,
        )
        tx = self._contract.functions.claim(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction("claim", cast(TxParams, tx), account)

    # ── Write: game management ─────────────────────────────────────────────

    def create_game(
        self, game_name: str, dev_fee_bps: int, treasury: str
    ) -> tuple[str, TransactionResult]:
        account = self._require_signer()
        logger.info(
            "create_game | name=%r dev_fee_bps=%s treasury=%s from=%s",
            game_name,
            dev_fee_bps,
            treasury,
            account.address,
        )

        # calculateGameId is pure — safe to call even if createGame would revert
        # This lets us know the game_id before sending the tx
        game_id = self.calculate_game_id(account.address, game_name)
        logger.debug("create_game | computed game_id=%s", game_id)

        tx = self._contract.functions.createGame(
            game_name,
            dev_fee_bps,
            Web3.to_checksum_address(treasury),
        ).build_transaction(cast(TxParams, {"from": account.address}))

        result = self._send_transaction("createGame", cast(TxParams, tx), account)
        logger.info("create_game done | game_id=%s tx=%s", game_id, result.tx_hash)
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
        account = self._require_signer()
        logger.info(
            "create_round | game_id=%s start=%s end=%s lock=%s fee_bps=%s token=%s from=%s",
            game_id,
            start_ts,
            end_ts,
            lock_time,
            deposit_fee_bps,
            payment_token,
            account.address,
        )

        tx = self._contract.functions.createRound(
            self._to_bytes32(game_id),
            start_ts,
            end_ts,
            lock_time,
            deposit_fee_bps,
            Web3.to_checksum_address(payment_token),
        ).build_transaction(cast(TxParams, {"from": account.address}))

        result = self._send_transaction("createRound", cast(TxParams, tx), account)

        # Parse round_id from the RoundCreated event in the receipt
        # Fallback: roundCounter - 1 (safe because createRound increments it)
        round_id = self._parse_round_id_from_receipt(result.tx_hash) or (
            self.get_game(game_id).round_counter - 1
        )
        logger.info(
            "create_round done | game_id=%s round_id=%s tx=%s",
            game_id,
            round_id,
            result.tx_hash,
        )
        return int(round_id), result

    # ── Write: vault lifecycle ────────────────────────────────────────────

    def deposit_to_vault(self, game_id: str, round_id: int) -> TransactionResult:
        account = self._require_signer()
        logger.info("deposit_to_vault | game_id=%s round_id=%s", game_id, round_id)
        tx = self._contract.functions.depositToVault(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction("depositToVault", cast(TxParams, tx), account)

    def withdraw_from_vault(self, game_id: str, round_id: int) -> TransactionResult:
        account = self._require_signer()
        logger.info("withdraw_from_vault | game_id=%s round_id=%s", game_id, round_id)
        tx = self._contract.functions.withdrawFromVault(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction("withdrawFromVault", cast(TxParams, tx), account)

    def settlement(self, game_id: str, round_id: int) -> TransactionResult:
        account = self._require_signer()
        logger.info("settlement | game_id=%s round_id=%s", game_id, round_id)
        tx = self._contract.functions.settlement(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction("settlement", cast(TxParams, tx), account)

    def choose_winner(
        self, game_id: str, round_id: int, winner: str, amount_wei: int
    ) -> TransactionResult:
        account = self._require_signer()
        logger.info(
            "choose_winner | game_id=%s round_id=%s winner=%s amount=%s",
            game_id,
            round_id,
            winner,
            amount_wei,
        )
        tx = self._contract.functions.chooseWinner(
            self._to_bytes32(game_id),
            round_id,
            Web3.to_checksum_address(winner),
            amount_wei,
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction("chooseWinner", cast(TxParams, tx), account)

    def finalize_round(self, game_id: str, round_id: int) -> TransactionResult:
        account = self._require_signer()
        logger.info("finalize_round | game_id=%s round_id=%s", game_id, round_id)
        tx = self._contract.functions.finalizeRound(
            self._to_bytes32(game_id), round_id
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction("finalizeRound", cast(TxParams, tx), account)

    # ── Token utilities ────────────────────────────────────────────────────

    def get_token_balance(self, token_address: str, user_address: str) -> int:
        token = self._w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
        )
        try:
            balance = cast(
                int,
                token.functions.balanceOf(
                    Web3.to_checksum_address(user_address)
                ).call(),
            )
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("balanceOf failed", str(exc)) from exc
        logger.debug(
            "get_token_balance | token=%s user=%s balance=%s",
            token_address,
            user_address,
            balance,
        )
        return balance

    def get_token_allowance(self, token_address: str, owner_address: str) -> int:
        token = self._w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
        )
        try:
            allowance = cast(
                int,
                token.functions.allowance(
                    Web3.to_checksum_address(owner_address),
                    Web3.to_checksum_address(self._config.yield_play_address),
                ).call(),
            )
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("allowance failed", str(exc)) from exc
        logger.debug(
            "get_token_allowance | token=%s owner=%s allowance=%s",
            token_address,
            owner_address,
            allowance,
        )
        return allowance

    def approve_token(
        self, token_address: str, amount_wei: Optional[int] = None
    ) -> TransactionResult:
        account = self._require_signer()
        spender_amount = amount_wei if amount_wei is not None else _MAX_UINT256
        logger.info(
            "approve_token | token=%s spender=%s amount=%s",
            token_address,
            self._config.yield_play_address,
            "MaxUint256" if amount_wei is None else amount_wei,
        )
        token = self._w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
        )
        tx = token.functions.approve(
            Web3.to_checksum_address(self._config.yield_play_address),
            spender_amount,
        ).build_transaction(cast(TxParams, {"from": account.address}))
        return self._send_transaction("approve", cast(TxParams, tx), account)

    def get_token_decimals(self, token_address: str) -> int:
        token = self._w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=ERC20_ABI
        )
        try:
            return cast(int, token.functions.decimals().call())
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("decimals failed", str(exc)) from exc

    # ── Projected yield (ERC-4626) ─────────────────────────────────────────

    def _parse_round_id_from_receipt(self, tx_hash: str) -> int | None:
        """
        Parse the roundId from the RoundCreated event in a transaction receipt.
        Returns None if the event cannot be found (fallback to roundCounter-1).
        """
        try:
            receipt = self._w3.eth.get_transaction_receipt(tx_hash)
            # RoundCreated: gameId (indexed), roundId (indexed), ...
            # indexed topics: [0]=event_sig [1]=gameId [2]=roundId
            from web3 import Web3 as _W3

            event_sig = _W3.keccak(
                text="RoundCreated(bytes32,uint256,uint64,uint64,uint64,uint16,address,address)"
            ).hex()
            for log in receipt.get("logs", []):
                topics = log.get("topics", [])
                if topics and topics[0].hex() == event_sig and len(topics) >= 3:
                    round_id = int(topics[2].hex(), 16)
                    logger.debug(
                        "_parse_round_id_from_receipt | tx=%s round_id=%s",
                        tx_hash,
                        round_id,
                    )
                    return round_id
        except Exception as exc:
            logger.warning(
                "_parse_round_id_from_receipt failed (will use roundCounter fallback): %s",
                exc,
            )
        return None

    def get_projected_yield(self, game_id: str, round_id: int) -> int:
        """
        Yield thực tế đang tích lũy trong vault.
        projected_yield = vault.previewRedeem(deployedShares) - deployedAmounts
        """
        deployed_shares = self.get_deployed_shares(game_id, round_id)
        if deployed_shares == 0:
            logger.debug(
                "get_projected_yield | game_id=%s round_id=%s no shares deployed → 0",
                game_id,
                round_id,
            )
            return 0

        deployed_amount = self.get_deployed_amounts(game_id, round_id)
        round_info = self.get_round(game_id, round_id)

        vault = self._w3.eth.contract(
            address=Web3.to_checksum_address(round_info.vault),
            abi=ERC4626_ABI,
        )
        try:
            current_value = cast(
                int, vault.functions.previewRedeem(deployed_shares).call()
            )
        except (
            ContractLogicError,
            ContractCustomError,
            ContractPanicError,
            BadFunctionCallOutput,
        ) as exc:
            raise ContractCallError("previewRedeem failed", str(exc)) from exc

        projected = max(0, current_value - deployed_amount)
        logger.debug(
            "get_projected_yield | game_id=%s round_id=%s shares=%s deployed=%s "
            "current_value=%s projected_yield=%s",
            game_id,
            round_id,
            deployed_shares,
            deployed_amount,
            current_value,
            projected,
        )
        return projected

    # ── Fee calculation (off-chain) ────────────────────────────────────────

    @staticmethod
    def calculate_fee_breakdown(
        total_deposit_gross: int,
        deposit_fee_bps: int,
        dev_fee_bps: int,
        vault_yield: int,
    ) -> FeeBreakdown:
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

    # ── Private ────────────────────────────────────────────────────────────

    def _ensure_allowance(
        self, token_address: str, required_amount: int, account: LocalAccount
    ) -> None:
        current = self.get_token_allowance(token_address, account.address)
        if current < required_amount:
            logger.info(
                "_ensure_allowance | insufficient current=%s required=%s → approving MaxUint256",
                current,
                required_amount,
            )
            self.approve_token(token_address)
        else:
            logger.debug(
                "_ensure_allowance | OK current=%s >= required=%s",
                current,
                required_amount,
            )
