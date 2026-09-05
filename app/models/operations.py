from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import CheckConstraint, UniqueConstraint, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from decimal import Decimal
import uuid
from .base import BaseModel, AccessResult, WalletType, TicketStatus

# Importaciones condicionales para relaciones
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .customers import Client
    from .iot import Gate

class Wallet(BaseModel, table=True):
    __tablename__ = "wallets"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="wallet_amount_non_negative"),
        CheckConstraint(
            "client_id IS NOT NULL OR client_credential_id IS NOT NULL",
            name="wallet_owner_required"
        ),
        UniqueConstraint("client_id", "wallet_type", name="uq_wallet_client_type"),
        UniqueConstraint("client_credential_id", "wallet_type", name="uq_wallet_credential_type"),
    )
    amount: Decimal = Field(default=0, max_digits=10, decimal_places=2)
    wallet_type: WalletType = Field(default=WalletType.MAIN)
    client_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=True)
    )
    client_credential_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("client_credential.id", ondelete="CASCADE"), nullable=True)
    )

    client: Optional["Client"] = Relationship(back_populates="wallets")
    transactions: list["Transaction"] = Relationship(back_populates="wallet")

class Type(BaseModel, table=True):
    __tablename__ = "types" # Tipos de transacción
    name: str
    description: str

class Access(BaseModel, table=True):
    __tablename__ = "access"
    __table_args__ = (
        CheckConstraint(
            "client_credential_id IS NOT NULL OR ticket_id IS NOT NULL",
            name="access_credential_or_ticket_required"
        ),
    )
    result: AccessResult
    reason: Optional[str] = Field(default=None)
    extra_data: Optional[str] = Field(default=None)

    gate_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("gates.id", ondelete="RESTRICT"), nullable=False)
    )
    client_credential_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("client_credential.id", ondelete="RESTRICT"), nullable=True)
    )
    ticket_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=True)
    )

class Transaction(BaseModel, table=True):
    __tablename__ = "transactions"
    __table_args__ = (
        # Convención de signos: positivo = ingreso (recarga), negativo = egreso (cobro de acceso)
        CheckConstraint("amount != 0", name="transaction_amount_nonzero"),
        CheckConstraint(
            "wallet_id IS NOT NULL OR ticket_id IS NOT NULL",
            name="transaction_wallet_or_ticket_required"
        ),
    )
    amount: Decimal = Field(max_digits=10, decimal_places=2)

    type_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("types.id", ondelete="RESTRICT"), nullable=False)
    )
    wallet_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=True)
    )
    ticket_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=True)
    )
    access_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("access.id", ondelete="SET NULL"), nullable=True)
    )
    client_credential_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("client_credential.id", ondelete="SET NULL"), nullable=True)
    )

    wallet: Optional[Wallet] = Relationship(back_populates="transactions")
    # access: Optional[Access] = Relationship()