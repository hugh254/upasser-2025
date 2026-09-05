from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime, timezone
from uuid import UUID

from app.database import get_session
from app.models.base import AccessResult, WalletType, AssignmentStatus, TicketStatus
from app.models.operations import Wallet, Transaction, Access, Type
from app.models.customers import Credential, ClientCredential, Ticket
from app.models.iot import Device, Gate
from app.models.org import User
from app.schemas.operations import RechargeRequest, IoTScanRequest, RechargeAnonymousRequest, TypeRead
from app.dependencies import PermissionChecker, get_company_filter

router = APIRouter(prefix="/operations",
    tags=["Operaciones & IoT Gateway"],
    responses={404: {"description": "Not found"}},)


# ==========================================
# 0. TIPOS DE TRANSACCIÓN
# ==========================================
@router.get("/types", response_model=List[TypeRead])
async def list_types(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("operations", "types_read")),
):
    return (await session.exec(select(Type))).all()


# ==========================================
# 1. RECARGA DE SALDO (Cash-in en ventanilla)
# ==========================================
@router.post("/recharge", status_code=status.HTTP_200_OK)
async def recharge_wallet(
    req: RechargeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("operations", "recharge"))
):
    # 1. Buscar la billetera principal del cliente
    query_wallet = select(Wallet).where(
        Wallet.client_id == req.client_id,
        Wallet.wallet_type == WalletType.MAIN
    )
    wallet = (await session.exec(query_wallet)).first()
    
    if not wallet:
        raise HTTPException(status_code=404, detail="Billetera no encontrada para este cliente.")

    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")

    # --- INICIO TRANSACCIÓN ACID ---
    try:
        # Aumentar saldo
        wallet.amount += req.amount
        session.add(wallet)
        await session.flush() # Sincronizamos sin hacer commit definitivo

        # Registrar la transacción histórica
        new_tx = Transaction(
            wallet_id=wallet.id,
            type_id=req.type_id,
            amount=req.amount,
            # Aquí podrías guardar el ID del cajero que hizo la recarga
        )
        session.add(new_tx)
        
        await session.commit()
        await session.refresh(wallet)
        
        return {"message": "Recarga exitosa", "new_balance": wallet.amount}
        
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Error en la recarga: {str(e)}")


# ==========================================
# 2. RECARGA WALLET ANÓNIMA (chip sin titular registrado)
# ==========================================
@router.post("/recharge-anonymous", status_code=status.HTTP_200_OK)
async def recharge_anonymous_credential(
    req: RechargeAnonymousRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(PermissionChecker("operations", "recharge_anonymous")),
):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")

    credential = (await session.exec(
        select(Credential).where(Credential.public_id == req.credential_public_id)
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
            ClientCredential.assignment_status == AssignmentStatus.PENDING,
        )
    )).first()
    if not client_cred:
        raise HTTPException(
            status_code=400,
            detail="Esta credencial no tiene asignación anónima activa. "
                   "Si ya tiene titular registrado, usa el endpoint de recarga estándar.",
        )

    wallet = (await session.exec(
        select(Wallet).where(
            Wallet.client_credential_id == client_cred.id,
            Wallet.wallet_type == WalletType.MAIN,
        ).with_for_update()
    )).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Billetera anónima no encontrada.")

    try:
        wallet.amount += req.amount
        session.add(wallet)
        await session.flush()

        session.add(Transaction(
            wallet_id=wallet.id,
            type_id=req.type_id,
            amount=req.amount,
            client_credential_id=client_cred.id,
        ))

        await session.commit()
        await session.refresh(wallet)

        return {
            "message": "Recarga exitosa",
            "credential_public_id": credential.public_id,
            "new_balance": wallet.amount,
        }

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Error en la recarga: {str(e)}")


