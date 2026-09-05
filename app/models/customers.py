from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PgUUID
import uuid
from .base import BaseModel, CredentialType, Status, BatchStatus, TicketStatus, AssignmentStatus

class Client(BaseModel, table=True):
    __tablename__ = "clients" # Respetando tu nombre original
    name: str
    last_name: str
    ci: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    company_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    )

    company: "Company" = Relationship(back_populates="clients")
    # Relación con Wallets y Credenciales
    wallets: List["Wallet"] = Relationship(back_populates="client")
    client_credentials: List["ClientCredential"] = Relationship(back_populates="client")

class Credential(BaseModel, table=True):
    __tablename__ = "credentials"
    type: CredentialType
    public_id: str = Field(unique=True, index=True)  # UID del chip o QR público
    secret_data: str # Encriptado
    status: Status
    company_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    )
    chip_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("chips.id", ondelete="SET NULL"), nullable=True)
    )
    chip: Optional["Chip"] = Relationship(back_populates="credentials")

class Chip(BaseModel, table=True):
    """Inventario físico de chips. NULL company_id = pool de Upasser, non-null = asignado a empresa."""
    __tablename__ = "chips"
    nro_batch: str = Field(index=True)
    batch_status: BatchStatus = Field(default=BatchStatus.AVAILABLE)
    physical_uuid: str = Field(unique=True, index=True)
    upasser_uuid: str = Field(unique=True, index=True)
    company_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    )
    # Relación inversa hacia las credenciales
    credentials: List["Credential"] = Relationship(back_populates="chip")

class ClientCredential(BaseModel, table=True):
    """Tabla intermedia: Asigna una credencial a un cliente.
    client_id puede ser NULL cuando la credencial se vende sin registrar (PENDING).
    """
    __tablename__ = "client_credential"
    client_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=True)
    )
    credential_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("credentials.id", ondelete="RESTRICT"), nullable=False)
    )
    state: bool = True
    assignment_status: AssignmentStatus = Field(default=AssignmentStatus.PENDING)

    client: Optional[Client] = Relationship(back_populates="client_credentials")
    credential: Credential = Relationship()


class Ticket(BaseModel, table=True):
    """QR de un solo uso. Puede tener monto pre-cargado o dar acceso libre."""
    __tablename__ = "tickets"
    qr_code: str = Field(unique=True, index=True)
    amount: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    zone_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    )
    company_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    )
    expires_at: Optional[datetime] = Field(default=None)
    used_at: Optional[datetime] = Field(default=None)
    status: TicketStatus = Field(default=TicketStatus.AVAILABLE)