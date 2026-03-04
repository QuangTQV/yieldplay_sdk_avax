"""
tests/test_contract.py
───────────────────────
Test suite for YieldPlayContract (Layer 1).

Hai nhóm test:

  UNIT  — không cần RPC, chạy offline với mock
  INTEGRATION — cần PRIVATE_KEY + RPC thật (Sepolia)
                Chạy với: pytest -m integration -v

Chạy unit test:
    cd yieldplay-sdk
    pytest tests/test_contract.py -v

Chạy tất cả (cần .env):
    pytest tests/test_contract.py -v -m "unit or integration"
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractCustomError, ContractLogicError

from yieldplay.contract import YieldPlayContract
from yieldplay.exceptions import (
    AlreadyClaimedError,
    ContractCallError,
    FundsNotDeployedError,
    GameAlreadyExistsError,
    InvalidAmountError,
    InvalidDevFeeBpsError,
    RoundNotActiveError,
    SignerNotConfiguredError,
    TransactionError,
    UnauthorizedError,
    map_revert_reason,
)
from yieldplay.types import (
    FeeBreakdown,
    GameInfo,
    RoundInfo,
    RoundStatus,
    SDKConfig,
    UserDepositInfo,
)

load_dotenv()
logging.basicConfig(level=logging.WARNING)

# ── Test constants ─────────────────────────────────────────────────────────

YIELDPLAY_ADDRESS = "0x02AA158dc37f4E1128CeE3E69e9E59920E799F90"
TOKEN_ADDRESS = "0xdd13E55209Fd76AfE204dBda4007C227904f0a81"
VAULT_ADDRESS = "0xf323aEa80bF9962e26A3499a4Ffd70205590F54d"
RPC_URL = os.getenv("RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

# Known deployed game on Sepolia (used for read-only tests)
# Replace with a real game_id from your Sepolia deployment
KNOWN_GAME_ID = os.getenv("TEST_GAME_ID", "")
KNOWN_ROUND_ID = int(os.getenv("TEST_ROUND_ID", "0"))

_has_private_key = bool(PRIVATE_KEY)
_has_known_game = bool(KNOWN_GAME_ID)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def sdk_readonly() -> YieldPlayContract:
    """SDK without signer — for read-only integration tests."""
    return YieldPlayContract(
        SDKConfig(
            yield_play_address=YIELDPLAY_ADDRESS,
            rpc_url=RPC_URL,
        )
    )


@pytest.fixture(scope="session")
def sdk_signer() -> Optional[YieldPlayContract]:
    """SDK with signer — for write integration tests."""
    if not _has_private_key:
        return None
    return YieldPlayContract(
        SDKConfig(
            yield_play_address=YIELDPLAY_ADDRESS,
            rpc_url=RPC_URL,
            private_key=PRIVATE_KEY,
        )
    )


@pytest.fixture
def mock_sdk() -> YieldPlayContract:
    """SDK with a mocked web3 — for fast unit tests."""
    sdk = YieldPlayContract.__new__(YieldPlayContract)
    sdk._config = SDKConfig(
        yield_play_address=YIELDPLAY_ADDRESS,
        rpc_url="http://localhost:8545",
        private_key="0x" + "a" * 64,
    )
    sdk._w3 = MagicMock()
    sdk._account = Account.from_key("0x" + "a" * 64)
    sdk._contract = MagicMock()
    return sdk


# ══════════════════════════════════════════════════════════════════════════
# UNIT TESTS — no network required
# ══════════════════════════════════════════════════════════════════════════


class TestStaticHelpers:
    """Pure / static methods — no RPC."""

    @pytest.mark.unit
    def test_to_bytes32_normal(self):
        hex_str = "0x" + "ab" * 32
        result = YieldPlayContract._to_bytes32(hex_str)
        assert isinstance(result, bytes)
        assert len(result) == 32

    @pytest.mark.unit
    def test_to_bytes32_short_pads(self):
        result = YieldPlayContract._to_bytes32("0xdeadbeef")
        assert len(result) == 32
        assert result[-4:] == bytes.fromhex("deadbeef")

    @pytest.mark.unit
    def test_to_bytes32_no_prefix(self):
        result = YieldPlayContract._to_bytes32("deadbeef")
        assert len(result) == 32

    @pytest.mark.unit
    def test_bytes32_roundtrip(self):
        original = "0x" + "ff" * 32
        as_bytes = YieldPlayContract._to_bytes32(original)
        back = YieldPlayContract._bytes32_to_hex(as_bytes)
        assert back == original

    @pytest.mark.unit
    def test_calculate_game_id_offline(self, mock_sdk):
        """calculate_game_id must work with no RPC call."""
        owner = "0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5"
        name = "wordle"
        game_id = mock_sdk.calculate_game_id(owner, name)

        assert game_id.startswith("0x")
        assert len(game_id) == 66  # "0x" + 64 hex chars

    @pytest.mark.unit
    def test_calculate_game_id_deterministic(self, mock_sdk):
        """Same inputs always produce same game_id."""
        owner = "0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5"
        name = "test-game"
        assert mock_sdk.calculate_game_id(owner, name) == mock_sdk.calculate_game_id(
            owner, name
        )

    @pytest.mark.unit
    def test_calculate_game_id_differs_by_name(self, mock_sdk):
        owner = "0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5"
        assert mock_sdk.calculate_game_id(
            owner, "game-a"
        ) != mock_sdk.calculate_game_id(owner, "game-b")

    @pytest.mark.unit
    def test_calculate_game_id_differs_by_owner(self, mock_sdk):
        name = "same-game"
        owner_a = "0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5"
        owner_b = "0x1234567890123456789012345678901234567890"
        assert mock_sdk.calculate_game_id(owner_a, name) != mock_sdk.calculate_game_id(
            owner_b, name
        )

    @pytest.mark.unit
    def test_calculate_game_id_no_rpc(self, mock_sdk):
        """calculate_game_id must NOT call any web3 method."""
        mock_sdk._w3.reset_mock()
        mock_sdk.calculate_game_id("0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5", "test")
        mock_sdk._w3.eth.call.assert_not_called()
        mock_sdk._contract.functions.calculateGameId.assert_not_called()


class TestFeeBreakdown:
    """calculate_fee_breakdown — pure arithmetic."""

    @pytest.mark.unit
    def test_zero_yield(self):
        fb = YieldPlayContract.calculate_fee_breakdown(
            total_deposit_gross=1_000_000,
            deposit_fee_bps=0,
            dev_fee_bps=0,
            vault_yield=0,
        )
        assert fb.vault_yield == 0
        assert fb.performance_fee == 0
        assert fb.dev_fee == 0
        assert fb.yield_prize == 0
        assert fb.total_prize_pool == 0

    @pytest.mark.unit
    def test_deposit_fee_goes_to_prize_pool(self):
        fb = YieldPlayContract.calculate_fee_breakdown(
            total_deposit_gross=1_000_000,
            deposit_fee_bps=100,  # 1%
            dev_fee_bps=0,
            vault_yield=0,
        )
        assert fb.deposit_fee_collected == 10_000
        assert fb.net_deposits == 990_000
        assert fb.total_prize_pool == 10_000  # deposit fee becomes prize

    @pytest.mark.unit
    def test_performance_fee_is_20_pct(self):
        fb = YieldPlayContract.calculate_fee_breakdown(
            total_deposit_gross=1_000_000,
            deposit_fee_bps=0,
            dev_fee_bps=0,
            vault_yield=100_000,
        )
        assert fb.performance_fee == 20_000  # 20% of 100_000
        assert fb.yield_prize == 80_000  # 80% remaining

    @pytest.mark.unit
    def test_dev_fee_applied_after_perf_fee(self):
        fb = YieldPlayContract.calculate_fee_breakdown(
            total_deposit_gross=1_000_000,
            deposit_fee_bps=0,
            dev_fee_bps=1_000,  # 10%
            vault_yield=100_000,
        )
        # 100_000 yield → 20_000 perf → 80_000 net → 8_000 dev → 72_000 yield_prize
        assert fb.performance_fee == 20_000
        assert fb.dev_fee == 8_000
        assert fb.yield_prize == 72_000

    @pytest.mark.unit
    def test_full_breakdown_adds_up(self):
        fb = YieldPlayContract.calculate_fee_breakdown(
            total_deposit_gross=10_000_000,
            deposit_fee_bps=200,  # 2%
            dev_fee_bps=500,  # 5%
            vault_yield=500_000,
        )
        # Conservation checks
        assert fb.deposit_fee_collected + fb.net_deposits == 10_000_000
        assert fb.performance_fee + (fb.dev_fee + fb.yield_prize) == fb.vault_yield
        assert fb.total_prize_pool == fb.yield_prize + fb.deposit_fee_collected

    @pytest.mark.unit
    def test_returns_fee_breakdown_model(self):
        fb = YieldPlayContract.calculate_fee_breakdown(
            total_deposit_gross=0, deposit_fee_bps=0, dev_fee_bps=0, vault_yield=0
        )
        assert isinstance(fb, FeeBreakdown)


class TestExceptionMapping:
    """map_revert_reason covers all custom errors from the ABI."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "error_str,expected_type",
        [
            ("ContractCustomError: InvalidDevFeeBps", InvalidDevFeeBpsError),
            ("execution reverted: InvalidDevFeeBps", InvalidDevFeeBpsError),
            ("ContractCustomError: RoundNotActive", RoundNotActiveError),
            ("ContractCustomError: AlreadyClaimed", AlreadyClaimedError),
            ("ContractCustomError: GameAlreadyExists", GameAlreadyExistsError),
            ("ContractCustomError: Unauthorized", UnauthorizedError),
            ("ContractCustomError: FundsNotDeployed", FundsNotDeployedError),
            ("ContractCustomError: InvalidAmount", InvalidAmountError),
            ("something completely unknown", TransactionError),
        ],
    )
    def test_map_revert(self, error_str, expected_type):
        exc = map_revert_reason(error_str)
        assert isinstance(exc, expected_type), (
            f"Expected {expected_type.__name__}, got {type(exc).__name__} for: {error_str!r}"
        )

    @pytest.mark.unit
    def test_all_mapped_errors_are_yield_play_errors(self):
        from yieldplay.exceptions import YieldPlayError

        errors = [
            "InvalidDevFeeBps",
            "RoundNotActive",
            "AlreadyClaimed",
            "GameAlreadyExists",
            "Unauthorized",
            "FundsNotDeployed",
            "InvalidAmount",
            "GameNotFound",
            "RoundNotFound",
        ]
        for e in errors:
            exc = map_revert_reason(f"ContractCustomError: {e}")
            assert isinstance(exc, YieldPlayError), f"{e} not mapped to YieldPlayError"


