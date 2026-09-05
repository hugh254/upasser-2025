from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.models.org import User, Role, RoleUserLink, Permission, UserPermissionLink
from app.schemas.org import (
    UserCreateWithRoles, UserReadWithRoles, UserUpdate,
    UserPermissionOverrideCreate, UserPermissionOverrideRead, PermissionRead,
)
from app.security import get_password_hash
from app.dependencies import PermissionChecker, get_company_filter

router = APIRouter(prefix="/users",
    tags=["Users Management"],
    responses={404: {"description": "Not found"}},)

# --- CREATE USER (Solo Admins) ---
@router.post("/", response_model=UserReadWithRoles, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreateWithRoles,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("users", "write"))
):
    # 1. Validar que el admin de empresa solo cree usuarios dentro de su empresa
    tenant_id = get_company_filter(current_user)
    if tenant_id and user_in.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No puedes crear usuarios en otra empresa.")

    # 2. Validar email
    query = select(User).where(User.email == user_in.email)
    result = await session.exec(query)
    if result.first():
        raise HTTPException(status_code=400, detail="El email ya está registrado.")

    # 2. Preparar Usuario
    user_data = user_in.model_dump(exclude={"role_ids"})
    user_data["password"] = get_password_hash(user_in.password)
    new_user = User.model_validate(user_data)
    
    # Iniciamos el seguimiento del objeto en la sesión (Inicio visual de transacción)
    session.add(new_user)

    # --- INICIO BLOQUE TRANSACCIONAL SEGURO ---
    try:
        # MAGIA: Enviamos el INSERT a la BD para que genere el ID (UUID),
        # PERO la transacción sigue abierta. No hemos hecho commit.
        await session.flush() 

        # 3. Asignar Roles
        if user_in.role_ids:
            for role_id in user_in.role_ids:
                role = await session.get(Role, role_id)
                if not role:
                    # Lanzamos un error genérico de Python para caer en el except
                    raise ValueError(f"Rol con ID {role_id} no existe.")
                
                link = RoleUserLink(user_id=new_user.id, role_id=role_id)
                session.add(link)

        # 4. Si todo el bloque anterior funcionó perfecto, hacemos el COMMIT FINAL
        await session.commit()

    except Exception as e:
        # 🚨 SI ALGO FALLÓ (ej. rol no existe, error de BD), DESHACEMOS TODO
        await session.rollback()
        
        # Le respondemos al cliente qué salió mal
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Transacción fallida, no se guardó nada: {str(e)}"
        )
    # --- FIN BLOQUE TRANSACCIONAL ---

    # 5. Retornar el usuario creado con sus relaciones
    query_refresh = select(User).where(User.id == new_user.id).options(selectinload(User.roles))
    result_refresh = await session.exec(query_refresh)
    return result_refresh.first()

# --- LIST USERS ---
@router.get("/", response_model=List[UserReadWithRoles])
async def read_users(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("users", "read"))
):
    query = select(User).options(selectinload(User.roles)).offset(offset).limit(limit)

    # Filtro tenant: platform_admin ve todos los usuarios, admin de empresa solo los suyos
    company_id = get_company_filter(current_user)
    if company_id:
        query = query.where(User.company_id == company_id)

    return (await session.exec(query)).all()


