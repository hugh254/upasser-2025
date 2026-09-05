import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from sqlmodel import select

from app.database import async_session
from app.security import get_password_hash
from app.models.org import Company, Branch, Role, User, RoleUserLink, Permission, RolePermissionLink
from app.models.iot import Zone, Device, Gate
from app.models.customers import Client, Chip, Credential, ClientCredential, Ticket
from app.models.operations import Wallet, Type
from app.models.base import (
    Status, CredentialType, BatchStatus,
    Direction, WalletType, RoleScope, AssignmentStatus, TicketStatus
)


async def seed():
    async with async_session() as session:

        # ── IDEMPOTENCIA ─────────────────────────────────────────────
        existing = (await session.exec(
            select(Company).where(Company.name == "Upasser")
        )).first()

        if existing:
            print("⚠️  Seeds ya aplicados, omitiendo.")
            return

        # ── 1. EMPRESA DE PLATAFORMA (Upasser) ───────────────────────
        upasser_company = Company(
            name="Upasser",
            description="Empresa operadora de la plataforma Upasser",
            status=Status.ACTIVE,
            is_platform=True
        )
        session.add(upasser_company)
        await session.flush()

        # ── 2. ROLES ─────────────────────────────────────────────────
        platform_admin_role = Role(name="platform_admin", scope=RoleScope.PLATFORM, is_system=True)
        admin_role   = Role(name="admin",   scope=RoleScope.COMPANY, is_system=True)
        manager_role = Role(name="manager", scope=RoleScope.COMPANY, is_system=True)
        cajero_role  = Role(name="cajero",  scope=RoleScope.COMPANY, is_system=True)
        session.add_all([platform_admin_role, admin_role, manager_role, cajero_role])
        await session.flush()

        # ── 3. USUARIO SUPER ADMIN DE PLATAFORMA ─────────────────────
        platform_user = User(
            name="Super",
            last_name="Admin",
            email="admin@upasser.io",
            password=get_password_hash("upasser_admin_2025"),
            company_id=upasser_company.id
        )
        session.add(platform_user)
        await session.flush()

        session.add(RoleUserLink(user_id=platform_user.id, role_id=platform_admin_role.id))
        await session.flush()

        # ── 3b. PERMISOS Y ASIGNACIÓN POR ROL ────────────────────────
        # Definición del inventario completo de permisos del sistema
        perms_def = [
            # companies
            ("companies",    "read",              "Listar y ver empresas"),
            ("companies",    "write",             "Crear y editar empresas"),
            ("companies",    "delete",            "Eliminar empresas"),
            ("companies",    "onboard",           "Alta de empresa con admin inicial"),
            # users
            ("users",        "read",              "Listar y ver usuarios"),
            ("users",        "write",             "Crear y editar usuarios"),
            ("users",        "delete",            "Eliminar usuarios"),
            # clients
            ("clients",      "read",              "Listar y ver clientes"),
            ("clients",      "write",             "Crear y editar clientes"),
            ("clients",      "delete",            "Eliminar clientes"),
            # branches
            ("branches",     "read",              "Listar y ver sucursales"),
            ("branches",     "write",             "Crear y editar sucursales"),
            ("branches",     "delete",            "Eliminar sucursales"),
            # credentials
            ("credentials",  "read",              "Listar y ver credenciales"),
            ("credentials",  "write",             "Crear y editar credenciales"),
            ("credentials",  "delete",            "Eliminar credenciales"),
            ("credentials",  "lookup",            "Consulta rápida de credencial por UID"),
            ("credentials",  "assign",            "Asignar credencial a cliente"),
            ("credentials",  "activate",          "Activar asignación de credencial"),
            # chips (solo lectura para roles COMPANY; operaciones de escritura son platform_admin exclusivo)
            ("chips",        "read",              "Listar y ver chips"),
            # devices
            ("devices",      "read",              "Listar y ver dispositivos IoT"),
            ("devices",      "write",             "Crear y editar dispositivos IoT"),
            ("devices",      "delete",            "Eliminar dispositivos IoT"),
            # zones
            ("zones",        "read",              "Listar y ver zonas"),
            ("zones",        "write",             "Crear y editar zonas"),
            ("zones",        "delete",            "Eliminar zonas"),
            # gates
            ("gates",        "read",              "Listar y ver puertas/torniquetes"),
            ("gates",        "write",             "Crear y editar puertas/torniquetes"),
            ("gates",        "delete",            "Eliminar puertas/torniquetes"),
            # operations
            ("operations",   "recharge",          "Recargar saldo de cliente registrado"),
            ("operations",   "recharge_anonymous","Recargar saldo de tarjeta anónima"),
            ("operations",   "types_read",        "Ver tipos de transacción disponibles"),
            # tickets
            ("tickets",      "read",              "Listar y ver tickets QR"),
            ("tickets",      "write",             "Crear tickets QR"),
            ("tickets",      "manage",            "Editar y cancelar tickets QR"),
            ("tickets",      "delete",            "Eliminar tickets QR"),
            # roles & permissions
            ("roles",        "read",              "Listar roles y sus permisos"),
            ("roles",        "assign",            "Asignar roles a usuarios"),
            ("permissions",  "read",              "Listar permisos del sistema"),
            ("permissions",  "assign",            "Asignar permisos a roles o usuarios"),
        ]

        perms: dict[str, Permission] = {}
        for resource, action, description in perms_def:
            p = Permission(resource=resource, action=action, description=description)
            session.add(p)
            perms[f"{resource}:{action}"] = p
        await session.flush()

        # Permisos por rol — platform_admin tiene bypass total (scope=PLATFORM),
        # los roles COMPANY reciben solo lo que corresponde a su función.
        role_perms: dict[str, list[str]] = {
            "admin": [
                "companies:read", "companies:write",
                "users:read", "users:write", "users:delete",
                "clients:read", "clients:write", "clients:delete",
                "branches:read", "branches:write", "branches:delete",
                "credentials:read", "credentials:write", "credentials:delete",
                "credentials:lookup", "credentials:assign", "credentials:activate",
                "chips:read",
                "devices:read", "devices:write",
                "zones:read", "zones:write", "zones:delete",
                "gates:read", "gates:write",
                "operations:recharge", "operations:recharge_anonymous", "operations:types_read",
                "tickets:read", "tickets:write", "tickets:manage", "tickets:delete",
                "roles:read", "roles:assign",
                "permissions:read", "permissions:assign",
            ],
            "manager": [
                "companies:read",
                "clients:read", "clients:write",
                "branches:read",
                "credentials:read", "credentials:write",
                "credentials:lookup", "credentials:assign", "credentials:activate",
                "chips:read",
                "devices:read", "devices:write",
                "zones:read", "zones:write",
                "gates:read", "gates:write",
                "operations:recharge", "operations:recharge_anonymous", "operations:types_read",
                "tickets:read", "tickets:write", "tickets:manage",
                "roles:read",
                "permissions:read",
            ],
            "cajero": [
                "credentials:lookup", "credentials:assign", "credentials:activate",
                "operations:recharge", "operations:recharge_anonymous", "operations:types_read",
                "tickets:read", "tickets:write",
            ],
        }

        role_map = {
            "admin":   admin_role,
            "manager": manager_role,
            "cajero":  cajero_role,
        }

        for role_name, perm_keys in role_perms.items():
            role = role_map[role_name]
            for key in perm_keys:
                session.add(RolePermissionLink(role_id=role.id, permission_id=perms[key].id))
        await session.flush()

        # ── 4. EMPRESA DEMO (cliente de prueba) ──────────────────────
        company = Company(
            name="Empresa Demo",
            description="Empresa para pruebas locales",
            status=Status.ACTIVE
        )
        session.add(company)
        await session.flush()

        # ── 5. BRANCH ────────────────────────────────────────────────
        branch = Branch(
            name="Sucursal Central",
            description="Sede principal",
            address="Av. Principal 123",
            city="La Paz",
            is_main=True,
            status=Status.ACTIVE,
            company_id=company.id
        )
        session.add(branch)
        await session.flush()

        # ── 6. USER ADMIN DE EMPRESA DEMO ────────────────────────────
        admin_user = User(
            name="Admin",
            last_name="Demo",
            email="admin@empresademo.com",
            password=get_password_hash("admin123"),
            company_id=company.id
        )
        session.add(admin_user)
        await session.flush()

        session.add(RoleUserLink(user_id=admin_user.id, role_id=admin_role.id))
        await session.flush()

        # ── 7. USER MANAGER DE EMPRESA DEMO ──────────────────────────
        manager_user = User(
            name="Manager",
            last_name="Demo",
            email="manager@empresademo.com",
            password=get_password_hash("manager123"),
            company_id=company.id
        )
        session.add(manager_user)
        await session.flush()

        session.add(RoleUserLink(user_id=manager_user.id, role_id=manager_role.id))
        await session.flush()

        # ── 8. USER CAJERO DE EMPRESA DEMO ───────────────────────────
        cajero_user = User(
            name="Cajero",
            last_name="Demo",
            email="cajero@empresademo.com",
            password=get_password_hash("cajero123"),
            company_id=company.id
        )
        session.add(cajero_user)
        await session.flush()

        session.add(RoleUserLink(user_id=cajero_user.id, role_id=cajero_role.id))
        await session.flush()

        # ── 10. ZONE ─────────────────────────────────────────────────
        zone = Zone(
            name="Zona A",
            code="ZONA-A",
            description="Zona de entrada principal",
            branch_id=branch.id
        )
        session.add(zone)
        await session.flush()

        # ── 11. DEVICE ───────────────────────────────────────────────
        device = Device(
            mac_address="AA:BB:CC:DD:EE:FF",
            chip_model="ESP32-WROOM",
            fw_version="1.0.0",
            last_ip="192.168.1.100",
            last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
            status=Status.ACTIVE,
            branch_id=branch.id
        )
        session.add(device)
        await session.flush()

        # ── 12. GATE ─────────────────────────────────────────────────
        gate = Gate(
            code="GATE-01",
            direction=Direction.ENTRY,
            price=Decimal("5.00"),
            zone_id=zone.id,
            device_id=device.id
        )
        session.add(gate)
        await session.flush()

        # ── 13. TYPES ────────────────────────────────────────────────
        cobro_type = Type(
            name="COBRO_ACCESO",
            description="Cobro automático al pasar por torniquete"
        )
        recarga_type = Type(
            name="RECARGA",
            description="Recarga manual en ventanilla"
        )
        session.add_all([cobro_type, recarga_type])
        await session.flush()

        # ── 14. CLIENT + WALLET ──────────────────────────────────────
        client = Client(
            name="Juan",
            last_name="Pérez",
            ci="12345678",
            email="juan.perez@demo.com",
            company_id=company.id
        )
        session.add(client)
        await session.flush()

        wallet = Wallet(
            client_id=client.id,
            amount=Decimal("50.00"),
            wallet_type=WalletType.MAIN
        )
        session.add(wallet)
        await session.flush()

        # ── 15. CHIP + CREDENTIAL + CLIENT CREDENTIAL ────────────────
        chip = Chip(
            nro_batch="LOTE-2024-001",
            batch_status=BatchStatus.ASSIGNED,
            physical_uuid="PHYS-UUID-DEMO-0001",
            upasser_uuid="UPS-UUID-DEMO-0001",
            company_id=company.id
        )
        session.add(chip)
        await session.flush()

        credential = Credential(
            type=CredentialType.NFC,
            public_id="04:AB:CD:EF:12:34",
            secret_data="secret_encriptado",
            status=Status.ACTIVE,
            company_id=company.id,
            chip_id=chip.id
        )
        session.add(credential)
        await session.flush()

        client_credential = ClientCredential(
            client_id=client.id,
            credential_id=credential.id,
            state=True,
            assignment_status=AssignmentStatus.ACTIVE
        )
        session.add(client_credential)
        await session.flush()

        # ── 16. TICKET DEMO ──────────────────────────────────────────
        demo_ticket = Ticket(
            qr_code="TICKET-DEMO-001",
            amount=Decimal("5.00"),
            zone_id=zone.id,
            company_id=company.id,
            status=TicketStatus.AVAILABLE
        )
        session.add(demo_ticket)

        # ── COMMIT ───────────────────────────────────────────────────
        await session.commit()

        print("Seeds aplicados correctamente.")
        print("")
        print("  ── PLATAFORMA ──────────────────────────────────────")
        print(f"  Empresa plataforma: {upasser_company.name}  ({upasser_company.id})")
        print(f"  Super Admin:        {platform_user.email}  /  upasser_admin_2025")
        print("")
        print("  ── EMPRESA DEMO ────────────────────────────────────")
        print(f"  Empresa:    {company.name}  ({company.id})")
        print(f"  Admin:      {admin_user.email}  /  admin123")
        print(f"  Manager:    {manager_user.email}  /  manager123")
        print(f"  Cajero:     {cajero_user.email}  /  cajero123")
        print(f"  Device MAC: {device.mac_address}")
        print(f"  NFC UID:    {credential.public_id}")
        print(f"  Cliente:    {client.name} {client.last_name}  —  saldo: {wallet.amount}")
        print(f"  Ticket QR:  {demo_ticket.qr_code}  —  monto: {demo_ticket.amount}")
        print("  Type IDs:")
        print(f"    COBRO_ACCESO -> {cobro_type.id}")
        print(f"    RECARGA      -> {recarga_type.id}")


if __name__ == "__main__":
    asyncio.run(seed())
