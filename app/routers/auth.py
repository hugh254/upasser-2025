from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
from app.database import get_session
from app.models.org import User, Role, Permission, UserPermissionLink
from app.schemas.org import Token, UserRead, UserCreate, UserReadWithRoles
from app.security import verify_password, create_access_token, create_refresh_token, get_password_hash
from jose import jwt, JWTError
from app.config import get_settings

settings = get_settings()
from app.dependencies import get_current_user, PermissionChecker

router = APIRouter(prefix="/auth",
    tags=["Auth"],
    responses={404: {"description": "Not found"}},
    )

# LOGIN
@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    statement = (
        select(User)
        .where(User.email == form_data.username)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = (await session.exec(statement)).first()

    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Permisos base desde roles
    effective: set[str] = {
        f"{p.resource}:{p.action}"
        for role in user.roles
        for p in role.permissions
    }

    # Aplicar overrides individuales (granted=True agrega, granted=False quita)
    overrides = (await session.exec(
        select(UserPermissionLink).where(UserPermissionLink.user_id == user.id)
    )).all()

    if overrides:
        override_ids = [o.permission_id for o in overrides]
        perms = (await session.exec(
            select(Permission).where(Permission.id.in_(override_ids))
        )).all()
        perm_key = {p.id: f"{p.resource}:{p.action}" for p in perms}
        for o in overrides:
            key = perm_key[o.permission_id]
            if o.granted:
                effective.add(key)
            else:
                effective.discard(key)

    access_token = create_access_token(subject=user.id, permissions=sorted(effective))
    refresh_token = create_refresh_token(subject=user.id)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


# REFRESH — Emite un nuevo par de tokens recomputando permisos desde BD
@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_token: str,
    session: AsyncSession = Depends(get_session),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise credentials_exception
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    statement = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = (await session.exec(statement)).first()
    if not user:
        raise credentials_exception

    effective: set[str] = {
        f"{p.resource}:{p.action}"
        for role in user.roles
        for p in role.permissions
    }

    overrides = (await session.exec(
        select(UserPermissionLink).where(UserPermissionLink.user_id == user.id)
    )).all()

    if overrides:
        override_ids = [o.permission_id for o in overrides]
        perms = (await session.exec(select(Permission).where(Permission.id.in_(override_ids)))).all()
        perm_key = {p.id: f"{p.resource}:{p.action}" for p in perms}
        for o in overrides:
            key = perm_key[o.permission_id]
            if o.granted:
                effective.add(key)
            else:
                effective.discard(key)

    new_access = create_access_token(subject=user.id, permissions=sorted(effective))
    new_refresh = create_refresh_token(subject=user.id)
    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


# ME — Devuelve el usuario autenticado con sus roles (necesario para el frontend)
@router.get("/me", response_model=UserReadWithRoles)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


# REGISTRO — Solo admins pueden crear usuarios del sistema
@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(
    user: UserCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("users", "write")),
):
    existing = (await session.exec(select(User).where(User.email == user.email))).first()
    if existing:
        raise HTTPException(status_code=400, detail="El email ya está registrado.")

    user.password = get_password_hash(user.password)
    new_user = User.model_validate(user)
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user