from typing import Optional
from sqlmodel import SQLModel
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.base import AccessResult, WalletType

# --- TYPES (Tipos de Transacción) ---
class TypeBase(SQLModel):
    name: str
    description: str

class TypeCreate(TypeBase):
    pass

class TypeUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None

class TypeRead(TypeBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

# --- WALLETS ---
class WalletBase(SQLModel):
    client_id: Optional[UUID] = None              # None para wallets anónimas
    client_credential_id: Optional[UUID] = None   # Usado cuando client_id es None
    amount: Decimal = Decimal("0.00")
    wallet_type: WalletType = WalletType.MAIN

class WalletCreate(WalletBase):
    pass

class WalletUpdate(SQLModel):
    wallet_type: Optional[WalletType] = None

class WalletRead(WalletBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

# --- TRANSACTIONS ---
class TransactionBase(SQLModel):
    amount: Decimal
    type_id: UUID
    wallet_id: Optional[UUID] = None       # None para transacciones de ticket
    ticket_id: Optional[UUID] = None       # None para transacciones de wallet
    access_id: Optional[UUID] = None
    client_credential_id: Optional[UUID] = None

class TransactionCreate(TransactionBase):
    pass

class TransactionRead(TransactionBase):
    id: UUID
    created_at: datetime

# --- ACCESS ---
class AccessBase(SQLModel):
    result: AccessResult
    reason: Optional[str] = None
    extra_data: Optional[str] = None
    gate_id: UUID
    client_credential_id: Optional[UUID] = None   # None si el acceso es por ticket
    ticket_id: Optional[UUID] = None               # None si el acceso es por credencial

class AccessCreate(AccessBase):
    pass

class AccessRead(AccessBase):
    id: UUID
    created_at: datetime

# Esquema para que el cajero haga una recarga
class RechargeRequest(SQLModel):
    client_id: UUID
    amount: Decimal
    # El ID del tipo de transacción "RECARGA" que creaste antes
    type_id: UUID

# Esquema para el ESP32 (El hardware solo conoce textos, no UUIDs)
class IoTScanRequest(SQLModel):
    mac_address: str
    nfc_uid: str

# Recarga de wallet anónima (chip sin titular registrado)
class RechargeAnonymousRequest(SQLModel):
    credential_public_id: str   # upasser_uuid del chip
    amount: Decimal
    type_id: UUID