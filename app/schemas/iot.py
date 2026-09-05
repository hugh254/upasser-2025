from typing import Optional, Annotated
from sqlmodel import SQLModel, Field
from decimal import Decimal
from uuid import UUID
from datetime import datetime
from app.models.base import Status, Direction # Importamos el Enum del modelo base

# --- DEVICES ---
class DeviceBase(SQLModel):
    mac_address: str
    chip_model: str
    fw_version: str
    last_ip: str
    branch_id: UUID
    status: Status = Status.ACTIVE

class DeviceCreate(DeviceBase):
    pass # last_seen se puede setear automático en el backend

class DeviceUpdate(SQLModel):
    fw_version: Optional[str] = None
    last_ip: Optional[str] = None
    status: Optional[Status] = None
    branch_id: Optional[UUID] = None

class DeviceRead(DeviceBase):
    id: UUID
    last_seen: datetime
    created_at: datetime
    updated_at: datetime

# --- ZONES ---
class ZoneBase(SQLModel):
    name: str
    code: str
    description: str
    branch_id: UUID

class ZoneCreate(ZoneBase):
    pass

class ZoneUpdate(SQLModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None

class ZoneRead(ZoneBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

# --- GATES ---
class GateBase(SQLModel):
    zone_id: UUID
    device_id: UUID
    code: str
    direction: Direction
    price: Annotated[
        Decimal,
        Field(default=Decimal("0"), max_digits=10, decimal_places=2, ge=0)
    ]

class GateCreate(GateBase):
    pass

class GateUpdate(SQLModel):
    zone_id: Optional[UUID] = None
    device_id: Optional[UUID] = None
    code: Optional[str] = None
    direction: Optional[Direction] = None
    price: Optional[Decimal] = None 

class GateRead(GateBase):
    id: UUID
    created_at: datetime
    updated_at: datetime