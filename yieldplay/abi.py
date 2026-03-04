"""
yieldplay/abi.py
────────────────
ABI definitions for YieldPlay contract and ERC-20 token.
Structs are represented as ABI tuples with named components.
"""

from __future__ import annotations

from typing import Any

# ── YieldPlay main contract ABI ───────────────────────────────────────────

YIELD_PLAY_ABI: list[dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "address", "name": "_protocolTreasury", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor",
    },
    {"inputs": [], "name": "AlreadyClaimed", "type": "error"},
    {"inputs": [], "name": "EnforcedPause", "type": "error"},
    {"inputs": [], "name": "ExpectedPause", "type": "error"},
    {"inputs": [], "name": "FundsAlreadyWithdrawn", "type": "error"},
    {"inputs": [], "name": "FundsNotDeployed", "type": "error"},
    {"inputs": [], "name": "FundsNotWithdrawn", "type": "error"},
    {"inputs": [], "name": "GameAlreadyExists", "type": "error"},
    {"inputs": [], "name": "GameNotFound", "type": "error"},
    {"inputs": [], "name": "InsufficientPrizePool", "type": "error"},
    {"inputs": [], "name": "InvalidAmount", "type": "error"},
    {"inputs": [], "name": "InvalidDevFeeBps", "type": "error"},
    {"inputs": [], "name": "InvalidPaymentToken", "type": "error"},
    {"inputs": [], "name": "InvalidRoundTime", "type": "error"},
    {"inputs": [], "name": "NoDepositsFound", "type": "error"},
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "OwnableInvalidOwner",
        "type": "error",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "OwnableUnauthorizedAccount",
        "type": "error",
    },
    {"inputs": [], "name": "ReentrancyGuardReentrantCall", "type": "error"},
    {"inputs": [], "name": "RoundAlreadySettled", "type": "error"},
    {"inputs": [], "name": "RoundNotActive", "type": "error"},
    {"inputs": [], "name": "RoundNotCompleted", "type": "error"},
    {"inputs": [], "name": "RoundNotEnded", "type": "error"},
    {"inputs": [], "name": "RoundNotFound", "type": "error"},
    {"inputs": [], "name": "RoundNotSettled", "type": "error"},
    {
        "inputs": [{"internalType": "address", "name": "token", "type": "address"}],
        "name": "SafeERC20FailedOperation",
        "type": "error",
    },
    {"inputs": [], "name": "StrategyNotSet", "type": "error"},
    {"inputs": [], "name": "Unauthorized", "type": "error"},
    {"inputs": [], "name": "ZeroAddress", "type": "error"},
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "bytes32",
                "name": "gameId",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "uint256",
                "name": "roundId",
                "type": "uint256",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "user",
                "type": "address",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "principal",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "prize",
                "type": "uint256",
            },
        ],
        "name": "Claimed",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "bytes32",
                "name": "gameId",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "uint256",
                "name": "roundId",
                "type": "uint256",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "user",
                "type": "address",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "depositFee",
                "type": "uint256",
            },
        ],
        "name": "Deposited",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "bytes32",
                "name": "gameId",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "uint256",
                "name": "roundId",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "shares",
                "type": "uint256",
            },
        ],
        "name": "FundsDeployed",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "bytes32",
                "name": "gameId",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "uint256",
                "name": "roundId",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "principal",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "yield",
                "type": "uint256",
            },
        ],
        "name": "FundsWithdrawn",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "bytes32",
                "name": "gameId",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "owner",
                "type": "address",
            },
            {
                "indexed": False,
                "internalType": "string",
                "name": "gameName",
                "type": "string",
            },
            {
                "indexed": False,
                "internalType": "uint16",
                "name": "devFeeBps",
                "type": "uint16",
            },
        ],
        "name": "GameCreated",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "address",
                "name": "previousOwner",
                "type": "address",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "newOwner",
                "type": "address",
            },
        ],
        "name": "OwnershipTransferred",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": False,
                "internalType": "address",
                "name": "account",
                "type": "address",
            }
        ],
        "name": "Paused",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "address",
                "name": "newTreasury",
                "type": "address",
            }
        ],
        "name": "ProtocolTreasuryUpdated",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "bytes32",
                "name": "gameId",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "uint256",
                "name": "roundId",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint64",
                "name": "startTs",
                "type": "uint64",
            },
            {
                "indexed": False,
                "internalType": "uint64",
                "name": "endTs",
                "type": "uint64",
            },
            {
                "indexed": False,
                "internalType": "uint64",
                "name": "lockTime",
                "type": "uint64",
            },
            {
                "indexed": False,
                "internalType": "uint16",
                "name": "depositFeeBps",
                "type": "uint16",
            },
            {
                "indexed": False,
                "internalType": "address",
                "name": "paymentToken",
                "type": "address",
            },
            {
                "indexed": False,
                "internalType": "address",
                "name": "vault",
                "type": "address",
            },
        ],
        "name": "RoundCreated",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "bytes32",
                "name": "gameId",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "uint256",
                "name": "roundId",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "totalYield",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "performanceFee",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "devFee",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "prizePool",
                "type": "uint256",
            },
        ],
        "name": "RoundSettled",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": False,
                "internalType": "address",
                "name": "account",
                "type": "address",
            }
        ],
        "name": "Unpaused",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "address",
                "name": "token",
                "type": "address",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "vault",
                "type": "address",
            },
        ],
        "name": "VaultUpdated",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "bytes32",
                "name": "gameId",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "uint256",
                "name": "roundId",
                "type": "uint256",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "winner",
                "type": "address",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256",
            },
        ],
        "name": "WinnerChosen",
        "type": "event",
    },
    {
        "inputs": [],
        "name": "BPS_DENOMINATOR",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "PERFORMANCE_FEE_BPS",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "string", "name": "gameName", "type": "string"},
        ],
        "name": "calculateGameId",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "pure",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
            {"internalType": "address", "name": "winner", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "chooseWinner",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
        ],
        "name": "claim",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "string", "name": "gameName", "type": "string"},
            {"internalType": "uint16", "name": "devFeeBps", "type": "uint16"},
            {"internalType": "address", "name": "treasury", "type": "address"},
        ],
        "name": "createGame",
        "outputs": [{"internalType": "bytes32", "name": "gameId", "type": "bytes32"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint64", "name": "startTs", "type": "uint64"},
            {"internalType": "uint64", "name": "endTs", "type": "uint64"},
            {"internalType": "uint64", "name": "lockTime", "type": "uint64"},
            {"internalType": "uint16", "name": "depositFeeBps", "type": "uint16"},
            {"internalType": "address", "name": "paymentToken", "type": "address"},
        ],
        "name": "createRound",
        "outputs": [{"internalType": "uint256", "name": "roundId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "", "type": "bytes32"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
        ],
        "name": "deployedAmounts",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "", "type": "bytes32"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
        ],
        "name": "deployedShares",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
        ],
        "name": "depositToVault",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
        ],
        "name": "finalizeRound",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "name": "games",
        "outputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "string", "name": "gameName", "type": "string"},
            {"internalType": "uint16", "name": "devFeeBps", "type": "uint16"},
            {"internalType": "address", "name": "treasury", "type": "address"},
            {"internalType": "uint256", "name": "roundCounter", "type": "uint256"},
            {"internalType": "bool", "name": "initialized", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
        ],
        "name": "getCurrentStatus",
        "outputs": [{"internalType": "enum RoundStatus", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "gameId", "type": "bytes32"}],
        "name": "getGame",
        "outputs": [
            {
                "components": [
                    {"internalType": "address", "name": "owner", "type": "address"},
                    {"internalType": "string", "name": "gameName", "type": "string"},
                    {"internalType": "uint16", "name": "devFeeBps", "type": "uint16"},
                    {"internalType": "address", "name": "treasury", "type": "address"},
                    {
                        "internalType": "uint256",
                        "name": "roundCounter",
                        "type": "uint256",
                    },
                    {"internalType": "bool", "name": "initialized", "type": "bool"},
                ],
                "internalType": "struct Game",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
        ],
        "name": "getRound",
        "outputs": [
            {
                "components": [
                    {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
                    {"internalType": "uint256", "name": "roundId", "type": "uint256"},
                    {
                        "internalType": "uint256",
                        "name": "totalDeposit",
                        "type": "uint256",
                    },
                    {
                        "internalType": "uint256",
                        "name": "bonusPrizePool",
                        "type": "uint256",
                    },
                    {"internalType": "uint256", "name": "devFee", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalWin", "type": "uint256"},
                    {
                        "internalType": "uint256",
                        "name": "yieldAmount",
                        "type": "uint256",
                    },
                    {
                        "internalType": "address",
                        "name": "paymentToken",
                        "type": "address",
                    },
                    {"internalType": "address", "name": "vault", "type": "address"},
                    {
                        "internalType": "uint16",
                        "name": "depositFeeBps",
                        "type": "uint16",
                    },
                    {"internalType": "uint64", "name": "startTs", "type": "uint64"},
                    {"internalType": "uint64", "name": "endTs", "type": "uint64"},
                    {"internalType": "uint64", "name": "lockTime", "type": "uint64"},
                    {"internalType": "bool", "name": "initialized", "type": "bool"},
                    {"internalType": "bool", "name": "isSettled", "type": "bool"},
                    {
                        "internalType": "enum RoundStatus",
                        "name": "status",
                        "type": "uint8",
                    },
                    {"internalType": "bool", "name": "isWithdrawn", "type": "bool"},
                ],
                "internalType": "struct Round",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
            {"internalType": "address", "name": "user", "type": "address"},
        ],
        "name": "getUserDeposit",
        "outputs": [
            {
                "components": [
                    {
                        "internalType": "uint256",
                        "name": "depositAmount",
                        "type": "uint256",
                    },
                    {
                        "internalType": "uint256",
                        "name": "amountToClaim",
                        "type": "uint256",
                    },
                    {"internalType": "bool", "name": "isClaimed", "type": "bool"},
                    {"internalType": "bool", "name": "exists", "type": "bool"},
                ],
                "internalType": "struct UserDeposit",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "pause",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "paused",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "protocolTreasury",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "renounceOwnership",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "", "type": "bytes32"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
        ],
        "name": "rounds",
        "outputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
            {"internalType": "uint256", "name": "totalDeposit", "type": "uint256"},
            {"internalType": "uint256", "name": "bonusPrizePool", "type": "uint256"},
            {"internalType": "uint256", "name": "devFee", "type": "uint256"},
            {"internalType": "uint256", "name": "totalWin", "type": "uint256"},
            {"internalType": "uint256", "name": "yieldAmount", "type": "uint256"},
            {"internalType": "address", "name": "paymentToken", "type": "address"},
            {"internalType": "address", "name": "vault", "type": "address"},
            {"internalType": "uint16", "name": "depositFeeBps", "type": "uint16"},
            {"internalType": "uint64", "name": "startTs", "type": "uint64"},
            {"internalType": "uint64", "name": "endTs", "type": "uint64"},
            {"internalType": "uint64", "name": "lockTime", "type": "uint64"},
            {"internalType": "bool", "name": "initialized", "type": "bool"},
            {"internalType": "bool", "name": "isSettled", "type": "bool"},
            {"internalType": "enum RoundStatus", "name": "status", "type": "uint8"},
            {"internalType": "bool", "name": "isWithdrawn", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "newTreasury", "type": "address"}
        ],
        "name": "setProtocolTreasury",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "vault", "type": "address"},
        ],
        "name": "setVault",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
        ],
        "name": "settlement",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "newOwner", "type": "address"}],
        "name": "transferOwnership",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "unpause",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
        ],
        "name": "updateRoundStatus",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "", "type": "bytes32"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
            {"internalType": "address", "name": "", "type": "address"},
        ],
        "name": "userDeposits",
        "outputs": [
            {"internalType": "uint256", "name": "depositAmount", "type": "uint256"},
            {"internalType": "uint256", "name": "amountToClaim", "type": "uint256"},
            {"internalType": "bool", "name": "isClaimed", "type": "bool"},
            {"internalType": "bool", "name": "exists", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "vaults",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "gameId", "type": "bytes32"},
            {"internalType": "uint256", "name": "roundId", "type": "uint256"},
        ],
        "name": "withdrawFromVault",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ── Minimal ERC-20 ABI (only what YieldPlay SDK needs) ────────────────────

ERC20_ABI: list[dict[str, Any]] = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
    {
        "name": "symbol",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
]
