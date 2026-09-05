from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.operations import Type # Tu modelo de base de datos
from app.models.org import User
# Asegúrate de tener estos esquemas definidos en app/schemas/operations.py
from app.schemas.operations import TypeCreate, TypeRead, TypeUpdate
from app.dependencies import PermissionChecker, require_platform_admin

router = APIRouter(prefix="/types",
    tags=["Operaciones"],
    responses={404: {"description": "Not found"}},)

# --- CREATE TYPE ---
@router.post("/", response_model=TypeRead, status_code=status.HTTP_201_CREATED)
async def create_type(
    type_in: TypeCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin)
):
    # Validar que no exista un tipo con el mismo nombre (ej. "RECARGA" duplicado)
    query = select(Type).where(Type.name == type_in.name)
    if (await session.exec(query)).first():
        raise HTTPException(status_code=400, detail="Este tipo de transacción ya existe.")

    db_type = Type.model_validate(type_in)
    session.add(db_type)
    
    await session.commit()
    await session.refresh(db_type)
    return db_type

# --- READ ALL TYPES ---
@router.get("/", response_model=List[TypeRead])
async def read_types(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    # Operadores y cajeros necesitan poder leer los tipos para hacer transacciones
    current_user: User = Depends(PermissionChecker("operations", "types_read"))
):
    result = await session.exec(select(Type).offset(offset).limit(limit))
    return result.all()

# --- READ ONE TYPE ---
@router.get("/{type_id}", response_model=TypeRead)
async def read_type(
    type_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("operations", "types_read"))  # lectura: OK para todos
):
    transaction_type = await session.get(Type, type_id)
    if not transaction_type:
        raise HTTPException(status_code=404, detail="Tipo de transacción no encontrado.")
    return transaction_type

# --- UPDATE TYPE ---
@router.patch("/{type_id}", response_model=TypeRead)
async def update_type(
    type_id: UUID,
    type_update: TypeUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin)
):
    db_type = await session.get(Type, type_id)
    if not db_type:
        raise HTTPException(status_code=404, detail="Tipo de transacción no encontrado.")

    # Si intentan cambiar el nombre, validar que no choque con otro existente
    if type_update.name and type_update.name != db_type.name:
        query = select(Type).where(Type.name == type_update.name)
        if (await session.exec(query)).first():
            raise HTTPException(status_code=400, detail="Ya existe otro tipo con ese nombre.")

    type_data = type_update.model_dump(exclude_unset=True)
    for key, value in type_data.items():
        setattr(db_type, key, value)

    session.add(db_type)
    await session.commit()
    await session.refresh(db_type)
    return db_type

# --- DELETE TYPE ---
@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_type(
    type_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin)
):
    transaction_type = await session.get(Type, type_id)
    if not transaction_type:
        raise HTTPException(status_code=404, detail="Tipo de transacción no encontrado.")
    
    await session.delete(transaction_type)
    await session.commit()
    return None