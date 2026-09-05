from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.models.org import Permission, RolePermissionLink, UserPermissionLink, User
from app.schemas.org import PermissionCreate, PermissionUpdate, PermissionRead
from app.dependencies import PermissionChecker

router = APIRouter(
    prefix="/permissions",
    tags=["Permissions"],
    responses={404: {"description": "Not found"}},
)

allow_read   = PermissionChecker("permissions", "read")
allow_assign = PermissionChecker("permissions", "assign")


@router.get("/", response_model=List[PermissionRead])
async def read_permissions(
    resource: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read),
):
    query = select(Permission)
    if resource:
        query = query.where(Permission.resource == resource)
    return (await session.exec(query)).all()


@router.post("/", response_model=PermissionRead, status_code=status.HTTP_201_CREATED)
async def create_permission(
    body: PermissionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_assign),
):
    existing = (await session.exec(
        select(Permission).where(
            Permission.resource == body.resource,
            Permission.action == body.action,
        )
    )).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"El permiso '{body.resource}:{body.action}' ya existe.")

    perm = Permission(**body.model_dump())
    session.add(perm)
    await session.commit()
    await session.refresh(perm)
    return perm


@router.patch("/{permission_id}", response_model=PermissionRead)
async def update_permission(
    permission_id: UUID,
    body: PermissionUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_assign),
):
    perm = await session.get(Permission, permission_id)
    if not perm:
        raise HTTPException(status_code=404, detail="Permiso no encontrado.")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(perm, key, value)

    session.add(perm)
    await session.commit()
    await session.refresh(perm)
    return perm


@router.delete("/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    permission_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_assign),
):
    perm = await session.get(Permission, permission_id)
    if not perm:
        raise HTTPException(status_code=404, detail="Permiso no encontrado.")

    try:
        await session.delete(perm)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el permiso porque está asignado a roles o usuarios.",
        )
    return None