class TestSignerRequired:
    """Methods that require a private key should raise SignerNotConfiguredError."""

    @pytest.fixture
    def sdk_no_signer(self) -> YieldPlayContract:
        sdk = YieldPlayContract.__new__(YieldPlayContract)
        sdk._config = SDKConfig(
            yield_play_address=YIELDPLAY_ADDRESS,
            rpc_url="http://localhost:8545",
        )
        sdk._w3 = MagicMock()
        sdk._account = None
        sdk._contract = MagicMock()
        return sdk

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "method,args",
        [
            ("deposit", ("0x" + "0" * 64, 0, 1000)),
            ("claim", ("0x" + "0" * 64, 0)),
            ("create_game", ("test", 500, "0x" + "0" * 40)),
            ("deposit_to_vault", ("0x" + "0" * 64, 0)),
            ("withdraw_from_vault", ("0x" + "0" * 64, 0)),
            ("settlement", ("0x" + "0" * 64, 0)),
            ("finalize_round", ("0x" + "0" * 64, 0)),
            ("approve_token", ("0x" + "0" * 40,)),
        ],
    )
    def test_raises_signer_not_configured(self, sdk_no_signer, method, args):
        with pytest.raises(SignerNotConfiguredError):
            getattr(sdk_no_signer, method)(*args)


