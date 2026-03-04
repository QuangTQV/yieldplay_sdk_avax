"""
yieldplay/abi.py
────────────────
ABI lấy trực tiếp từ artifact Hardhat – YieldPlay.sol.
"""
from __future__ import annotations
from typing import Any

YIELD_PLAY_ABI: list[dict[str, Any]] = [
    # ── Constants ────────────────────────────────────────────────────────
    {"name": "BPS_DENOMINATOR", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "PERFORMANCE_FEE_BPS", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint256"}]},

    # ── Pure / view ──────────────────────────────────────────────────────
    {"name": "calculateGameId", "type": "function", "stateMutability": "pure",
     "inputs": [{"name": "owner", "type": "address"}, {"name": "gameName", "type": "string"}],
     "outputs": [{"name": "", "type": "bytes32"}]},

    {"name": "getCurrentStatus", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "gameId", "type": "bytes32"}, {"name": "roundId", "type": "uint256"}],
     "outputs": [{"name": "", "type": "uint8"}]},

    {"name": "getGame", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "gameId", "type": "bytes32"}],
     "outputs": [{"name": "", "type": "tuple", "components": [
         {"name": "owner",        "type": "address"},
         {"name": "gameName",     "type": "string"},
         {"name": "devFeeBps",    "type": "uint16"},   # uint16 not uint256
         {"name": "treasury",     "type": "address"},
         {"name": "roundCounter", "type": "uint256"},
         {"name": "initialized",  "type": "bool"},
     ]}]},

    {"name": "getRound", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "gameId", "type": "bytes32"}, {"name": "roundId", "type": "uint256"}],
     "outputs": [{"name": "", "type": "tuple", "components": [
         {"name": "gameId",        "type": "bytes32"},
         {"name": "roundId",       "type": "uint256"},
         {"name": "totalDeposit",  "type": "uint256"},
         {"name": "bonusPrizePool","type": "uint256"},
         {"name": "devFee",        "type": "uint256"},
         {"name": "totalWin",      "type": "uint256"},
         {"name": "yieldAmount",   "type": "uint256"},
         {"name": "paymentToken",  "type": "address"},
         {"name": "vault",         "type": "address"},
         {"name": "depositFeeBps", "type": "uint16"},  # uint16
         {"name": "startTs",       "type": "uint64"},  # uint64
         {"name": "endTs",         "type": "uint64"},  # uint64
         {"name": "lockTime",      "type": "uint64"},  # uint64
         {"name": "initialized",   "type": "bool"},
         {"name": "isSettled",     "type": "bool"},
         {"name": "status",        "type": "uint8"},
         {"name": "isWithdrawn",   "type": "bool"},
     ]}]},

    {"name": "getUserDeposit", "type": "function", "stateMutability": "view",
     "inputs": [
         {"name": "gameId", "type": "bytes32"},
         {"name": "roundId", "type": "uint256"},
         {"name": "user", "type": "address"},
     ],
     "outputs": [{"name": "", "type": "tuple", "components": [
         {"name": "depositAmount", "type": "uint256"},
         {"name": "amountToClaim", "type": "uint256"},
         {"name": "isClaimed",     "type": "bool"},
         {"name": "exists",        "type": "bool"},
     ]}]},

    # ── Public state variables (accessed as functions) ───────────────────
    # NOTE: these are public mappings/variables — not getter functions we invented
    {"name": "vaults", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "address"}],
     "outputs": [{"name": "", "type": "address"}]},

    {"name": "protocolTreasury", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},

    {"name": "deployedAmounts", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "bytes32"}, {"name": "", "type": "uint256"}],
     "outputs": [{"name": "", "type": "uint256"}]},

    {"name": "deployedShares", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "bytes32"}, {"name": "", "type": "uint256"}],
     "outputs": [{"name": "", "type": "uint256"}]},

    {"name": "paused", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "bool"}]},

    {"name": "owner", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},

    # ── Write: user ──────────────────────────────────────────────────────
    {"name": "deposit", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "gameId", "type": "bytes32"},
         {"name": "roundId", "type": "uint256"},
         {"name": "amount", "type": "uint256"},
     ], "outputs": []},

    {"name": "claim", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "gameId", "type": "bytes32"},
         {"name": "roundId", "type": "uint256"},
     ], "outputs": []},

    # ── Write: game management ───────────────────────────────────────────
    # createGame returns bytes32 gameId DIRECTLY (not via event)
    {"name": "createGame", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "gameName",  "type": "string"},
         {"name": "devFeeBps", "type": "uint16"},   # uint16
         {"name": "treasury",  "type": "address"},
     ],
     "outputs": [{"name": "gameId", "type": "bytes32"}]},

    # createRound returns uint256 roundId DIRECTLY
    {"name": "createRound", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "gameId",        "type": "bytes32"},
         {"name": "startTs",       "type": "uint64"},   # uint64
         {"name": "endTs",         "type": "uint64"},   # uint64
         {"name": "lockTime",      "type": "uint64"},   # uint64
         {"name": "depositFeeBps", "type": "uint16"},   # uint16
         {"name": "paymentToken",  "type": "address"},
     ],
     "outputs": [{"name": "roundId", "type": "uint256"}]},

    # ── Write: vault lifecycle ───────────────────────────────────────────
    {"name": "depositToVault", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "gameId", "type": "bytes32"}, {"name": "roundId", "type": "uint256"}],
     "outputs": []},

    {"name": "withdrawFromVault", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "gameId", "type": "bytes32"}, {"name": "roundId", "type": "uint256"}],
     "outputs": []},

    {"name": "settlement", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "gameId", "type": "bytes32"}, {"name": "roundId", "type": "uint256"}],
     "outputs": []},

    {"name": "chooseWinner", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "gameId",  "type": "bytes32"},
         {"name": "roundId", "type": "uint256"},
         {"name": "winner",  "type": "address"},
         {"name": "amount",  "type": "uint256"},
     ], "outputs": []},

    {"name": "finalizeRound", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "gameId", "type": "bytes32"}, {"name": "roundId", "type": "uint256"}],
     "outputs": []},

    {"name": "updateRoundStatus", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "gameId", "type": "bytes32"}, {"name": "roundId", "type": "uint256"}],
     "outputs": []},

    # ── Admin ────────────────────────────────────────────────────────────
    {"name": "setVault", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "token", "type": "address"}, {"name": "vault", "type": "address"}],
     "outputs": []},

    {"name": "setProtocolTreasury", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "newTreasury", "type": "address"}],
     "outputs": []},

    {"name": "pause",   "type": "function", "stateMutability": "nonpayable",
     "inputs": [], "outputs": []},
    {"name": "unpause", "type": "function", "stateMutability": "nonpayable",
     "inputs": [], "outputs": []},

    {"name": "transferOwnership", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "newOwner", "type": "address"}], "outputs": []},
    {"name": "renounceOwnership", "type": "function", "stateMutability": "nonpayable",
     "inputs": [], "outputs": []},
]

