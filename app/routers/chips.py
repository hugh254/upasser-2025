import csv
import io
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.models.customers import Chip, Credential, ClientCredential
from app.models.operations import Wallet
from app.models.org import Company, User
from app.models.base import BatchStatus, CredentialType, Status, WalletType, AssignmentStatus
from app.schemas.customers import (
    ChipCreate, ChipRead, ChipUpdate,
    BatchAssignRequest, BatchActivateRequest, BatchAssignResult, BatchActivateResult,
)
from app.dependencies import get_company_filter, PermissionChecker, require_platform_admin

router = APIRouter(
    prefix="/chips",
    tags=["Chips"],
    responses={404: {"description": "Not found"}},
)

allow_read = PermissionChecker("chips", "read")


# --- IMPORT CSV ---
@router.post("/import", status_code=status.HTTP_200_OK)
async def import_chips_csv(
    file: UploadFile = File(...),
    company_id: Optional[UUID] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin),
):
    if not (file.filename or "").endswith(".csv"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .csv")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="El archivo debe estar codificado en UTF-8.")

    reader = csv.DictReader(io.StringIO(text))

    required_columns = {"nro_batch", "physical_uuid", "upasser_uuid"}
    if not required_columns.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"El CSV debe tener las columnas: {', '.join(sorted(required_columns))}",
        )

    # Prefetch UUIDs existentes para detección rápida de duplicados en memoria
    existing_physical: set = set((await session.exec(select(Chip.physical_uuid))).all())
    existing_upasser: set = set((await session.exec(select(Chip.upasser_uuid))).all())

    chips_to_insert: List[Chip] = []
    errors = []
    seen_physical: set = set()
    seen_upasser: set = set()

    for i, row in enumerate(reader, start=2):  # fila 1 = encabezado
        nro_batch     = (row.get("nro_batch")     or "").strip()
        physical_uuid = (row.get("physical_uuid") or "").strip()
        upasser_uuid  = (row.get("upasser_uuid")  or "").strip()
        raw_company   = (row.get("company_id")    or "").strip()
        raw_status    = (row.get("batch_status")  or "").strip().upper()

        # Validar campos requeridos
        if not nro_batch or not physical_uuid or not upasser_uuid:
            errors.append({"row": i, "reason": "nro_batch, physical_uuid y upasser_uuid son requeridos"})
            continue

        # Duplicados dentro del mismo lote
        if physical_uuid in seen_physical:
            errors.append({"row": i, "physical_uuid": physical_uuid, "reason": "physical_uuid duplicado en el lote"})
            continue
        if upasser_uuid in seen_upasser:
            errors.append({"row": i, "upasser_uuid": upasser_uuid, "reason": "upasser_uuid duplicado en el lote"})
            continue

        # Duplicados en la BD
        if physical_uuid in existing_physical:
            errors.append({"row": i, "physical_uuid": physical_uuid, "reason": "physical_uuid ya existe en la base de datos"})
            continue
        if upasser_uuid in existing_upasser:
            errors.append({"row": i, "upasser_uuid": upasser_uuid, "reason": "upasser_uuid ya existe en la base de datos"})
            continue

        # Resolver company_id: columna CSV > query param > NULL
        resolved_company_id: Optional[UUID] = None
        if raw_company:
            try:
                resolved_company_id = UUID(raw_company)
            except ValueError:
                errors.append({"row": i, "reason": f"company_id inválido: {raw_company}"})
                continue
        elif company_id:
            resolved_company_id = company_id

        # batch_status opcional (default AVAILABLE)
        batch_status = BatchStatus.AVAILABLE
        if raw_status:
            try:
                batch_status = BatchStatus(raw_status)
            except ValueError:
                errors.append({"row": i, "reason": f"batch_status inválido: {raw_status}. Valores válidos: {[e.value for e in BatchStatus]}"})
                continue

        seen_physical.add(physical_uuid)
        seen_upasser.add(upasser_uuid)
        chips_to_insert.append(Chip(
            nro_batch=nro_batch,
            physical_uuid=physical_uuid,
            upasser_uuid=upasser_uuid,
            company_id=resolved_company_id,
            batch_status=batch_status,
        ))

    if chips_to_insert:
        session.add_all(chips_to_insert)
        await session.commit()

    return {
        "inserted": len(chips_to_insert),
        "errors": errors,
    }


