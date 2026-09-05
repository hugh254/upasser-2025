from typing import Optional
from datetime import datetime, timezone
import uuid
from sqlmodel import SQLModel, Field
from enum import Enum

# --- ENUMS ---
class CredentialType(str, Enum):
    NFC = "NFC"
    QR = "QR"
    BLE = "BLE"
    PIN = "PIN"

class Status(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"
    LOST = "LOST"
    EXPIRED = "EXPIRED"

"""
class TransactionTypeEnum(str, Enum):
    DEBIT = "DEBITAR"
    REDEEM = "REDIMIR"
    RECHARGE = "RECARGAR" # Agregado para soportar recargas
"""

class AccessResult(str, Enum):
    GRANTED = "GRANTED"
    DENIED = "DENIED"

class BatchStatus(str, Enum):
    AVAILABLE = "AVAILABLE"  # Disponible en inventario
    ASSIGNED = "ASSIGNED"      # Ya vinculado a una credencial
    DEFECTIVE = "DEFECTIVE"    # Dañado de fábrica
    LOST = "LOST"              # Perdido

class TicketStatus(str, Enum):
    AVAILABLE  = "AVAILABLE"   # Sin usar
    USED       = "USED"        # Canjeado
    EXPIRED    = "EXPIRED"     # Venció sin usar
    CANCELLED  = "CANCELLED"   # Anulado manualmente

class Direction(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"

class WalletType(str, Enum):
    MAIN = "MAIN"           # Billetera principal — usada por defecto en cobros y recargas
    BONUS = "BONUS"         # Saldo bono / promocional
    COURTESY = "COURTESY"   # Saldo de cortesía otorgado por la empresa

class RoleScope(str, Enum):
    PLATFORM = "PLATFORM"   # Roles internos de Upasser (platform_admin, etc.)
    COMPANY  = "COMPANY"    # Roles de empresas clientes (admin, manager, cajero)

class AssignmentStatus(str, Enum):
    PENDING = "PENDING"  # Vendida sin registrar — titular desconocido
    ACTIVE  = "ACTIVE"   # Vinculada a un cliente registrado

class ExpirationUnit(str, Enum):
    HOURS = "HOURS"
    DAYS  = "DAYS"

# --- MIXINS ---
class BaseModel(SQLModel):
    """Modelo base con UUID y Timestamps automáticos"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc).replace(tzinfo=None)}
    )