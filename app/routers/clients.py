from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.customers import Client
from app.models.operations import Wallet
from app.models.org import Company, User
from app.schemas.customers import ClientCreate, ClientRead, ClientUpdate
from app.dependencies import PermissionChecker, get_company_filter

router = APIRouter(prefix="/clients",
    tags=["Clients & Customers"],
    responses={404: {"description": "Not found"}},)

# --- CREATE CLIENT (+ Auto-crear Wallet) ---
@router.post("/", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    client_in: ClientCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("clients", "write"))
):
    # 1. Validar que el usuario solo cree clientes dentro de su empresa
    tenant_id = get_company_filter(current_user)
    if tenant_id and client_in.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No puedes crear clientes en otra empresa.")

    # 2. Validar que la empresa exista y no sea la empresa de plataforma
    company = await session.get(Company, client_in.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if company.is_platform:
        raise HTTPException(status_code=403, detail="No se pueden crear clientes en la empresa de la plataforma.")

    # 2. Validar que el email o CI no existan ya (Opcional pero recomendado)
    query_email = select(Client).where(Client.email == client_in.email)
    if (await session.exec(query_email)).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado para otro cliente.")

    # 3. Preparar el Cliente
    db_client = Client.model_validate(client_in)
    session.add(db_client)

    # --- INICIO DE TRANSACCIÓN ---
    try:
        # Hacemos flush para obtener el ID del cliente sin hacer commit definitivo
        await session.flush()

        # ¡MAGIA! Creamos automáticamente su billetera con saldo 0
        new_wallet = Wallet(
            client_id=db_client.id,
            amount=0.00
        )
        session.add(new_wallet)

        # Si todo salió bien, guardamos cliente y billetera al mismo tiempo
        await session.commit()
        await session.refresh(db_client)
        
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear el cliente y su billetera: {str(e)}"
        )
    # --- FIN DE TRANSACCIÓN ---

    return db_client

# --- READ ALL CLIENTS ---
@router.get("/", response_model=List[ClientRead])
async def read_clients(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("clients", "read"))
):
    query = select(Client).offset(offset).limit(limit)

    # Filtro tenant: platform_admin ve todos, usuario de empresa solo los suyos
    company_id = get_company_filter(current_user)
    if company_id:
        query = query.where(Client.company_id == company_id)

    return (await session.exec(query)).all()

# --- READ ONE CLIENT ---
@router.get("/{client_id}", response_model=ClientRead)
async def read_client(
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("clients", "read"))
):
    client = await session.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    tenant_id = get_company_filter(current_user)
    if tenant_id and client.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este cliente.")

    return client

# --- UPDATE CLIENT ---
@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(
    client_id: UUID,
    client_update: ClientUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("clients", "write"))
):
    db_client = await session.get(Client, client_id)
    if not db_client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    tenant_id = get_company_filter(current_user)
    if tenant_id and db_client.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este cliente.")

    client_data = client_update.model_dump(exclude_unset=True)
    for key, value in client_data.items():
        setattr(db_client, key, value)

    session.add(db_client)
    await session.commit()
    await session.refresh(db_client)
    return db_client

# --- DELETE CLIENT ---
@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("clients", "delete"))
):
    client = await session.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    tenant_id = get_company_filter(current_user)
    if tenant_id and client.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este cliente.")

    await session.delete(client)
    await session.commit()
    return None