from typing import List
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.models.iot import Device
from app.models.org import Branch, User
from app.schemas.iot import DeviceCreate, DeviceRead, DeviceUpdate
from app.dependencies import PermissionChecker, get_company_filter

router = APIRouter(prefix="/devices",
    tags=["IoT Dispositivos"],
    responses={404: {"description": "Not found"}},)

# --- CREATE DEVICE ---
@router.post("/", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(
    device_in: DeviceCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("devices", "read"))
):
    # 1. Validar que la sucursal exista
    branch = await session.get(Branch, device_in.branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada.")

    # 2. Validar que la sucursal pertenezca a la empresa del usuario
    tenant_id = get_company_filter(current_user)
    if tenant_id and branch.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta sucursal.")

    # 2. Validar que la MAC address no esté duplicada
    query = select(Device).where(Device.mac_address == device_in.mac_address)
    if (await session.exec(query)).first():
        raise HTTPException(status_code=400, detail="Ya existe un dispositivo registrado con esta MAC Address.")

    # 3. Crear el dispositivo
    db_device = Device.model_validate(device_in)
    
    # Asignamos la fecha de "última vez visto" al momento de su creación en UTC
    db_device.last_seen = datetime.now(timezone.utc)
    
    session.add(db_device)
    await session.commit()
    await session.refresh(db_device)
    return db_device

# --- READ ALL DEVICES ---
@router.get("/", response_model=List[DeviceRead])
async def read_devices(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("devices", "read"))
):
    # Device no tiene company_id directo — se filtra via JOIN con Branch
    company_id = get_company_filter(current_user)
    if company_id:
        query = (
            select(Device)
            .join(Branch, Device.branch_id == Branch.id)
            .where(Branch.company_id == company_id)
            .offset(offset).limit(limit)
        )
    else:
        query = select(Device).offset(offset).limit(limit)

    return (await session.exec(query)).all()

# --- READ ONE DEVICE ---
@router.get("/{device_id}", response_model=DeviceRead)
async def read_device(
    device_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("devices", "read"))
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")

    # Verificar acceso via la sucursal del dispositivo
    tenant_id = get_company_filter(current_user)
    if tenant_id:
        branch = await session.get(Branch, device.branch_id)
        if not branch or branch.company_id != tenant_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a este dispositivo.")

    return device

# --- UPDATE DEVICE ---
@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: UUID,
    device_update: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("devices", "write"))
):
    db_device = await session.get(Device, device_id)
    if not db_device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")

    tenant_id = get_company_filter(current_user)
    if tenant_id:
        branch = await session.get(Branch, db_device.branch_id)
        if not branch or branch.company_id != tenant_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a este dispositivo.")

    # Si se mueve a otra sucursal, validar que exista y pertenezca a la misma empresa
    if device_update.branch_id:
        new_branch = await session.get(Branch, device_update.branch_id)
        if not new_branch:
            raise HTTPException(status_code=404, detail="La nueva sucursal no existe.")
        if tenant_id and new_branch.company_id != tenant_id:
            raise HTTPException(status_code=403, detail="No puedes mover el dispositivo a una sucursal de otra empresa.")

    device_data = device_update.model_dump(exclude_unset=True)
    for key, value in device_data.items():
        setattr(db_device, key, value)

    session.add(db_device)
    await session.commit()
    await session.refresh(db_device)
    return db_device

# --- DELETE DEVICE ---
@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("devices", "delete"))
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")

    tenant_id = get_company_filter(current_user)
    if tenant_id:
        branch = await session.get(Branch, device.branch_id)
        if not branch or branch.company_id != tenant_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a este dispositivo.")

    try:
        await session.delete(device)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el dispositivo porque tiene gates o registros asociados."
        )
    return None