# --- ASSIGN BATCH TO COMPANY ---
@router.post("/assign-batch", response_model=BatchAssignResult, status_code=status.HTTP_200_OK)
async def assign_batch_to_company(
    req: BatchAssignRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin),
):
    """
    Transfiere chips del pool de Upasser (company_id NULL, AVAILABLE) a una empresa.
    Operación comercial/logística: equivale a entregar físicamente el lote a la empresa.
    El batch_status permanece AVAILABLE hasta que se ejecute activate-batch.
    """
    company = await session.get(Company, req.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if company.is_platform:
        raise HTTPException(status_code=403, detail="No se puede asignar chips a la empresa de la plataforma.")

    unassigned = (await session.exec(
        select(Chip).where(
            Chip.nro_batch == req.nro_batch,
            Chip.company_id == None,
            Chip.batch_status == BatchStatus.AVAILABLE,
        )
    )).all()

    all_in_batch = (await session.exec(
        select(Chip).where(Chip.nro_batch == req.nro_batch)
    )).all()

    for chip in unassigned:
        chip.company_id = req.company_id
        session.add(chip)

    await session.commit()

    return BatchAssignResult(
        assigned=len(unassigned),
        skipped=len(all_in_batch) - len(unassigned),
    )


# --- ACTIVATE BATCH FOR COMPANY ---
@router.post("/activate-batch", response_model=BatchActivateResult, status_code=status.HTTP_200_OK)
async def activate_batch_for_company(
    req: BatchActivateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin),
):
    """
    Activa los chips de un lote ya asignados a la empresa: crea Credential (NFC) +
    ClientCredential (PENDING) + Wallet anónima por cada chip.
    Tras esto el chip es operable en el scan aunque aún no tenga cliente registrado.
    """
    company = await session.get(Company, req.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if company.is_platform:
        raise HTTPException(status_code=403, detail="No se puede activar chips en la empresa de la plataforma.")

    chips = (await session.exec(
        select(Chip).where(
            Chip.nro_batch == req.nro_batch,
            Chip.company_id == req.company_id,
            Chip.batch_status == BatchStatus.AVAILABLE,
        )
    )).all()

    if not chips:
        raise HTTPException(
            status_code=404,
            detail=f"No hay chips disponibles para activar en el lote '{req.nro_batch}' de esta empresa. "
                   "Verifique que el lote esté asignado con assign-batch primero.",
        )

    # Pre-filtrar chips que ya tienen credencial vinculada
    already_credentialed = (await session.exec(
        select(Credential).where(
            Credential.chip_id.in_([c.id for c in chips])
        )
    )).all()
    skip_ids = {c.chip_id for c in already_credentialed}

    to_activate = [c for c in chips if c.id not in skip_ids]
    skipped = len(chips) - len(to_activate)

    try:
        for chip in to_activate:
            credential = Credential(
                type=CredentialType.NFC,
                public_id=chip.physical_uuid,
                secret_data=chip.upasser_uuid,
                status=Status.ACTIVE,
                company_id=req.company_id,
                chip_id=chip.id,
            )
            session.add(credential)
            await session.flush()

            client_cred = ClientCredential(
                credential_id=credential.id,
                client_id=None,
                state=True,
                assignment_status=AssignmentStatus.PENDING,
            )
            session.add(client_cred)
            await session.flush()

            session.add(Wallet(
                client_credential_id=client_cred.id,
                wallet_type=WalletType.MAIN,
                amount=0,
            ))

            chip.batch_status = BatchStatus.ASSIGNED
            session.add(chip)

        await session.commit()

    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Error de integridad al activar el lote. Puede que algún upasser_uuid ya exista como credencial.",
        )

    return BatchActivateResult(activated=len(to_activate), skipped=skipped)


# --- CREATE ---
@router.post("/", response_model=ChipRead, status_code=status.HTTP_201_CREATED)
async def create_chip(
    chip_in: ChipCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin),
):
    for field, value in [("physical_uuid", chip_in.physical_uuid), ("upasser_uuid", chip_in.upasser_uuid)]:
        existing = (await session.exec(
            select(Chip).where(getattr(Chip, field) == value)
        )).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Ya existe un chip con ese {field}.")

    db_chip = Chip.model_validate(chip_in)
    session.add(db_chip)
    await session.commit()
    await session.refresh(db_chip)
    return db_chip


# --- READ ALL ---
@router.get("/", response_model=List[ChipRead])
async def read_chips(
    offset: int = 0,
    limit: int = 100,
    batch_status: Optional[BatchStatus] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read),
):
    query = select(Chip).offset(offset).limit(limit)

    company_id = get_company_filter(current_user)
    if company_id:
        query = query.where(Chip.company_id == company_id)
    if batch_status:
        query = query.where(Chip.batch_status == batch_status)

    return (await session.exec(query)).all()


# --- READ ONE ---
@router.get("/{chip_id}", response_model=ChipRead)
async def read_chip(
    chip_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_read),
):
    chip = await session.get(Chip, chip_id)
    if not chip:
        raise HTTPException(status_code=404, detail="Chip no encontrado.")

    company_id = get_company_filter(current_user)
    if company_id and chip.company_id != company_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este chip.")

    return chip


# --- UPDATE ---
@router.patch("/{chip_id}", response_model=ChipRead)
async def update_chip(
    chip_id: UUID,
    chip_update: ChipUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin),
):
    chip = await session.get(Chip, chip_id)
    if not chip:
        raise HTTPException(status_code=404, detail="Chip no encontrado.")

    update_data = chip_update.model_dump(exclude_unset=True)

    # Verificar unicidad si se actualizan los UUIDs
    for field in ("physical_uuid", "upasser_uuid"):
        if field in update_data:
            conflict = (await session.exec(
                select(Chip).where(getattr(Chip, field) == update_data[field])
            )).first()
            if conflict and conflict.id != chip.id:
                raise HTTPException(status_code=400, detail=f"Ya existe un chip con ese {field}.")

    for key, value in update_data.items():
        setattr(chip, key, value)

    session.add(chip)
    await session.commit()
    await session.refresh(chip)
    return chip


# --- DELETE ---
@router.delete("/{chip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chip(
    chip_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin),
):
    chip = await session.get(Chip, chip_id)
    if not chip:
        raise HTTPException(status_code=404, detail="Chip no encontrado.")

    if chip.batch_status != BatchStatus.AVAILABLE:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar un chip con estado '{chip.batch_status.value}'. Solo se pueden eliminar chips AVAILABLE."
        )

    try:
        await session.delete(chip)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el chip porque tiene credenciales asociadas."
        )
    return None
