"""
yieldplay/exceptions.py
───────────────────────
Custom exception hierarchy for YieldPlay SDK.
"""

from __future__ import annotations


class YieldPlayError(Exception):
    """Base exception for all YieldPlay errors."""

    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


# ── Contract / chain errors ────────────────────────────────────────────────


class ContractCallError(YieldPlayError):
    """Raised when a view call to the contract fails."""


class TransactionError(YieldPlayError):
    """Raised when a state-changing transaction fails or reverts."""

    def __init__(self, message: str, tx_hash: str = "", details: str = "") -> None:
        super().__init__(message, details)
        self.tx_hash = tx_hash


class TransactionRevertedError(TransactionError):
    """Raised when a sent transaction is mined but has status=0."""


# ── Business / validation errors ──────────────────────────────────────────


class RoundNotActiveError(YieldPlayError):
    """Round is not in a state that accepts deposits."""


class RoundNotInProgressError(YieldPlayError):
    """Operation requires RoundStatus.IN_PROGRESS."""


class RoundNotLockingError(YieldPlayError):
    """Operation requires RoundStatus.LOCKING or later."""


class RoundNotChoosingWinnersError(YieldPlayError):
    """Operation requires RoundStatus.CHOOSING_WINNERS."""


class RoundNotDistributingError(YieldPlayError):
    """Operation requires RoundStatus.DISTRIBUTING_REWARDS."""


class AlreadyClaimedError(YieldPlayError):
    """User already claimed for this round."""


class NoDepositFoundError(YieldPlayError):
    """User has no deposit in this round."""


class InvalidAmountError(YieldPlayError):
    """Amount is zero or otherwise invalid."""


class InsufficientBalanceError(YieldPlayError):
    """Token balance is too low for the requested operation."""


class InsufficientAllowanceError(YieldPlayError):
    """Token allowance is too low; approve first."""


class UnauthorizedError(YieldPlayError):
    """Caller is not authorised to perform this action."""


# ── Config / SDK errors ───────────────────────────────────────────────────


class SignerNotConfiguredError(YieldPlayError):
    """Private key was not provided; write operations are unavailable."""

    def __init__(self) -> None:
        super().__init__(
            "Signer not configured",
            "Provide a private_key in SDKConfig to enable write operations.",
        )


class ContractPausedError(YieldPlayError):
    """The YieldPlay contract is currently paused."""


# ── Utility ───────────────────────────────────────────────────────────────


def map_revert_reason(error_message: str) -> YieldPlayError:
    """
    Convert a raw revert string / error message from web3
    into a typed YieldPlayError.
    """
    msg = error_message.lower()

    if "roundnotactive" in msg or "round not active" in msg:
        return RoundNotActiveError("Round is not currently active", error_message)
    if "invalidamount" in msg or "invalid amount" in msg:
        return InvalidAmountError("Invalid deposit amount", error_message)
    if "insufficient" in msg:
        return InsufficientBalanceError("Insufficient balance", error_message)
    if "notowner" in msg or "unauthorized" in msg or "onlyowner" in msg:
        return UnauthorizedError("Caller is not authorised", error_message)
    if "alreadyclaimed" in msg or "already claimed" in msg:
        return AlreadyClaimedError("Reward already claimed", error_message)
    if "paused" in msg:
        return ContractPausedError("Contract is paused", error_message)

    return TransactionError("Transaction failed", details=error_message)
