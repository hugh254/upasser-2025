from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.database import get_session
from app.models.org import Branch, Company, User
from app.schemas.org import BranchCreate, BranchRead, BranchUpdate
from app.dependencies import PermissionChecker, get_company_filter

router = APIRouter(prefix="/branches",
    tags=["Branches"],
    responses={404: {"description": "Not found"}},)

allow_write  = PermissionChecker("branches", "write")
allow_read   = PermissionChecker("branches", "read")
allow_delete = PermissionChecker("branches", "delete")

# --- CREATE ---
@router.post("/", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
async def create_branch(
    branch: BranchCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_write)
):
    # Validar que el usuario no cree sucursales en otra empresa
    tenant_id = get_company_filter(current_user)
    if tenant_id and branch.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No puedes crear sucursales en otra empresa.")

    company = await session.get(Company, branch.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if company.is_platform:
        raise HTTPException(status_code=403, detail="No se pueden crear sucursales en la empresa de la plataforma.")

    db_branch = Branch.model_validate(branch)
    session.add(db_branch)
    await session.commit()
    await session.refresh(db_branch)
    return db_branch

# --- READ ALL ---
@router.get("/", response_model=List[BranchRead])
async def read_branches(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read)
):
    query = select(Branch).offset(offset).limit(limit)

    # Filtro tenant: platform_admin ve todas, usuario de empresa solo las suyas
    company_id = get_company_filter(current_user)
    if company_id:
        query = query.where(Branch.company_id == company_id)

    return (await session.exec(query)).all()

# --- READ ONE ---
@router.get("/{branch_id}", response_model=BranchRead)
async def read_branch(
    branch_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read)
):
    branch = await session.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada.")

    tenant_id = get_company_filter(current_user)
    if tenant_id and branch.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta sucursal.")

    return branch

# --- UPDATE ---
@router.patch("/{branch_id}", response_model=BranchRead)
async def update_branch(
    branch_id: UUID,
    branch_update: BranchUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_write)
):
    db_branch = await session.get(Branch, branch_id)
    if not db_branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada.")

    tenant_id = get_company_filter(current_user)
    if tenant_id and db_branch.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta sucursal.")

    branch_data = branch_update.model_dump(exclude_unset=True)
    for key, value in branch_data.items():
        setattr(db_branch, key, value)

    session.add(db_branch)
    await session.commit()
    await session.refresh(db_branch)
    return db_branch

# --- DELETE ---
@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(
    branch_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_delete)
):
    branch = await session.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada.")

    tenant_id = get_company_filter(current_user)
    if tenant_id and branch.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta sucursal.")

    await session.delete(branch)
    await session.commit()
    return None