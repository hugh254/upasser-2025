from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select, update as sql_update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.customers import Credential, Chip, ClientCredential, Client
from app.models.operations import Wallet, Transaction
from app.models.org import Company, User
from app.models.base import AssignmentStatus, WalletType, Status
from app.schemas.customers import (
    CredentialCreate, CredentialRead, CredentialUpdate,
    ChipCreate, ChipRead,
    ClientCredentialCreate, ClientCredentialRead, ClientCredentialActivate,
    CredentialLookupRead,
)
from app.dependencies import PermissionChecker, get_company_filter, require_platform_admin

router = APIRouter(prefix="/credentials",
    tags=["Credenciales y Chips"],
    responses={404: {"description": "Not found"}},)

# ==========================================
# 1. CRUD DE CREDENTIALS (Identidad Lógica)
# ==========================================

@router.post("/", response_model=CredentialRead, status_code=status.HTTP_201_CREATED)
async def create_credential(
    credential_in: CredentialCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("credentials", "write"))
):
    # 1. Validar que no cree credenciales en otra empresa
    tenant_id = get_company_filter(current_user)
    if tenant_id and credential_in.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No puedes crear credenciales en otra empresa.")

    # 2. Validar Empresa
    company = await session.get(Company, credential_in.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="La empresa no existe.")
    if company.is_platform:
        raise HTTPException(status_code=403, detail="No se pueden crear credenciales en la empresa de la plataforma.")

    # 2. Validar Chip (Si es que se está asociando a un chip físico)
    if credential_in.chip_id:
        chip = await session.get(Chip, credential_in.chip_id)
        if not chip:
            raise HTTPException(status_code=404, detail="El Chip físico especificado no existe en inventario.")

    # 3. Validar Duplicados (public_id único)
    query = select(Credential).where(Credential.public_id == credential_in.public_id)
    if (await session.exec(query)).first():
        raise HTTPException(status_code=400, detail="Esta credencial ya está registrada.")

    # 4. Guardar
    db_credential = Credential.model_validate(credential_in)
    session.add(db_credential)
    await session.commit()
    await session.refresh(db_credential)
    return db_credential

# --- LOOKUP POR PUBLIC_ID ---
@router.get("/lookup", response_model=CredentialLookupRead)
async def lookup_credential(
    public_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("credentials", "lookup")),
):
    """
    Consulta rápida por upasser_uuid del chip.
    Devuelve estado de la credencial, assignment_status y saldo de wallet.
    Útil para el cajero antes de recargar un chip anónimo.
    """
    credential = (await session.exec(
        select(Credential).where(Credential.public_id == public_id)
    )).first()
    if not credential:
        raise HTTPException(status_code=404, detail="Credencial no encontrada.")

    company_id = get_company_filter(current_user)
    if company_id and credential.company_id != company_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta credencial.")

    client_cred = (await session.exec(
        select(ClientCredential).where(
            ClientCredential.credential_id == credential.id,
            ClientCredential.state == True,
        )
    )).first()

    wallet_balance = None
    client = None
    if client_cred:
        if client_cred.assignment_status == AssignmentStatus.PENDING:
            wallet = (await session.exec(
                select(Wallet).where(
                    Wallet.client_credential_id == client_cred.id,
                    Wallet.wallet_type == WalletType.MAIN,
                )
            )).first()
        else:
            wallet = (await session.exec(
                select(Wallet).where(
                    Wallet.client_id == client_cred.client_id,
                    Wallet.wallet_type == WalletType.MAIN,
                )
            )).first()
        if wallet:
            wallet_balance = wallet.amount
        if client_cred.client_id:
            client = await session.get(Client, client_cred.client_id)

    return CredentialLookupRead(
        credential_id=credential.id,
        public_id=credential.public_id,
        status=credential.status,
        type=credential.type,
        company_id=credential.company_id,
        chip_id=credential.chip_id,
        assignment_status=client_cred.assignment_status if client_cred else None,
        client_id=client_cred.client_id if client_cred else None,
        client_credential_id=client_cred.id if client_cred else None,
        wallet_balance=wallet_balance,
        client_name=client.name if client else None,
        client_last_name=client.last_name if client else None,
        client_ci=client.ci if client else None,
    )


@router.get("/", response_model=List[CredentialRead])
async def read_credentials(
    offset: int = 0, limit: int = 100,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("credentials", "read"))
):
    query = select(Credential).offset(offset).limit(limit)

    # Filtro tenant: platform_admin ve todas, usuario de empresa solo las suyas
    company_id = get_company_filter(current_user)
    if company_id:
        query = query.where(Credential.company_id == company_id)

    return (await session.exec(query)).all()

# ==========================================
# 2. GESTIÓN DE CHIPS (Inventario Físico)
# ==========================================

@router.post("/chips", response_model=ChipRead, status_code=status.HTTP_201_CREATED)
async def register_chip(
    chip_in: ChipCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin)
):
    # Ya no validamos la credencial. Solo registramos el inventario físico en blanco.
    db_chip = Chip.model_validate(chip_in)
    session.add(db_chip)
    await session.commit()
    await session.refresh(db_chip)
    return db_chip

# ==========================================
# 3. ASIGNACIÓN: CLIENTE <-> CREDENCIAL
# ==========================================

