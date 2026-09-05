from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.models.iot import Gate, Device, Zone
from app.models.org import Branch, User
from app.schemas.iot import GateCreate, GateRead, GateUpdate
from app.dependencies import PermissionChecker, get_company_filter

allow_read   = PermissionChecker("gates", "read")
allow_write  = PermissionChecker("gates", "write")
allow_delete = PermissionChecker("gates", "delete")

router = APIRouter(prefix="/gates",
    tags=["IoT Gates"],
    responses={404: {"description": "Not found"}},)

# --- CREATE GATE ---
@router.post("/", response_model=GateRead, status_code=status.HTTP_201_CREATED)
async def create_gate(
    gate_in: GateCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_write)
):
    # 1. Validar que el Dispositivo exista
    device = await session.get(Device, gate_in.device_id)
    if not device:
        raise HTTPException(status_code=404, detail="El Dispositivo IoT no existe.")

    # 2. Validar que la Zona exista y pertenezca a la empresa del usuario
    zone = await session.get(Zone, gate_in.zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="La Zona física no existe.")

    tenant_id = get_company_filter(current_user)
    if tenant_id:
        branch = await session.get(Branch, zone.branch_id)
        if not branch or branch.company_id != tenant_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a esta zona.")

    # 3. Crear el Gate (Configuración lógica)
    db_gate = Gate.model_validate(gate_in)
    session.add(db_gate)

    await session.commit()
    await session.refresh(db_gate)
    return db_gate

# --- READ ALL GATES ---
@router.get("/", response_model=List[GateRead])
async def read_gates(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read)
):
    company_id = get_company_filter(current_user)
    if company_id:
        query = (
            select(Gate)
            .join(Zone, Gate.zone_id == Zone.id)
            .join(Branch, Zone.branch_id == Branch.id)
            .where(Branch.company_id == company_id)
            .offset(offset).limit(limit)
        )
    else:
        query = select(Gate).offset(offset).limit(limit)

    return (await session.exec(query)).all()

# --- READ ONE GATE ---
@router.get("/{gate_id}", response_model=GateRead)
async def read_gate(
    gate_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read)
):
    gate = await session.get(Gate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Gate no encontrado.")

    tenant_id = get_company_filter(current_user)
    if tenant_id:
        zone = await session.get(Zone, gate.zone_id)
        branch = await session.get(Branch, zone.branch_id) if zone else None
        if not branch or branch.company_id != tenant_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a este gate.")

    return gate

# --- UPDATE GATE ---
@router.patch("/{gate_id}", response_model=GateRead)
async def update_gate(
    gate_id: UUID,
    gate_update: GateUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_write)
):
    db_gate = await session.get(Gate, gate_id)
    if not db_gate:
        raise HTTPException(status_code=404, detail="Gate no encontrado.")

    # Validar FKs si se intentan actualizar
    if gate_update.device_id:
        if not await session.get(Device, gate_update.device_id):
            raise HTTPException(status_code=404, detail="El nuevo Dispositivo no existe.")
            
    if gate_update.zone_id:
        if not await session.get(Zone, gate_update.zone_id):
            raise HTTPException(status_code=404, detail="La nueva Zona no existe.")

    gate_data = gate_update.model_dump(exclude_unset=True)
    for key, value in gate_data.items():
        setattr(db_gate, key, value)

    session.add(db_gate)
    await session.commit()
    await session.refresh(db_gate)
    return db_gate

# --- DELETE GATE ---
@router.delete("/{gate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gate(
    gate_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_delete)
):
    gate = await session.get(Gate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Gate no encontrado.")

    try:
        await session.delete(gate)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el gate porque tiene registros de acceso asociados."
        )
    return None