class TestReadOnlyMocked:
    """Read functions with mocked contract calls."""

    @pytest.mark.unit
    def test_get_game_parses_tuple(self, mock_sdk):
        mock_sdk._contract.functions.getGame.return_value.call.return_value = (
            "0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5",  # owner
            "TestGame",  # gameName
            500,  # devFeeBps (uint16)
            "0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5",  # treasury
            3,  # roundCounter
            True,  # initialized
        )
        game_id = "0x" + "ab" * 32
        result = mock_sdk.get_game(game_id)

        assert isinstance(result, GameInfo)
        assert result.game_name == "TestGame"
        assert result.dev_fee_bps == 500
        assert result.round_counter == 3
        assert result.initialized is True

    @pytest.mark.unit
    def test_get_round_parses_tuple(self, mock_sdk):
        game_id_bytes = bytes.fromhex("ab" * 32)
        mock_sdk._contract.functions.getRound.return_value.call.return_value = (
            game_id_bytes,  # gameId bytes32
            0,  # roundId
            1_000_000,  # totalDeposit
            0,  # bonusPrizePool
            0,  # devFee
            0,  # totalWin
            0,  # yieldAmount
            TOKEN_ADDRESS,  # paymentToken
            VAULT_ADDRESS,  # vault
            100,  # depositFeeBps (uint16)
            1_000_000_000,  # startTs (uint64)
            1_100_000_000,  # endTs (uint64)
            86400,  # lockTime (uint64)
            True,  # initialized
            False,  # isSettled
            1,  # status = IN_PROGRESS
            False,  # isWithdrawn
        )
        result = mock_sdk.get_round("0x" + "ab" * 32, 0)

        assert isinstance(result, RoundInfo)
        assert result.total_deposit == 1_000_000
        assert result.deposit_fee_bps == 100
        assert result.status == RoundStatus.IN_PROGRESS
        assert result.is_settled is False

    @pytest.mark.unit
    def test_get_user_deposit_parses_tuple(self, mock_sdk):
        mock_sdk._contract.functions.getUserDeposit.return_value.call.return_value = (
            500_000,  # depositAmount
            500_000,  # amountToClaim
            False,  # isClaimed
            True,  # exists
        )
        result = mock_sdk.get_user_deposit("0x" + "ab" * 32, 0, "0x" + "cd" * 20)

        assert isinstance(result, UserDepositInfo)
        assert result.deposit_amount == 500_000
        assert result.exists is True
        assert result.is_claimed is False

    @pytest.mark.unit
    def test_get_current_status_returns_enum(self, mock_sdk):
        mock_sdk._contract.functions.getCurrentStatus.return_value.call.return_value = 3
        result = mock_sdk.get_current_status("0x" + "ab" * 32, 0)
        assert result == RoundStatus.CHOOSING_WINNERS

    @pytest.mark.unit
    def test_is_paused(self, mock_sdk):
        mock_sdk._contract.functions.paused.return_value.call.return_value = True
        assert mock_sdk.is_paused() is True

        mock_sdk._contract.functions.paused.return_value.call.return_value = False
        assert mock_sdk.is_paused() is False

    @pytest.mark.unit
    def test_get_protocol_treasury(self, mock_sdk):
        addr = "0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5"
        mock_sdk._contract.functions.protocolTreasury.return_value.call.return_value = (
            addr
        )
        assert mock_sdk.get_protocol_treasury() == addr

    @pytest.mark.unit
    def test_get_deployed_amounts(self, mock_sdk):
        mock_sdk._contract.functions.deployedAmounts.return_value.call.return_value = (
            9_999_999
        )
        result = mock_sdk.get_deployed_amounts("0x" + "ab" * 32, 0)
        assert result == 9_999_999

    @pytest.mark.unit
    def test_get_deployed_shares(self, mock_sdk):
        mock_sdk._contract.functions.deployedShares.return_value.call.return_value = (
            8_888_888
        )
        result = mock_sdk.get_deployed_shares("0x" + "ab" * 32, 0)
        assert result == 8_888_888

    @pytest.mark.unit
    def test_get_token_balance(self, mock_sdk):
        erc20_mock = MagicMock()
        erc20_mock.functions.balanceOf.return_value.call.return_value = 5_000_000
        mock_sdk._w3.eth.contract.return_value = erc20_mock
        result = mock_sdk.get_token_balance(TOKEN_ADDRESS, "0x" + "cd" * 20)
        assert result == 5_000_000

    @pytest.mark.unit
    def test_get_token_allowance(self, mock_sdk):
        erc20_mock = MagicMock()
        erc20_mock.functions.allowance.return_value.call.return_value = 1_000_000
        mock_sdk._w3.eth.contract.return_value = erc20_mock
        result = mock_sdk.get_token_allowance(TOKEN_ADDRESS, "0x" + "cd" * 20)
        assert result == 1_000_000

    @pytest.mark.unit
    def test_contract_call_error_on_logic_error(self, mock_sdk):
        mock_sdk._contract.functions.getGame.return_value.call.side_effect = (
            ContractLogicError("execution reverted")
        )
        with pytest.raises(ContractCallError):
            mock_sdk.get_game("0x" + "ab" * 32)

    @pytest.mark.unit
    def test_contract_call_error_on_custom_error(self, mock_sdk):
        mock_sdk._contract.functions.getGame.return_value.call.side_effect = (
            ContractCustomError("GameNotFound", b"")
        )
        with pytest.raises(ContractCallError):
            mock_sdk.get_game("0x" + "ab" * 32)