@router.post("/assign", response_model=ClientCredentialRead, status_code=status.HTTP_201_CREATED)
async def assign_credential(
    assignment_in: ClientCredentialCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("credentials", "assign"))
):
    """
    Asigna una credencial. Dos modos:
    - Con client_id (ACTIVE): registro completo en ventanilla normal.
    - Sin client_id (PENDING): venta rápida en hora pico — el titular puede registrarse después.
    """
    # 1. Validar credencial
    credential = await session.get(Credential, assignment_in.credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="La credencial no existe.")

    # 2. Verificar que la credencial pertenece a la empresa del usuario
    company_id = get_company_filter(current_user)
    if company_id and credential.company_id != company_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta credencial.")

    # 3. Verificar que la credencial está activa
    if credential.status != Status.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"La credencial no está activa (estado: {credential.status.value})."
        )

    # 4. Determinar assignment_status y validar cliente
    if assignment_in.client_id:
        client = await session.get(Client, assignment_in.client_id)
        if not client:
            raise HTTPException(status_code=404, detail="El cliente no existe.")
        if client.company_id != credential.company_id:
            raise HTTPException(
                status_code=400,
                detail="El cliente y la credencial deben pertenecer a la misma empresa."
            )
        assignment_status = AssignmentStatus.ACTIVE
    else:
        assignment_status = AssignmentStatus.PENDING

    # 5. Validar que la credencial no esté ya asignada y activa
    if (await session.exec(
        select(ClientCredential).where(
            ClientCredential.credential_id == assignment_in.credential_id,
            ClientCredential.state == True
        )
    )).first():
        raise HTTPException(status_code=400, detail="Esta credencial ya está asignada y activa.")

    try:
        db_assignment = ClientCredential(
            client_id=assignment_in.client_id,
            credential_id=assignment_in.credential_id,
            assignment_status=assignment_status,
            state=True,
        )
        session.add(db_assignment)
        await session.flush()

        if assignment_status == AssignmentStatus.PENDING:
            session.add(Wallet(
                client_credential_id=db_assignment.id,
                wallet_type=WalletType.MAIN,
                amount=0
            ))

        await session.commit()
        await session.refresh(db_assignment)

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear la asignación: {str(e)}")

    return db_assignment


@router.patch("/assign/{assignment_id}/activate", response_model=ClientCredentialRead)
async def activate_assignment(
    assignment_id: UUID,
    body: ClientCredentialActivate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("credentials", "activate"))
):
    """
    Vincula un cliente registrado a una credencial anónima (PENDING → ACTIVE).
    Transfiere el saldo de la wallet anónima a la wallet principal del cliente.
    """
    # 1. Obtener la asignación
    assignment = await session.get(ClientCredential, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada.")

    if assignment.assignment_status == AssignmentStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Esta credencial ya está activada.")

    # 2. Verificar tenant: la credencial de la asignación debe pertenecer a la empresa del usuario
    credential = await session.get(Credential, assignment.credential_id)
    company_id = get_company_filter(current_user)
    if company_id and credential.company_id != company_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta asignación.")

    # 3. Validar que el cliente exista y pertenezca a la misma empresa
    client = await session.get(Client, body.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="El cliente no existe.")
    if client.company_id != credential.company_id:
        raise HTTPException(
            status_code=400,
            detail="El cliente debe pertenecer a la misma empresa que la credencial."
        )

    # 3. Obtener wallet anónima (ligada a la credencial)
    anon_wallet = (await session.exec(
        select(Wallet).where(
            Wallet.client_credential_id == assignment.id,
            Wallet.wallet_type == WalletType.MAIN
        )
    )).first()

    # 4. Obtener o crear wallet del cliente
    client_wallet = (await session.exec(
        select(Wallet).where(
            Wallet.client_id == body.client_id,
            Wallet.wallet_type == WalletType.MAIN
        )
    )).first()

    try:
        # 5. Transferir saldo si hay wallet anónima con saldo
        if anon_wallet:
            if client_wallet:
                client_wallet.amount += anon_wallet.amount
                session.add(client_wallet)
            else:
                # Reconvertir la wallet anónima en la wallet oficial del cliente
                anon_wallet.client_id = body.client_id
                anon_wallet.client_credential_id = None
                session.add(anon_wallet)
            await session.flush()

            # Eliminar wallet anónima solo si el cliente ya tenía su propia wallet.
            # Primero reasignar sus transacciones para no violar la check constraint
            # (SQLAlchemy ORM pone wallet_id=NULL antes del DELETE, lo que dispara
            # "transaction_wallet_or_ticket_required" aunque la FK tenga RESTRICT).
            if client_wallet:
                await session.exec(
                    sql_update(Transaction)
                    .where(Transaction.wallet_id == anon_wallet.id)
                    .values(wallet_id=client_wallet.id)
                )
                await session.flush()
                await session.delete(anon_wallet)
                await session.flush()

        # 6. Activar la asignación
        assignment.client_id = body.client_id
        assignment.assignment_status = AssignmentStatus.ACTIVE
        session.add(assignment)

        await session.commit()
        await session.refresh(assignment)

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Error al activar la asignación: {str(e)}")

    return assignment