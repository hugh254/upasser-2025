import secrets
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.models.customers import Ticket
from app.models.org import Company, User
from app.models.base import TicketStatus, ExpirationUnit
from app.schemas.customers import TicketCreate, TicketRead, TicketUpdate
from app.dependencies import PermissionChecker, get_company_filter

router = APIRouter(
    prefix="/tickets",
    tags=["Tickets"],
    responses={404: {"description": "Not found"}},
)

allow_write  = PermissionChecker("tickets", "write")
allow_manage = PermissionChecker("tickets", "manage")
allow_delete = PermissionChecker("tickets", "delete")
allow_read   = PermissionChecker("tickets", "read")


# --- CREATE ---
@router.post("/", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    ticket: TicketCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_write),
):
    # Validar empresa
    tenant_id = get_company_filter(current_user)
    if tenant_id and ticket.company_id != tenant_id:
        raise HTTPException(status_code=403, detail="No puedes crear tickets en otra empresa.")

    company = await session.get(Company, ticket.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if company.is_platform:
        raise HTTPException(status_code=403, detail="No se pueden crear tickets en la empresa de la plataforma.")

    while True:
        qr_code = secrets.token_urlsafe(16)
        existing = (await session.exec(
            select(Ticket).where(Ticket.qr_code == qr_code)
        )).first()
        if not existing:
            break

    # Auto-calcular expires_at desde la configuración de la empresa si no viene en el request
    if ticket.expires_at is None and company.ticket_expiration_value and company.ticket_expiration_unit:
        if company.ticket_expiration_unit == ExpirationUnit.DAYS:
            delta = timedelta(days=company.ticket_expiration_value)
        else:
            delta = timedelta(hours=company.ticket_expiration_value)
        ticket.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + delta

    # Normalizar expires_at a timezone-naive (columna es TIMESTAMP WITHOUT TIME ZONE)
    if ticket.expires_at and ticket.expires_at.tzinfo is not None:
        ticket.expires_at = ticket.expires_at.replace(tzinfo=None)

    db_ticket = Ticket.model_validate(ticket, update={"qr_code": qr_code})
    session.add(db_ticket)
    await session.commit()
    await session.refresh(db_ticket)
    return db_ticket


# --- READ ALL ---
@router.get("/", response_model=List[TicketRead])
async def read_tickets(
    offset: int = 0,
    limit: int = 100,
    status_filter: Optional[TicketStatus] = None,
    zone_id: Optional[UUID] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_manage),
):
    query = select(Ticket).offset(offset).limit(limit)

    company_id = get_company_filter(current_user)
    if company_id:
        query = query.where(Ticket.company_id == company_id)
    if status_filter:
        query = query.where(Ticket.status == status_filter)
    if zone_id:
        query = query.where(Ticket.zone_id == zone_id)

    return (await session.exec(query)).all()


# --- READ ONE ---
@router.get("/{ticket_id}", response_model=TicketRead)
async def read_ticket(
    ticket_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_manage),
):
    ticket = await session.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    company_id = get_company_filter(current_user)
    if company_id and ticket.company_id != company_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este ticket.")

    return ticket


# --- UPDATE (cancelar, cambiar expiración) ---
@router.patch("/{ticket_id}", response_model=TicketRead)
async def update_ticket(
    ticket_id: UUID,
    ticket_update: TicketUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_manage),
):
    ticket = await session.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    company_id = get_company_filter(current_user)
    if company_id and ticket.company_id != company_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este ticket.")

    if ticket.status == TicketStatus.USED:
        raise HTTPException(status_code=400, detail="No se puede modificar un ticket ya canjeado.")

    update_data = ticket_update.model_dump(exclude_unset=True)
    if "expires_at" in update_data and update_data["expires_at"] and update_data["expires_at"].tzinfo is not None:
        update_data["expires_at"] = update_data["expires_at"].replace(tzinfo=None)

    for key, value in update_data.items():
        setattr(ticket, key, value)

    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


# --- DELETE ---
@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    ticket_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(allow_delete),
):
    ticket = await session.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    company_id = get_company_filter(current_user)
    if company_id and ticket.company_id != company_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este ticket.")

    if ticket.status == TicketStatus.USED:
        raise HTTPException(status_code=400, detail="No se puede eliminar un ticket ya canjeado.")

    try:
        await session.delete(ticket)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el ticket porque tiene registros de acceso asociados."
        )
    return None