class TestProjectedYield:
    """get_projected_yield uses ERC-4626 vault."""

    @pytest.mark.unit
    def test_zero_when_no_shares(self, mock_sdk):
        mock_sdk._contract.functions.deployedShares.return_value.call.return_value = 0
        result = mock_sdk.get_projected_yield("0x" + "ab" * 32, 0)
        assert result == 0

    @pytest.mark.unit
    def test_calculates_yield_from_vault(self, mock_sdk):
        # deployedShares = 1_000_000, deployedAmounts = 1_000_000
        # vault.previewRedeem → 1_050_000 (5% yield)
        mock_sdk._contract.functions.deployedShares.return_value.call.return_value = (
            1_000_000
        )
        mock_sdk._contract.functions.deployedAmounts.return_value.call.return_value = (
            1_000_000
        )

        # Mock getRound to get vault address
        game_id_bytes = bytes.fromhex("ab" * 32)
        mock_sdk._contract.functions.getRound.return_value.call.return_value = (
            game_id_bytes,
            0,
            1_000_000,
            0,
            0,
            0,
            0,
            TOKEN_ADDRESS,
            VAULT_ADDRESS,
            100,
            0,
            0,
            0,
            True,
            False,
            1,
            False,
        )

        # Mock vault contract
        vault_mock = MagicMock()
        vault_mock.functions.previewRedeem.return_value.call.return_value = 1_050_000
        mock_sdk._w3.eth.contract.return_value = vault_mock

        result = mock_sdk.get_projected_yield("0x" + "ab" * 32, 0)
        assert result == 50_000  # 1_050_000 - 1_000_000

    @pytest.mark.unit
    def test_returns_zero_when_current_value_less_than_deployed(self, mock_sdk):
        """Should never return negative — max(0, value)."""
        mock_sdk._contract.functions.deployedShares.return_value.call.return_value = (
            1_000_000
        )
        mock_sdk._contract.functions.deployedAmounts.return_value.call.return_value = (
            1_000_000
        )
        game_id_bytes = bytes.fromhex("ab" * 32)
        mock_sdk._contract.functions.getRound.return_value.call.return_value = (
            game_id_bytes,
            0,
            1_000_000,
            0,
            0,
            0,
            0,
            TOKEN_ADDRESS,
            VAULT_ADDRESS,
            100,
            0,
            0,
            0,
            True,
            False,
            1,
            False,
        )
        vault_mock = MagicMock()
        vault_mock.functions.previewRedeem.return_value.call.return_value = (
            900_000  # loss
        )
        mock_sdk._w3.eth.contract.return_value = vault_mock

        result = mock_sdk.get_projected_yield("0x" + "ab" * 32, 0)
        assert result == 0  # no negative yield


