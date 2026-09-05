from typing import Optional
from sqlmodel import SQLModel
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.base import CredentialType, Status, BatchStatus, AssignmentStatus, TicketStatus

# --- CLIENTS (CLIENTS) ---
class ClientBase(SQLModel):
    name: str
    last_name: str
    ci: str
    email: str
    company_id: UUID

class ClientCreate(ClientBase):
    pass

class ClientUpdate(SQLModel):
    name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    ci: Optional[str] = None

class ClientRead(ClientBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

# --- CREDENTIALS ---
class CredentialBase(SQLModel):
    type: CredentialType
    public_id: str
    status: Status = Status.ACTIVE
    company_id: UUID
    chip_id: Optional[UUID] = None

class CredentialCreate(CredentialBase):
    secret_data: str # Necesario al crear

class CredentialUpdate(SQLModel):
    status: Optional[Status] = None
    secret_data: Optional[str] = None # Permitir rotar secretos

class CredentialRead(CredentialBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    # OJO: Decidimos NO devolver 'secret_data' por defecto.
    # Si necesitas verlo, crea un schema 'CredentialAdminRead' separado.

# --- CLIENT CREDENTIAL LINK ---
class ClientCredentialCreate(SQLModel):
    client_id: Optional[UUID] = None
    credential_id: UUID

class ClientCredentialRead(SQLModel):
    id: UUID
    client_id: Optional[UUID]
    credential_id: UUID
    state: bool
    assignment_status: AssignmentStatus
    created_at: datetime

class ClientCredentialActivate(SQLModel):
    """Vincula un titular registrado a una credencial anónima (PENDING → ACTIVE)."""
    client_id: UUID

# --- TICKETS ---
class TicketCreate(SQLModel):
    amount: Optional[Decimal] = None
    zone_id: Optional[UUID] = None
    company_id: UUID
    expires_at: Optional[datetime] = None

class TicketRead(SQLModel):
    id: UUID
    qr_code: str
    amount: Optional[Decimal]
    zone_id: Optional[UUID]
    company_id: UUID
    expires_at: Optional[datetime]
    used_at: Optional[datetime]
    status: TicketStatus
    created_at: datetime

class TicketUpdate(SQLModel):
    status: Optional[TicketStatus] = None
    expires_at: Optional[datetime] = None

# --- CHIPS (Inventario físico) ---
class ChipBase(SQLModel):
    nro_batch: str
    batch_status: BatchStatus
    physical_uuid: str
    upasser_uuid: str
    company_id: Optional[UUID] = None

class ChipCreate(ChipBase):
    pass

class ChipUpdate(SQLModel):
    nro_batch: Optional[str] = None
    batch_status: Optional[BatchStatus] = None
    physical_uuid: Optional[str] = None
    upasser_uuid: Optional[str] = None
    company_id: Optional[UUID] = None

class ChipRead(ChipBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

# --- CREDENTIAL LOOKUP ---
class CredentialLookupRead(SQLModel):
    credential_id: UUID
    public_id: str
    status: str
    type: str
    company_id: UUID
    chip_id: Optional[UUID] = None
    assignment_status: Optional[str] = None     # None si no tiene ClientCredential
    client_id: Optional[UUID] = None            # None si es PENDING
    client_credential_id: Optional[UUID] = None
    wallet_balance: Optional[Decimal] = None    # None si no tiene wallet
    client_name: Optional[str] = None
    client_last_name: Optional[str] = None
    client_ci: Optional[str] = None

# --- BATCH CHIP OPERATIONS ---
class BatchAssignRequest(SQLModel):
    nro_batch: str
    company_id: UUID

class BatchActivateRequest(SQLModel):
    nro_batch: str
    company_id: UUID

class BatchAssignResult(SQLModel):
    assigned: int
    skipped: int

class BatchActivateResult(SQLModel):
    activated: int
    skipped: int