# ── Events ABI (used by indexer only) ─────────────────────────────────────
# Taken verbatim from the artifact — do not edit manually.

YIELD_PLAY_EVENTS_ABI: list[dict[str, Any]] = [
    {
        "name": "GameCreated", "type": "event", "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "gameId",    "type": "bytes32"},
            {"indexed": True,  "name": "owner",     "type": "address"},
            {"indexed": False, "name": "gameName",  "type": "string"},
            # NOTE: no treasury in this event — fetch from getGame() if needed
            {"indexed": False, "name": "devFeeBps", "type": "uint16"},
        ],
    },
    {
        "name": "RoundCreated", "type": "event", "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "gameId",        "type": "bytes32"},
            {"indexed": True,  "name": "roundId",       "type": "uint256"},
            {"indexed": False, "name": "startTs",       "type": "uint64"},
            {"indexed": False, "name": "endTs",         "type": "uint64"},
            {"indexed": False, "name": "lockTime",      "type": "uint64"},
            {"indexed": False, "name": "depositFeeBps", "type": "uint16"},
            {"indexed": False, "name": "paymentToken",  "type": "address"},
            {"indexed": False, "name": "vault",         "type": "address"},
        ],
    },
    {
        # 'amount' = gross deposit before fee (NOT split into gross/net)
        "name": "Deposited", "type": "event", "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "gameId",     "type": "bytes32"},
            {"indexed": True,  "name": "roundId",    "type": "uint256"},
            {"indexed": True,  "name": "user",       "type": "address"},
            {"indexed": False, "name": "amount",     "type": "uint256"},
            {"indexed": False, "name": "depositFee", "type": "uint256"},
        ],
    },
    {
        "name": "Claimed", "type": "event", "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "gameId",    "type": "bytes32"},
            {"indexed": True,  "name": "roundId",   "type": "uint256"},
            {"indexed": True,  "name": "user",      "type": "address"},
            {"indexed": False, "name": "principal", "type": "uint256"},
            {"indexed": False, "name": "prize",     "type": "uint256"},
        ],
    },
    {
        "name": "WinnerChosen", "type": "event", "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "gameId",  "type": "bytes32"},
            {"indexed": True,  "name": "roundId", "type": "uint256"},
            {"indexed": True,  "name": "winner",  "type": "address"},
            {"indexed": False, "name": "amount",  "type": "uint256"},
        ],
    },
    {
        # Named RoundSettled in contract (not Settled)
        "name": "RoundSettled", "type": "event", "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "gameId",         "type": "bytes32"},
            {"indexed": True,  "name": "roundId",        "type": "uint256"},
            {"indexed": False, "name": "totalYield",     "type": "uint256"},
            {"indexed": False, "name": "performanceFee", "type": "uint256"},
            {"indexed": False, "name": "devFee",         "type": "uint256"},
            {"indexed": False, "name": "prizePool",      "type": "uint256"},
        ],
    },
    {
        "name": "FundsDeployed", "type": "event", "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "gameId",  "type": "bytes32"},
            {"indexed": True,  "name": "roundId", "type": "uint256"},
            {"indexed": False, "name": "amount",  "type": "uint256"},
            {"indexed": False, "name": "shares",  "type": "uint256"},
        ],
    },
    {
        "name": "FundsWithdrawn", "type": "event", "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "gameId",    "type": "bytes32"},
            {"indexed": True,  "name": "roundId",   "type": "uint256"},
            {"indexed": False, "name": "principal", "type": "uint256"},
            {"indexed": False, "name": "yield",     "type": "uint256"},
        ],
    },
]

# ── ERC-20 minimal ─────────────────────────────────────────────────────────

ERC20_ABI: list[dict[str, Any]] = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "allowance", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "approve", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
    {"name": "symbol", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "string"}]},
]

# ── ERC-4626 (for projected yield) ────────────────────────────────────────

ERC4626_ABI: list[dict[str, Any]] = [
    {"name": "previewRedeem", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "shares", "type": "uint256"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "convertToAssets", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "shares", "type": "uint256"}],
     "outputs": [{"name": "", "type": "uint256"}]},
]
