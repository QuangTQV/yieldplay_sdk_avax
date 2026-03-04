# YieldPlay Python SDK

No-loss prize pool protocol SDK — Python, FastAPI, PostgreSQL, on-chain event indexer.

---

## Yêu cầu

| Công cụ | Phiên bản |
|---|---|
| Python | 3.11+ |
| PostgreSQL | 14+ |
| Docker + Compose | (tuỳ chọn, dễ nhất) |

---

## Cách 1 — Docker Compose (khuyến nghị)

Cách nhanh nhất, không cần cài PostgreSQL thủ công.

```bash
# 1. Giải nén và vào thư mục
unzip yieldplay-sdk.zip
cd yieldplay-sdk

# 2. Tạo file .env
cp .env.example .env
```

Mở `.env`, điền `PRIVATE_KEY` (bắt buộc để gọi write transactions):

```env
PRIVATE_KEY=0xabc123...   # private key ví Sepolia của bạn
```

```bash
# 3. Chạy
docker compose up --build
```

API sẽ chạy tại **http://localhost:8000**  
Swagger UI tại **http://localhost:8000/docs**

---

## Cách 2 — Chạy thủ công (không Docker)

### Bước 1 — Cài Python dependencies

```bash
cd yieldplay-sdk

# Tạo virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# Cài dependencies
pip install -r requirements.txt
```

### Bước 2 — Chuẩn bị PostgreSQL

Cài PostgreSQL nếu chưa có:
```bash
# Ubuntu / Debian
sudo apt install postgresql

# macOS (Homebrew)
brew install postgresql@16 && brew services start postgresql@16
```

Tạo database:
```bash
psql -U postgres -c "CREATE USER yieldplay WITH PASSWORD 'password';"
psql -U postgres -c "CREATE DATABASE yieldplay OWNER yieldplay;"
```

### Bước 3 — Cấu hình .env

```bash
cp .env.example .env
```

Nội dung `.env`:

```env
# ── Chain ─────────────────────────────────────────────────────────────────
YIELDPLAY_ADDRESS=0x02AA158dc37f4E1128CeE3E69e9E59920E799F90
RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
PRIVATE_KEY=0xabc123...          # private key ví Sepolia (bỏ trống = read-only)

# ── Database ───────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://yieldplay:password@localhost:5432/yieldplay
DATABASE_URL_SYNC=postgresql+psycopg2://yieldplay:password@localhost:5432/yieldplay

# ── Indexer ────────────────────────────────────────────────────────────────
INDEXER_POLL_INTERVAL=12         # giây giữa mỗi lần poll (= 1 Ethereum block)
INDEXER_START_BLOCK=0            # block bắt đầu index (0 = từ đầu)
INDEXER_CONFIRMATIONS=2          # chờ N block trước khi xử lý

# ── API ────────────────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
```

### Bước 4 — Migrate database

```bash
# Tạo migration đầu tiên
alembic revision --autogenerate -m "initial"

# Chạy migration
alembic upgrade head
```

> **Lưu ý:** Nếu bỏ qua bước Alembic, API vẫn tự tạo tables khi khởi động
> (`create_all_tables()` được gọi trong `on_startup`). Alembic chỉ cần thiết
> khi bạn muốn quản lý schema changes sau này.

### Bước 5 — Chạy API

```bash
python main.py
```

Hoặc dùng uvicorn với hot-reload khi develop:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## Kiểm tra API đang chạy

```bash
# Health check
curl http://localhost:8000/health

# Protocol info
curl http://localhost:8000/api/v1/protocol

# Swagger UI
open http://localhost:8000/docs
```

---

## Chạy example script (Layer 1 trực tiếp)

Không cần API, gọi contract trực tiếp qua Python:

```bash
# Đảm bảo .env đã có PRIVATE_KEY
python examples/full_lifecycle.py
```

---

## Cấu trúc project

```
yieldplay-sdk/
├── main.py                          ← Entry point
├── .env.example                     ← Mẫu cấu hình
├── docker-compose.yml               ← PostgreSQL + API
├── Dockerfile
├── alembic/                         ← DB migrations
│   └── env.py
├── yieldplay/
│   ├── contract.py                  ← LAYER 1: web3 contract client
│   ├── types.py                     ← Pydantic models & enums
│   ├── abi.py                       ← Contract ABI
│   ├── exceptions.py                ← Exception hierarchy
│   ├── db/
│   │   ├── base.py                  ← AsyncEngine, session factory
│   │   └── models.py                ← 7 SQLAlchemy ORM tables
│   ├── repositories/
│   │   ├── deposit_repo.py          ← Deposit & Claim queries
│   │   └── round_repo.py            ← Round, Game, WinnerEvent queries
│   ├── indexer/
│   │   └── event_indexer.py         ← Background event indexer
│   └── api/                         ← LAYER 2: FastAPI
│       ├── app.py                   ← App factory + indexer startup
│       ├── deps.py                  ← Dependency injection
│       ├── services/
│       │   ├── user_service.py      ← User business logic (DB-first)
│       │   └── round_service.py     ← Round business logic (DB-first)
│       └── routes/
│           ├── games.py             ← /api/v1/games/*
│           ├── rounds.py            ← /api/v1/rounds/*
│           └── users.py             ← /api/v1/users/*
└── examples/
    └── full_lifecycle.py            ← End-to-end example
```

---

## Luồng hoạt động

```
Ethereum chain
     │  events (Deposit, Claim, WinnerChosen, ...)
     ▼
EventIndexer (background task, poll mỗi 12s)
     │  upsert
     ▼
PostgreSQL
     │  DB-first reads (portfolio, participants, winners)
     ▼
Services (UserService, RoundService)
     │  contract fallback cho safety-critical fields
     ▼
FastAPI routes  →  HTTP responses
```

---

## Các endpoints quan trọng

### Chỉ cần đọc (không cần PRIVATE_KEY)

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/v1/games/{game_id}/rounds/{round_id}/dashboard` | Toàn bộ thông tin round |
| GET | `/api/v1/games/{game_id}/rounds/{round_id}/participants` | Danh sách depositors (DB) |
| GET | `/api/v1/users/{addr}/portfolio` | Lịch sử tham gia của user (DB) |
| GET | `/api/v1/users/{addr}/rounds/{game}/{round}/summary` | Trạng thái user trong 1 round |
| GET | `/api/v1/users/{addr}/eligibility/deposit/{game}/{round}?amount_wei=N` | Pre-check deposit |

### Cần PRIVATE_KEY

| Method | Endpoint | Mô tả |
|---|---|---|
| POST | `/api/v1/users/deposit` | Gửi token vào round |
| POST | `/api/v1/users/claim` | Claim principal + prize |
| POST | `/api/v1/games` | Tạo game mới |
| POST | `/api/v1/rounds/settle-sequence` | withdraw + settlement 1 lần |
| POST | `/api/v1/rounds/distribute-and-finalize` | Chọn winners + finalize |
