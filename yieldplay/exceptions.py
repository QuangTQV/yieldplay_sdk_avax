"""
yieldplay/exceptions.py
───────────────────────
Custom exception hierarchy for YieldPlay SDK.
"""

from __future__ import annotations


class YieldPlayError(Exception):
    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return f"{self.message}: {self.details}" if self.details else self.message


# ── Contract / chain errors ────────────────────────────────────────────────


class ContractCallError(YieldPlayError):
    """Raised when a view call to the contract fails."""


class TransactionError(YieldPlayError):
    def __init__(self, message: str, tx_hash: str = "", details: str = "") -> None:
        super().__init__(message, details)
        self.tx_hash = tx_hash


class TransactionRevertedError(TransactionError):
    """Transaction mined but status=0."""


# ── Business errors ────────────────────────────────────────────────────────


class RoundNotActiveError(YieldPlayError):
    pass


class RoundNotInProgressError(YieldPlayError):
    pass


class RoundNotLockingError(YieldPlayError):
    pass


class RoundNotChoosingWinnersError(YieldPlayError):
    pass


class RoundNotDistributingError(YieldPlayError):
    pass


class AlreadyClaimedError(YieldPlayError):
    pass


class NoDepositFoundError(YieldPlayError):
    pass


class InvalidAmountError(YieldPlayError):
    pass


class InvalidDevFeeBpsError(YieldPlayError):
    pass


class InsufficientBalanceError(YieldPlayError):
    pass


class InsufficientAllowanceError(YieldPlayError):
    pass


class UnauthorizedError(YieldPlayError):
    pass


class ContractPausedError(YieldPlayError):
    pass


class GameAlreadyExistsError(YieldPlayError):
    pass


class GameNotFoundError(YieldPlayError):
    pass


class RoundNotFoundError(YieldPlayError):
    pass


class FundsNotDeployedError(YieldPlayError):
    pass


class FundsAlreadyWithdrawnError(YieldPlayError):
    pass


class InsufficientPrizePoolError(YieldPlayError):
    pass


# ── Config errors ─────────────────────────────────────────────────────────


class SignerNotConfiguredError(YieldPlayError):
    def __init__(self) -> None:
        super().__init__(
            "Signer not configured",
            "Provide a private_key in SDKConfig to enable write operations.",
        )


def map_revert_reason(error_message: str) -> YieldPlayError:
    """
    Convert a raw revert / custom-error string from web3.py into a typed
    YieldPlayError.

    web3.py v6 formats custom errors as:
      ContractCustomError: <ErrorName> [args...]
    or:
      execution reverted: <ErrorName>
    """
    # Normalise — strip web3 prefix noise
    raw = error_message
    msg = error_message.lower()

    # ── Custom error names (exact match first) ────────────────────────────
    # These come from web3.py as "ContractCustomError: ErrorName ..."
    custom_map = {
        "invaliddevfeebps": lambda: InvalidDevFeeBpsError(
            "dev_fee_bps is out of range (max 5000 = 50%)", raw
        ),
        "roundnotactive": lambda: RoundNotActiveError("Round is not active", raw),
        "roundnotcompleted": lambda: RoundNotChoosingWinnersError(
            "Round not completed", raw
        ),
        "roundnotended": lambda: RoundNotActiveError("Round has not ended yet", raw),
        "roundnotfound": lambda: RoundNotFoundError("Round not found", raw),
        "roundnotsettled": lambda: TransactionError(
            "Round not settled yet", details=raw
        ),
        "roundalreadysettled": lambda: TransactionError(
            "Round already settled", details=raw
        ),
        "gamealreadyexists": lambda: GameAlreadyExistsError("Game already exists", raw),
        "gamenotfound": lambda: GameNotFoundError("Game not found", raw),
        "alreadyclaimed": lambda: AlreadyClaimedError("Already claimed", raw),
        "nodeposits": lambda: NoDepositFoundError("No deposits found", raw),
        "nodepositsound": lambda: NoDepositFoundError("No deposits found", raw),
        "invalidamount": lambda: InvalidAmountError(
            "Invalid amount (must be > 0)", raw
        ),
        "invalidpaymenttoken": lambda: InvalidAmountError("Invalid payment token", raw),
        "invalidroundtime": lambda: InvalidAmountError(
            "Invalid round time parameters", raw
        ),
        "fundsnotdeployed": lambda: FundsNotDeployedError(
            "Funds not deployed to vault", raw
        ),
        "fundsalreadywithdrawn": lambda: FundsAlreadyWithdrawnError(
            "Funds already withdrawn", raw
        ),
        "fundsnotwithdrawn": lambda: TransactionError(
            "Funds not yet withdrawn", details=raw
        ),
        "insufficientprizepool": lambda: InsufficientPrizePoolError(
            "Insufficient prize pool", raw
        ),
        "unauthorized": lambda: UnauthorizedError("Caller not authorised", raw),
        "strategynotset": lambda: TransactionError(
            "Vault strategy not set", details=raw
        ),
        "enforcedpause": lambda: ContractPausedError("Contract is paused", raw),
        "zeroaddress": lambda: InvalidAmountError("Zero address not allowed", raw),
        "reentrancyguardreentrantcall": lambda: TransactionError(
            "Reentrancy detected", details=raw
        ),
    }

    for key, factory in custom_map.items():
        if key in msg:
            return factory()

    # ── Fallback fuzzy matches ────────────────────────────────────────────
    if "paused" in msg:
        return ContractPausedError("Contract is paused", raw)
    if "unauthorized" in msg or "not owner" in msg or "onlyowner" in msg:
        return UnauthorizedError("Caller not authorised", raw)
    if "insufficient" in msg:
        return InsufficientBalanceError("Insufficient balance", raw)

    return TransactionError("Transaction failed", details=raw)
