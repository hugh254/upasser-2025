from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.models.org import Company, User, Role, RoleUserLink
from app.schemas.org import CompanyCreate, CompanyRead, CompanyUpdate, CompanyOnboardRequest, CompanyOnboardResponse
from app.dependencies import PermissionChecker, get_company_filter, is_platform_admin
from app.security import get_password_hash

router = APIRouter(
    prefix="/companies",
    tags=["Companies"],
    responses={404: {"description": "Not found"}},
)

allow_write  = PermissionChecker("companies", "write")
allow_read   = PermissionChecker("companies", "read")
allow_delete = PermissionChecker("companies", "delete")
allow_onboard = PermissionChecker("companies", "onboard")

# --- ONBOARD (platform_admin) — crea empresa + usuario admin inicial atómicamente ---
@router.post("/onboard", response_model=CompanyOnboardResponse, status_code=status.HTTP_201_CREATED)
async def onboard_company(
    req: CompanyOnboardRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_onboard)
):
    # 1. Validar nombre de empresa único
    if (await session.exec(select(Company).where(Company.name == req.company_name))).first():
        raise HTTPException(status_code=400, detail="Ya existe una empresa con ese nombre.")

    # 2. Validar email único del admin inicial
    if (await session.exec(select(User).where(User.email == req.admin_email))).first():
        raise HTTPException(status_code=400, detail="El email del administrador ya está registrado.")

    # 3. Obtener el rol "admin" de empresa (scope COMPANY, name "admin")
    from app.models.base import RoleScope
    admin_role = (await session.exec(
        select(Role).where(Role.name == "admin", Role.scope == RoleScope.COMPANY)
    )).first()
    if not admin_role:
        raise HTTPException(status_code=500, detail="Rol 'admin' no encontrado. Ejecuta los seeds primero.")

    try:
        # 4. Crear la empresa
        new_company = Company(
            name=req.company_name,
            description=req.company_description,
        )
        session.add(new_company)
        await session.flush()

        # 5. Crear el usuario admin inicial de la empresa
        new_admin = User(
            name=req.admin_name,
            last_name=req.admin_last_name,
            email=req.admin_email,
            password=get_password_hash(req.admin_password),
            company_id=new_company.id,
        )
        session.add(new_admin)
        await session.flush()

        # 6. Asignar rol admin al nuevo usuario
        session.add(RoleUserLink(user_id=new_admin.id, role_id=admin_role.id))

        await session.commit()
        await session.refresh(new_company)

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear la empresa: {str(e)}")

    return CompanyOnboardResponse(
        company_id=new_company.id,
        company_name=new_company.name,
        admin_email=new_admin.email,
    )


# --- CREATE ---
@router.post("/", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    company: CompanyCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_write)
):
    query = select(Company).where(Company.name == company.name)
    if (await session.exec(query)).first():
        raise HTTPException(status_code=400, detail="Ya existe una empresa con ese nombre.")

    db_company = Company.model_validate(company)
    session.add(db_company)
    await session.commit()
    await session.refresh(db_company)
    return db_company

# --- READ ALL ---
@router.get("/", response_model=List[CompanyRead])
async def read_companies(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read)
):
    # Nunca exponer la empresa plataforma en el listado de empresas cliente
    query = select(Company).where(Company.is_platform == False).offset(offset).limit(limit)

    # Filtro tenant: platform_admin ve todas las empresas cliente, usuario de empresa solo ve la suya
    company_id = get_company_filter(current_user)
    if company_id:
        query = query.where(Company.id == company_id)

    return (await session.exec(query)).all()

# --- READ ONE ---
@router.get("/{company_id}", response_model=CompanyRead)
async def read_company(
    company_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read)
):
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")

    # Un usuario de empresa solo puede ver su propia empresa
    tenant_id = get_company_filter(current_user)
    if tenant_id and company.id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta empresa.")

    return company

# --- UPDATE ---
@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: UUID,
    company_update: CompanyUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_write)
):
    db_company = await session.get(Company, company_id)
    if not db_company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")

    # Un admin de empresa solo puede modificar su propia empresa
    tenant_id = get_company_filter(current_user)
    if tenant_id and db_company.id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta empresa.")

    company_data = company_update.model_dump(exclude_unset=True)

    # Solo platform_admin puede cambiar status e is_platform
    platform_only_fields = {"status", "is_platform"}
    restricted = platform_only_fields.intersection(company_data)
    if restricted and not is_platform_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail=f"Solo el administrador de plataforma puede modificar: {', '.join(restricted)}."
        )

    for key, value in company_data.items():
        setattr(db_company, key, value)

    session.add(db_company)
    await session.commit()
    await session.refresh(db_company)
    return db_company

# --- DELETE ---
@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_delete)
):
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")

    if company.is_platform:
        raise HTTPException(status_code=403, detail="No se puede eliminar la empresa de la plataforma.")

    try:
        await session.delete(company)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar la empresa porque tiene sucursales, usuarios o clientes asociados."
        )
    return None
