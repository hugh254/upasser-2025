from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.iot import Zone
from app.models.org import Branch, User
from app.schemas.iot import ZoneCreate, ZoneRead, ZoneUpdate
from app.dependencies import PermissionChecker

router = APIRouter(prefix="/zones",
    tags=["IoT Zonas"],
    responses={404: {"description": "Not found"}},)

# --- CREATE ZONE ---
@router.post("/", response_model=ZoneRead, status_code=status.HTTP_201_CREATED)
async def create_zone(
    zone_in: ZoneCreate,
    session: AsyncSession = Depends(get_session),
    # Solo Admins o Managers pueden configurar la estructura física
    current_user: User = Depends(PermissionChecker("zones", "write"))
):
    # 1. Validar que la Sucursal (Branch) exista
    branch = await session.get(Branch, zone_in.branch_id)
    if not branch:
        raise HTTPException(
            status_code=404, 
            detail=f"Sucursal con id {zone_in.branch_id} no encontrada."
        )

    # 2. Crear la Zona
    db_zone = Zone.model_validate(zone_in)
    session.add(db_zone)
    
    # 3. Guardar en base de datos
    await session.commit()
    await session.refresh(db_zone)
    return db_zone

# --- READ ALL ZONES ---
@router.get("/", response_model=List[ZoneRead])
async def read_zones(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    # Aquí podríamos ser más permisivos y dejar que los empleados vean las zonas
    current_user: User = Depends(PermissionChecker("zones", "read"))
):
    result = await session.exec(select(Zone).offset(offset).limit(limit))
    return result.all()

# --- READ ONE ZONE ---
@router.get("/{zone_id}", response_model=ZoneRead)
async def read_zone(
    zone_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("zones", "read"))
):
    zone = await session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zona no encontrada.")
    return zone

# --- UPDATE ZONE ---
@router.patch("/{zone_id}", response_model=ZoneRead)
async def update_zone(
    zone_id: UUID,
    zone_update: ZoneUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("zones", "write"))
):
    # 1. Buscar la Zona existente
    db_zone = await session.get(Zone, zone_id)
    if not db_zone:
        raise HTTPException(status_code=404, detail="Zona no encontrada.")

    # 2. (Opcional) Si intentan cambiarla de sucursal, validar que la nueva sucursal exista
    '''if zone_update.branch_id:
        branch = await session.get(Branch, zone_update.branch_id)
        if not branch:
            raise HTTPException(status_code=404, detail="La nueva Sucursal no existe.")
    '''
    # 3. Actualizar campos
    zone_data = zone_update.model_dump(exclude_unset=True)
    for key, value in zone_data.items():
        setattr(db_zone, key, value)

    session.add(db_zone)
    await session.commit()
    await session.refresh(db_zone)
    return db_zone

# --- DELETE ZONE ---
@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(
    zone_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("zones", "delete"))
):
    zone = await session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zona no encontrada.")
    
    await session.delete(zone)
    await session.commit()
    return None