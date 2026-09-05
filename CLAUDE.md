# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Upasser** is an IoT-integrated access control and prepaid wallet system. It manages customers with prepaid wallets, NFC/QR credentials, and physical gate/turnstile access events — think toll booths or turnstile access with real-time balance deduction.

## Commands

### Running the Application

```bash
# Desarrollo — hot-reload, BD expuesta en :5432, /docs habilitado
docker-compose up

# Producción — fastapi run, BD sin puerto público, /docs deshabilitado
docker-compose -f docker-compose.prod.yml up -d

# FastAPI dev server solo (requiere BD local)
fastapi dev app/main.py
```

API docs disponibles en `http://localhost:8000/docs` (solo en ENVIRONMENT=local).

### Database Migrations

```bash
# Apply all migrations
alembic upgrade head

# Auto-generate migration from model changes
alembic revision --autogenerate -m "description"

# Rollback one step
alembic downgrade -1
```

## Architecture

### Multi-Tenant Organization Layer

Companies own branches. Users (with roles) belong to companies. RBAC is enforced via the `RoleChecker` dependency in `app/dependencies.py`.

### Core Business Flow

1. **Client Registration** (`POST /clients`) — creates a Client + Wallet atomically
2. **Credential Assignment** (`POST /credentials/assign`) — links NFC chip/QR to client
3. **Recharge** (`POST /operations/recharge`) — cashier adds balance to wallet
4. **Scan** (`POST /operations/scan`) — hardware (ESP32) calls this on NFC tap; validates credential, checks balance, deducts gate price, logs access. Returns GO/NO-GO. This endpoint is designed for direct device calls (no auth by default).

### Key Layers

- `app/models/` — SQLModel ORM (combines SQLAlchemy + Pydantic). Four files: `org.py`, `iot.py`, `customers.py`, `operations.py`
- `app/schemas/` — Pydantic request/response schemas (separate from models)
- `app/routers/` — FastAPI routers, one file per domain
- `app/security.py` — JWT creation/validation + bcrypt
- `app/database.py` — async SQLAlchemy engine + session factory

### Database

PostgreSQL 17 via `asyncpg`. All sessions are `AsyncSession`. The operations router uses `flush()` + explicit `rollback()` for ACID compliance on wallet deductions.

### Stack

- FastAPI 0.115+, SQLModel, SQLAlchemy 2.0 async, Pydantic Settings
- Python-Jose (JWT), Passlib/bcrypt, Alembic, Uvicorn
- PostgreSQL 17, Docker Compose

## Data Model Details

### Enums (defined in `app/models/base.py`)

- `CredentialType`: NFC, QR, BLE, PIN
- `Status`: ACTIVE, INACTIVE, BLOCKED, LOST, EXPIRED
- `AccessResult`: GRANTED, DENIED
- `Direction`: ENTRY, EXIT
- `BatchStatus`: AVAILABLE, ASSIGNED, DEFECTIVE, LOST

All models inherit from `BaseModel` which provides `id` (UUID), `created_at`, and `updated_at`.

### Key Relationships

- `Company` → `Branch` → `Zone` → `Gate` → `Device` (IoT hardware)
- `Client` → `Wallet` (1:many) and `Client` → `ClientCredential` → `Credential` (many:many join table)
- `Credential` optionally links to `Chip` (physical NFC chip inventory)
- `Access` records link `ClientCredential` + `Gate` + `AccessResult`
- `Transaction` records link `Wallet` + `Type` (transaction type), with optional `access_id`

### Required Seed Data

The `/operations/scan` endpoint depends on a `Type` row with `name = "COBRO_ACCESO"` existing in the database. This must be seeded manually or via migration before the scan flow works.

## Important Patterns

### Async Relationship Loading

SQLAlchemy lazy loading doesn't work with `AsyncSession`. Always use `selectinload` when querying models that need relationships:

```python
from sqlalchemy.orm import selectinload
query = select(User).where(User.id == user_id).options(selectinload(User.roles))
```

### Settings

`app/config.py` uses `pydantic-settings` with `lru_cache`. All env vars are read from `.env`. Required vars: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_SERVER`, `POSTGRES_DB`, `SECRET_KEY`.
