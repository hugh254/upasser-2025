from typing import Optional
from uuid import UUID
from fastapi import Depends, HTTPException, Request, status
from jose import jwt, JWTError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models.org import User
from app.models.base import RoleScope
from .security import oauth2_scheme
from .config import get_settings

settings = get_settings()


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    query = select(User).where(User.id == user_id).options(selectinload(User.roles))
    user = (await session.exec(query)).first()

    if user is None:
        raise credentials_exception

    # Permisos efectivos del JWT — cero queries adicionales por request
    request.state.permissions = set(payload.get("permissions", []))
    return user


def is_platform_admin(user: User) -> bool:
    """Devuelve True si el usuario tiene algún rol de scope PLATFORM."""
    return any(r.scope == RoleScope.PLATFORM for r in user.roles)


async def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    if not is_platform_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo accesible para administradores de plataforma.",
        )
    return user


def get_company_filter(user: User) -> Optional[UUID]:
    """
    Devuelve None si el usuario es de scope PLATFORM (accede a todos los datos).
    Devuelve company_id si es usuario de empresa (solo ve los datos de su empresa).
    Usar en los endpoints de listado para aplicar aislamiento por tenant.
    """
    return None if is_platform_admin(user) else user.company_id


# --- PERMISSION CHECKER ---
class PermissionChecker:
    def __init__(self, resource: str, action: str):
        self.resource = resource
        self.action = action

    def __call__(self, request: Request, user: User = Depends(get_current_user)) -> User:
        if is_platform_admin(user):
            return user
        permissions: set[str] = getattr(request.state, "permissions", set())
        if f"{self.resource}:{self.action}" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted"
            )
        return user