# ==========================================
# 3. EL MOTOR IoT (Pase de tarjeta en Torniquete)
# ==========================================
@router.post("/scan", status_code=status.HTTP_200_OK)
async def process_iot_scan(
    scan: IoTScanRequest,
    session: AsyncSession = Depends(get_session)
):
    # 1. Identificar el hardware (¿Qué puerta es y cuánto cobra?)
    device = (await session.exec(
        select(Device).where(Device.mac_address == scan.mac_address)
    )).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo IoT no reconocido.")

    gate = (await session.exec(
        select(Gate).where(Gate.device_id == device.id)
    )).first()
    if not gate:
        raise HTTPException(status_code=400, detail="El dispositivo no está asignado a ninguna puerta.")

    async def _deny(reason: str, *, credential_id=None, ticket_id=None) -> None:
        """Persiste un Access DENIED. Los errores se silencian para no ocultar la excepción original."""
        try:
            session.add(Access(
                gate_id=gate.id,
                result=AccessResult.DENIED,
                reason=reason,
                client_credential_id=credential_id,
                ticket_id=ticket_id,
            ))
            await session.commit()
        except Exception:
            await session.rollback()

    # ─── FLUJO A: Credencial persistente (NFC, QR de cliente, BLE) ──────────
    credential = (await session.exec(
        select(Credential).where(Credential.public_id == scan.nfc_uid)
    )).first()

    if credential:
        assignment = (await session.exec(
            select(ClientCredential).where(
                ClientCredential.credential_id == credential.id,
                ClientCredential.state == True
            )
        )).first()
        if not assignment:
            raise HTTPException(status_code=403, detail="Credencial inactiva o no asignada.")

        # Wallet según si el titular está registrado (ACTIVE) o es anónimo (PENDING)
        if assignment.assignment_status == AssignmentStatus.ACTIVE:
            wallet_query = select(Wallet).where(
                Wallet.client_id == assignment.client_id,
                Wallet.wallet_type == WalletType.MAIN
            ).with_for_update()
        else:
            wallet_query = select(Wallet).where(
                Wallet.client_credential_id == assignment.id,
                Wallet.wallet_type == WalletType.MAIN
            ).with_for_update()

        wallet = (await session.exec(wallet_query)).first()
        if not wallet:
            await _deny("Billetera no encontrada", credential_id=assignment.id)
            raise HTTPException(status_code=404, detail="No se encontró billetera para esta credencial.")

        if wallet.amount < gate.price:
            await _deny(
                f"Saldo insuficiente: {wallet.amount} < {gate.price}",
                credential_id=assignment.id
            )
            raise HTTPException(
                status_code=402,
                detail={"message": "Saldo insuficiente", "balance": wallet.amount, "required": gate.price}
            )

        tx_type = None
        if gate.price > 0:
            tx_type = (await session.exec(select(Type).where(Type.name == "COBRO_ACCESO"))).first()
            if not tx_type:
                raise HTTPException(status_code=500, detail="Falta configurar el tipo de transacción 'COBRO_ACCESO'.")

        try:
            if gate.price > 0:
                wallet.amount -= gate.price
                session.add(wallet)
                await session.flush()

            new_access = Access(
                client_credential_id=assignment.id,
                gate_id=gate.id,
                result=AccessResult.GRANTED,
                reason="Saldo suficiente"
            )
            session.add(new_access)
            await session.flush()

            if tx_type:
                session.add(Transaction(
                    wallet_id=wallet.id,
                    type_id=tx_type.id,
                    amount=-gate.price,
                    access_id=new_access.id,
                    client_credential_id=assignment.id
                ))
            await session.commit()
            await session.refresh(wallet)

            return {"authorized": True, "message": "Bienvenido", "new_balance": wallet.amount}

        except Exception:
            await session.rollback()
            raise HTTPException(status_code=500, detail="Fallo en la transacción. No se descontó saldo.")

    # ─── FLUJO B: Ticket QR de un solo uso ───────────────────────────────────
    ticket = (await session.exec(
        select(Ticket).where(Ticket.qr_code == scan.nfc_uid)
    )).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Credencial o ticket no reconocido.")

    if ticket.status != TicketStatus.AVAILABLE:
        await _deny(f"Ticket no disponible: {ticket.status.value}", ticket_id=ticket.id)
        raise HTTPException(status_code=403, detail=f"Ticket no disponible: {ticket.status.value}.")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if ticket.expires_at and ticket.expires_at < now:
        await _deny("Ticket expirado", ticket_id=ticket.id)
        raise HTTPException(status_code=403, detail="Ticket expirado.")

    if ticket.zone_id and ticket.zone_id != gate.zone_id:
        await _deny("Ticket no válido para esta zona", ticket_id=ticket.id)
        raise HTTPException(status_code=403, detail="Ticket no válido para esta zona.")

    if ticket.amount is not None and ticket.amount < gate.price:
        await _deny(
            f"Saldo de ticket insuficiente: {ticket.amount} < {gate.price}",
            ticket_id=ticket.id
        )
        raise HTTPException(
            status_code=402,
            detail={"message": "Saldo del ticket insuficiente", "balance": ticket.amount, "required": gate.price}
        )

    # Solo se registra transacción si la puerta cobra y el ticket tiene monto
    tx_type = None
    if gate.price > 0 and ticket.amount is not None:
        tx_type = (await session.exec(select(Type).where(Type.name == "COBRO_ACCESO"))).first()
        if not tx_type:
            raise HTTPException(status_code=500, detail="Falta configurar el tipo de transacción 'COBRO_ACCESO'.")

    try:
        ticket.status = TicketStatus.USED
        ticket.used_at = now
        session.add(ticket)
        await session.flush()

        new_access = Access(
            ticket_id=ticket.id,
            gate_id=gate.id,
            result=AccessResult.GRANTED,
            reason="Ticket válido"
        )
        session.add(new_access)
        await session.flush()

        if tx_type:
            session.add(Transaction(
                ticket_id=ticket.id,
                type_id=tx_type.id,
                amount=-gate.price,
                access_id=new_access.id
            ))

        await session.commit()
        return {"authorized": True, "message": "Bienvenido", "ticket_used": True}

    except Exception:
        await session.rollback()
        raise HTTPException(status_code=500, detail="Fallo al procesar el ticket.")