class TestEnsureAllowance:
    """_ensure_allowance auto-approves when needed."""

    @pytest.mark.unit
    def test_no_approve_when_sufficient(self, mock_sdk):
        erc20_mock = MagicMock()
        erc20_mock.functions.allowance.return_value.call.return_value = 1_000_000
        mock_sdk._w3.eth.contract.return_value = erc20_mock

        with patch.object(mock_sdk, "approve_token") as mock_approve:
            mock_sdk._ensure_allowance(TOKEN_ADDRESS, 500_000, mock_sdk._account)
            mock_approve.assert_not_called()

    @pytest.mark.unit
    def test_approves_when_insufficient(self, mock_sdk):
        erc20_mock = MagicMock()
        erc20_mock.functions.allowance.return_value.call.return_value = 0
        mock_sdk._w3.eth.contract.return_value = erc20_mock

        with patch.object(mock_sdk, "approve_token") as mock_approve:
            mock_approve.return_value = MagicMock()
            mock_sdk._ensure_allowance(TOKEN_ADDRESS, 500_000, mock_sdk._account)
            mock_approve.assert_called_once_with(TOKEN_ADDRESS)


# ══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — need real Sepolia RPC
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestReadOnlyIntegration:
    """Read-only integration tests — no PRIVATE_KEY needed."""

    def test_rpc_connection(self, sdk_readonly):
        assert sdk_readonly.w3.is_connected(), "Cannot connect to Sepolia RPC"

    def test_is_paused_returns_bool(self, sdk_readonly):
        result = sdk_readonly.is_paused()
        assert isinstance(result, bool)

    def test_get_protocol_treasury_is_address(self, sdk_readonly):
        addr = sdk_readonly.get_protocol_treasury()
        assert Web3.is_address(addr), f"Not an address: {addr}"

    def test_get_vault_for_token(self, sdk_readonly):
        vault = sdk_readonly.get_vault(TOKEN_ADDRESS)
        assert Web3.is_address(vault), f"Not an address: {vault}"

    def test_get_token_balance_returns_int(self, sdk_readonly):
        balance = sdk_readonly.get_token_balance(TOKEN_ADDRESS, YIELDPLAY_ADDRESS)
        assert isinstance(balance, int)
        assert balance >= 0

    def test_get_token_decimals(self, sdk_readonly):
        decimals = sdk_readonly.get_token_decimals(TOKEN_ADDRESS)
        assert isinstance(decimals, int)
        assert 0 <= decimals <= 18

    def test_calculate_game_id_consistent(self, sdk_readonly):
        owner = "0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5"
        name = "test-consistency"
        a = sdk_readonly.calculate_game_id(owner, name)
        b = sdk_readonly.calculate_game_id(owner, name)
        assert a == b
        assert a.startswith("0x") and len(a) == 66

    @pytest.mark.skipif(not _has_known_game, reason="TEST_GAME_ID not set")
    def test_get_game(self, sdk_readonly):
        game = sdk_readonly.get_game(KNOWN_GAME_ID)
        assert isinstance(game, GameInfo)
        assert game.initialized is True
        assert Web3.is_address(game.owner)
        assert 0 <= game.dev_fee_bps <= 10_000

    @pytest.mark.skipif(not _has_known_game, reason="TEST_GAME_ID not set")
    def test_get_round(self, sdk_readonly):
        round_info = sdk_readonly.get_round(KNOWN_GAME_ID, KNOWN_ROUND_ID)
        assert isinstance(round_info, RoundInfo)
        assert round_info.initialized is True
        assert round_info.round_id == KNOWN_ROUND_ID
        assert Web3.is_address(round_info.payment_token)

    @pytest.mark.skipif(not _has_known_game, reason="TEST_GAME_ID not set")
    def test_get_current_status(self, sdk_readonly):
        status = sdk_readonly.get_current_status(KNOWN_GAME_ID, KNOWN_ROUND_ID)
        assert isinstance(status, RoundStatus)
        assert status in list(RoundStatus)

    @pytest.mark.skipif(not _has_known_game, reason="TEST_GAME_ID not set")
    def test_get_user_deposit_non_participant(self, sdk_readonly):
        # Zero address has never deposited
        zero = "0x0000000000000000000000000000000000000001"
        info = sdk_readonly.get_user_deposit(KNOWN_GAME_ID, KNOWN_ROUND_ID, zero)
        assert isinstance(info, UserDepositInfo)
        assert info.exists is False
        assert info.deposit_amount == 0

    @pytest.mark.skipif(not _has_known_game, reason="TEST_GAME_ID not set")
    def test_deployed_amounts_and_shares(self, sdk_readonly):
        amounts = sdk_readonly.get_deployed_amounts(KNOWN_GAME_ID, KNOWN_ROUND_ID)
        shares = sdk_readonly.get_deployed_shares(KNOWN_GAME_ID, KNOWN_ROUND_ID)
        assert isinstance(amounts, int) and amounts >= 0
        assert isinstance(shares, int) and shares >= 0

    @pytest.mark.skipif(not _has_known_game, reason="TEST_GAME_ID not set")
    def test_projected_yield_non_negative(self, sdk_readonly):
        yield_val = sdk_readonly.get_projected_yield(KNOWN_GAME_ID, KNOWN_ROUND_ID)
        assert isinstance(yield_val, int)
        assert yield_val >= 0

    @pytest.mark.skipif(not _has_known_game, reason="TEST_GAME_ID not set")
    def test_fee_breakdown_with_live_data(self, sdk_readonly):
        round_info = sdk_readonly.get_round(KNOWN_GAME_ID, KNOWN_ROUND_ID)
        game_info = sdk_readonly.get_game(KNOWN_GAME_ID)
        yield_val = sdk_readonly.get_projected_yield(KNOWN_GAME_ID, KNOWN_ROUND_ID)

        fb = YieldPlayContract.calculate_fee_breakdown(
            total_deposit_gross=round_info.total_deposit,
            deposit_fee_bps=round_info.deposit_fee_bps,
            dev_fee_bps=game_info.dev_fee_bps,
            vault_yield=yield_val,
        )

        assert isinstance(fb, FeeBreakdown)
        # Conservation invariant
        assert fb.deposit_fee_collected + fb.net_deposits == round_info.total_deposit
        assert fb.total_prize_pool == fb.yield_prize + fb.deposit_fee_collected


