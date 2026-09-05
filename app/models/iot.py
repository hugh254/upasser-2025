from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from decimal import Decimal
import uuid
from .base import BaseModel, Status, Direction

# Necesitamos importar string references para evitar circular imports en tiempo de ejecución
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .org import Branch

class Device(BaseModel, table=True):
    __tablename__ = "devices"
    mac_address: str = Field(unique=True)
    chip_model: str
    fw_version: str
    last_ip: str
    last_seen: datetime
    status: Status
    branch_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    )

class Zone(BaseModel, table=True):
    __tablename__ = "zones"
    name: str
    code: str
    description: str
    branch_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    )
    branch: "Branch" = Relationship(back_populates="zones")
    # Relación back_populates a Branch debería definirse en org.py con string ref, 
    # pero aquí definimos la FK.
    
    gates: List["Gate"] = Relationship(back_populates="zone")

class Gate(BaseModel, table=True):
    __tablename__ = "gates"
    zone_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("zones.id", ondelete="RESTRICT"), nullable=False)
    )
    device_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False)
    )
    code: str
    direction: Direction
    price: Decimal = Field(default=0, max_digits=10, decimal_places=2)

    zone: Zone = Relationship(back_populates="gates")
    device: Device = Relationship()