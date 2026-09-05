from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.database import get_session
from app.models.org import Role, User, Permission, RolePermissionLink
from app.models.base import RoleScope
from app.schemas.org import RoleCreate, RoleRead, RoleUpdate, PermissionRead, RolePermissionAssign
from app.dependencies import PermissionChecker, require_platform_admin

router = APIRouter(
    prefix="/roles",
    tags=["Roles"],
    responses={404: {"description": "Not found"}},
)

allow_read   = PermissionChecker("roles", "read")
allow_assign = PermissionChecker("roles", "assign")


@router.post("/", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    role: RoleCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin)
):
    db_role = Role.model_validate(role)
    session.add(db_role)
    await session.commit()
    await session.refresh(db_role)
    return db_role


@router.get("/", response_model=List[RoleRead])
async def read_roles(
    scope: RoleScope | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read)
):
    """
    Lista todos los roles. Acepta ?scope=PLATFORM o ?scope=COMPANY para filtrar.
    Útil en el frontend para mostrar solo los roles asignables por empresa.
    """
    query = select(Role)
    if scope:
        query = query.where(Role.scope == scope)
    return (await session.exec(query)).all()


@router.get("/{role_id}", response_model=RoleRead)
async def read_role(
    role_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read)
):
    role = await session.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")
    return role


@router.patch("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: UUID,
    role_update: RoleUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin)
):
    role = await session.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los roles del sistema no pueden modificarse."
        )

    role_data = role_update.model_dump(exclude_unset=True)
    for key, value in role_data.items():
        setattr(role, key, value)

    session.add(role)
    await session.commit()
    await session.refresh(role)
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin)
):
    role = await session.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los roles del sistema no pueden eliminarse."
        )

    try:
        await session.delete(role)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el rol porque tiene usuarios asignados."
        )
    return None


# --- ROLE PERMISSIONS ---

@router.get("/{role_id}/permissions", response_model=List[PermissionRead])
async def get_role_permissions(
    role_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read),
):
    role = (await session.exec(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )).first()
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")
    return role.permissions


@router.post("/{role_id}/permissions", response_model=List[PermissionRead], status_code=status.HTTP_201_CREATED)
async def add_role_permission(
    role_id: UUID,
    body: RolePermissionAssign,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_assign),
):
    role = await session.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")
    if role.is_system:
        raise HTTPException(status_code=403, detail="No se pueden modificar los permisos de un rol del sistema.")
    if not await session.get(Permission, body.permission_id):
        raise HTTPException(status_code=404, detail="Permiso no encontrado.")

    existing = (await session.exec(
        select(RolePermissionLink).where(
            RolePermissionLink.role_id == role_id,
            RolePermissionLink.permission_id == body.permission_id,
        )
    )).first()
    if existing:
        raise HTTPException(status_code=400, detail="El rol ya tiene ese permiso asignado.")

    session.add(RolePermissionLink(role_id=role_id, permission_id=body.permission_id))
    await session.commit()

    role = (await session.exec(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )).first()
    return role.permissions


@router.delete("/{role_id}/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_permission(
    role_id: UUID,
    permission_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_assign),
):
    role = await session.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")
    if role.is_system:
        raise HTTPException(status_code=403, detail="No se pueden modificar los permisos de un rol del sistema.")

    link = (await session.exec(
        select(RolePermissionLink).where(
            RolePermissionLink.role_id == role_id,
            RolePermissionLink.permission_id == permission_id,
        )
    )).first()
    if not link:
        raise HTTPException(status_code=404, detail="El rol no tiene ese permiso asignado.")

    await session.delete(link)
    await session.commit()
    return None