@pytest.mark.integration
@pytest.mark.skipif(not _has_private_key, reason="PRIVATE_KEY not set in .env")
class TestWriteIntegration:
    """
    End-to-end write tests on Sepolia.

    WARNING: These send real transactions and cost gas.
    Each test is independent — game/round created fresh.
    """

    def _fresh_game(self, sdk: YieldPlayContract) -> tuple[str, str]:
        """Create a unique game and return (game_id, game_name)."""
        name = f"pytest-{int(time.time())}"
        game_id, tx = sdk.create_game(
            game_name=name,
            dev_fee_bps=500,  # 5% — valid
            treasury=sdk.signer_address,
        )
        assert tx.succeeded
        return game_id, name

    def _fresh_round(self, sdk: YieldPlayContract, game_id: str) -> int:
        """Create a round open for 1 hour and return round_id."""
        now = int(time.time())
        round_id, tx = sdk.create_round(
            game_id=game_id,
            start_ts=now,
            end_ts=now + 3600,
            lock_time=3600,
            deposit_fee_bps=100,  # 1%
            payment_token=TOKEN_ADDRESS,
        )
        assert tx.succeeded
        return round_id

    def test_create_game_basic(self, sdk_signer):
        game_id, name = self._fresh_game(sdk_signer)
        assert game_id.startswith("0x") and len(game_id) == 66

        # Verify on-chain
        game = sdk_signer.get_game(game_id)
        assert game.game_name == name
        assert game.dev_fee_bps == 500
        assert game.owner.lower() == sdk_signer.signer_address.lower()
        assert game.initialized is True

    def test_create_game_computes_correct_id(self, sdk_signer):
        """create_game's returned game_id must match calculateGameId."""
        name = f"id-check-{int(time.time())}"
        game_id, _ = sdk_signer.create_game(
            game_name=name,
            dev_fee_bps=100,
            treasury=sdk_signer.signer_address,
        )
        expected_id = sdk_signer.calculate_game_id(sdk_signer.signer_address, name)
        assert game_id == expected_id

    def test_create_game_invalid_dev_fee_raises(self, sdk_signer):
        """dev_fee_bps > 5000 should revert with InvalidDevFeeBps."""
        with pytest.raises(InvalidDevFeeBpsError):
            sdk_signer.create_game(
                game_name=f"bad-fee-{int(time.time())}",
                dev_fee_bps=9_999,  # too high
                treasury=sdk_signer.signer_address,
            )

    def test_create_game_duplicate_raises(self, sdk_signer):
        """Creating a game with the same name twice should raise GameAlreadyExistsError."""
        name = f"dup-{int(time.time())}"
        sdk_signer.create_game(name, 500, sdk_signer.signer_address)
        with pytest.raises(GameAlreadyExistsError):
            sdk_signer.create_game(name, 500, sdk_signer.signer_address)

    def test_create_round_basic(self, sdk_signer):
        game_id, _ = self._fresh_game(sdk_signer)
        round_id = self._fresh_round(sdk_signer, game_id)
        assert isinstance(round_id, int)
        assert round_id >= 0

        # Verify on-chain
        info = sdk_signer.get_round(game_id, round_id)
        assert info.initialized is True
        assert info.deposit_fee_bps == 100
        assert info.payment_token.lower() == TOKEN_ADDRESS.lower()

    def test_create_round_increments_counter(self, sdk_signer):
        game_id, _ = self._fresh_game(sdk_signer)
        r0 = self._fresh_round(sdk_signer, game_id)
        r1 = self._fresh_round(sdk_signer, game_id)
        assert r1 == r0 + 1

    def test_deposit_and_verify(self, sdk_signer):
        game_id, _ = self._fresh_game(sdk_signer)
        round_id = self._fresh_round(sdk_signer, game_id)
        amount = 1_000_000  # 1 token (assuming 6 decimals)

        # Check balance first
        balance = sdk_signer.get_token_balance(TOKEN_ADDRESS, sdk_signer.signer_address)
        if balance < amount:
            pytest.skip(f"Insufficient token balance: {balance} < {amount}")

        tx = sdk_signer.deposit(game_id, round_id, amount)
        assert tx.succeeded

        # Verify deposit recorded
        info = sdk_signer.get_user_deposit(game_id, round_id, sdk_signer.signer_address)
        assert info.exists is True
        assert info.deposit_amount > 0
        assert info.is_claimed is False

    def test_approve_token(self, sdk_signer):
        tx = sdk_signer.approve_token(TOKEN_ADDRESS, 0)  # approve 0 = reset
        assert tx.succeeded

        allowance = sdk_signer.get_token_allowance(
            TOKEN_ADDRESS, sdk_signer.signer_address
        )
        assert allowance == 0

    def test_deposit_to_vault_fails_before_lock(self, sdk_signer):
        """depositToVault should fail if round hasn't ended yet."""
        game_id, _ = self._fresh_game(sdk_signer)
        round_id = self._fresh_round(sdk_signer, game_id)  # round ends in 1 hour

        with pytest.raises(Exception):  # RoundNotEnded or similar
            sdk_signer.deposit_to_vault(game_id, round_id)

    def test_transaction_result_fields(self, sdk_signer):
        game_id, _ = self._fresh_game(sdk_signer)
        _, tx = sdk_signer.create_game(
            f"tx-fields-{int(time.time())}", 100, sdk_signer.signer_address
        )
        assert tx.tx_hash.startswith("0x")
        assert tx.block_number is not None and tx.block_number > 0
        assert tx.gas_used is not None and tx.gas_used > 0
        assert tx.status == 1
        assert tx.succeeded is True


# ── Utility ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick smoke test without pytest
    print("Running smoke tests...")

    # Test 1: offline game_id calculation
    from eth_abi.packed import encode_packed

    owner = "0xf971eEFd58b0831C9868A1a25A49D7EfD279D9c5"
    packed = encode_packed(["address", "string"], [owner, "smoke"])
    gid = "0x" + Web3.keccak(packed).hex()
    assert gid.startswith("0x") and len(gid) == 66
    print(f"  calculate_game_id: {gid} ✓")

    # Test 2: fee breakdown
    fb = YieldPlayContract.calculate_fee_breakdown(
        total_deposit_gross=10_000_000,
        deposit_fee_bps=200,
        dev_fee_bps=500,
        vault_yield=500_000,
    )
    assert fb.deposit_fee_collected + fb.net_deposits == 10_000_000
    print(f"  fee breakdown: prize_pool={fb.total_prize_pool} ✓")

    # Test 3: exception mapping
    exc = map_revert_reason("ContractCustomError: InvalidDevFeeBps")
    assert isinstance(exc, InvalidDevFeeBpsError)
    print(f"  map_revert_reason: {type(exc).__name__} ✓")

    print("Smoke tests passed!")