# --- GET ONE USER ---
@router.get("/{user_id}", response_model=UserReadWithRoles)
async def read_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("users", "read"))
):
    query = select(User).where(User.id == user_id).options(selectinload(User.roles))
    user = (await session.exec(query)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # Un admin de empresa solo puede ver usuarios de su propia empresa
    tenant_id = get_company_filter(current_user)
    if tenant_id and user.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este usuario.")

    return user


# --- UPDATE USER ---
@router.patch("/{user_id}", response_model=UserReadWithRoles)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("users", "write"))
):
    query = select(User).where(User.id == user_id).options(selectinload(User.roles))
    user = (await session.exec(query)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    update_data = user_in.model_dump(exclude_unset=True)

    # Hashear password si se está actualizando
    if "password" in update_data:
        update_data["password"] = get_password_hash(update_data["password"])

    # Actualizar campos del usuario
    for key, value in update_data.items():
        setattr(user, key, value)

    try:
        session.add(user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="El email ya está en uso por otro usuario.")

    # Recargar con roles
    query_refresh = select(User).where(User.id == user.id).options(selectinload(User.roles))
    return (await session.exec(query_refresh)).first()


# --- UPDATE ROLES (reemplaza todos los roles del usuario) ---
@router.put("/{user_id}/roles", response_model=UserReadWithRoles)
async def update_user_roles(
    user_id: UUID,
    role_ids: List[UUID],
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("users", "write"))
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # Validar que todos los roles existan antes de modificar
    for role_id in role_ids:
        if not await session.get(Role, role_id):
            raise HTTPException(status_code=404, detail=f"Rol {role_id} no existe.")

    try:
        # Eliminar todos los roles actuales del usuario
        await session.exec(
            delete(RoleUserLink).where(RoleUserLink.user_id == user_id)
        )
        await session.flush()

        # Asignar los nuevos roles
        for role_id in role_ids:
            session.add(RoleUserLink(user_id=user_id, role_id=role_id))

        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"Error al actualizar roles: {str(e)}")

    query_refresh = select(User).where(User.id == user_id).options(selectinload(User.roles))
    return (await session.exec(query_refresh)).first()


# --- DELETE USER ---
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("users", "delete"))
):
    # No permitir que el admin se elimine a sí mismo
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario.")

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    try:
        await session.delete(user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar el usuario porque tiene registros asociados."
        )
    return None


# --- USER PERMISSION OVERRIDES ---

@router.get("/{user_id}/permissions", response_model=List[UserPermissionOverrideRead])
async def get_user_permission_overrides(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("permissions", "read")),
):
    if not await session.get(User, user_id):
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    overrides = (await session.exec(
        select(UserPermissionLink).where(UserPermissionLink.user_id == user_id)
    )).all()

    if not overrides:
        return []

    perm_ids = [o.permission_id for o in overrides]
    perms = (await session.exec(
        select(Permission).where(Permission.id.in_(perm_ids))
    )).all()
    perm_map = {p.id: p for p in perms}

    return [
        UserPermissionOverrideRead(
            permission_id=o.permission_id,
            resource=perm_map[o.permission_id].resource,
            action=perm_map[o.permission_id].action,
            description=perm_map[o.permission_id].description,
            granted=o.granted,
        )
        for o in overrides
        if o.permission_id in perm_map
    ]


@router.post("/{user_id}/permissions", response_model=UserPermissionOverrideRead, status_code=status.HTTP_201_CREATED)
async def set_user_permission_override(
    user_id: UUID,
    body: UserPermissionOverrideCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("permissions", "assign")),
):
    if not await session.get(User, user_id):
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    perm = await session.get(Permission, body.permission_id)
    if not perm:
        raise HTTPException(status_code=404, detail="Permiso no encontrado.")

    existing = (await session.exec(
        select(UserPermissionLink).where(
            UserPermissionLink.user_id == user_id,
            UserPermissionLink.permission_id == body.permission_id,
        )
    )).first()

    if existing:
        existing.granted = body.granted
        session.add(existing)
    else:
        session.add(UserPermissionLink(
            user_id=user_id,
            permission_id=body.permission_id,
            granted=body.granted,
        ))

    await session.commit()

    return UserPermissionOverrideRead(
        permission_id=perm.id,
        resource=perm.resource,
        action=perm.action,
        description=perm.description,
        granted=body.granted,
    )


@router.delete("/{user_id}/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_permission_override(
    user_id: UUID,
    permission_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("permissions", "assign")),
):
    link = (await session.exec(
        select(UserPermissionLink).where(
            UserPermissionLink.user_id == user_id,
            UserPermissionLink.permission_id == permission_id,
        )
    )).first()
    if not link:
        raise HTTPException(status_code=404, detail="Override no encontrado para este usuario.")

    await session.delete(link)
    await session.commit()
    return None