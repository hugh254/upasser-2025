# Upasser API

Sistema de control de acceso y billetera prepago con integración IoT. Gestiona clientes con saldo prepago, credenciales NFC/QR y eventos de acceso físico en tiempo real — torniquetes y puertas controladas por dispositivos ESP32.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Framework | FastAPI 0.115+ |
| ORM | SQLModel (SQLAlchemy 2.0 async + Pydantic) |
| Base de datos | PostgreSQL 17 |
| Driver async | asyncpg |
| Auth | python-jose (JWT) + passlib/bcrypt |
| Migraciones | Alembic |
| Runtime | Python 3.13 / Uvicorn |
| Infraestructura | Docker + Docker Compose |

---

## Flujo principal

```
1. Registrar empresa        POST /companies
2. Crear sucursal/zona/gate POST /branches  →  /zones  →  /gates
3. Registrar cliente        POST /clients          (crea wallet MAIN automáticamente)
4. Asignar credencial NFC   POST /credentials/assign
5. Recargar saldo           POST /operations/recharge
6. Acceso IoT               POST /operations/scan  ←  ESP32 llama este endpoint al tapear chip
                                                       retorna GO / NO-GO + deduce saldo
```

---

## Levantar el proyecto

### Desarrollo (hot-reload, BD expuesta en :5432, `/docs` habilitado)

```bash
cp .env.example .env   # completar variables requeridas
docker-compose up
```

### Producción (`fastapi run`, BD sin puerto público, `/docs` deshabilitado)

```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Solo el servidor FastAPI (requiere BD local)

```bash
fastapi dev app/main.py
```

API disponible en `http://localhost:8000` — documentación en `http://localhost:8000/docs` (solo en `ENVIRONMENT=local`).

---

## Variables de entorno

Crear un archivo `.env` en la raíz con las siguientes variables:

| Variable | Descripción |
|----------|-------------|
| `POSTGRES_USER` | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL |
| `POSTGRES_DB` | Nombre de la base de datos |
| `POSTGRES_SERVER` | Host de PostgreSQL (`db` en Docker, `localhost` local) |
| `SECRET_KEY` | Clave secreta para firmar JWT |
| `ALLOWED_ORIGINS` | CORS origins separados por coma (ej. `http://localhost:3000`) |

---

## Migraciones

```bash
# Aplicar todas las migraciones pendientes
alembic upgrade head

# Generar migración desde cambios en los modelos
alembic revision --autogenerate -m "descripcion"

# Revertir un paso
alembic downgrade -1
```

> **Dato crítico:** el endpoint `POST /operations/scan` requiere que exista una fila en la tabla `types` con `name = "COBRO_ACCESO"`. Debe crearse vía seed antes de usar el flujo de acceso IoT.

---

## Estructura del proyecto

```
upasser-2025/
├── app/
│   ├── main.py          # FastAPI app, routers, CORS, lifespan
│   ├── config.py        # Settings via pydantic-settings (.env)
│   ├── database.py      # AsyncSession factory
│   ├── security.py      # JWT + bcrypt
│   ├── dependencies.py  # RoleChecker (RBAC)
│   ├── models/          # SQLModel ORM
│   │   ├── base.py      # BaseModel (UUID + timestamps) + enums
│   │   ├── org.py       # Company, Branch, User, Role, Permission
│   │   ├── iot.py       # Device, Zone, Gate
│   │   ├── customers.py # Client, Wallet, Credential, Chip, Ticket
│   │   └── operations.py# Access, Transaction, Type
│   ├── schemas/         # Pydantic request/response schemas
│   └── routers/         # Un router por dominio
├── migrations/          # Versiones de Alembic
├── docs-diagrams/       # ERD, C4 y diccionario de datos
├── Dockerfile
├── docker-compose.yml
└── docker-compose.prod.yml
```

---

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/auth/login` | Login — retorna access + refresh token |
| `POST` | `/auth/refresh` | Renovar access token |
| `GET/POST` | `/companies` | CRUD de empresas |
| `GET/POST` | `/branches` | CRUD de sucursales |
| `GET/POST` | `/clients` | CRUD de clientes |
| `GET/POST` | `/credentials` | CRUD de credenciales NFC/QR |
| `GET` | `/credentials/lookup` | Lookup por UID — retorna estado, saldo y datos del cliente |
| `GET/POST` | `/chips` | Inventario de chips NFC |
| `POST` | `/chips/batch-assign` | Asignar lote de chips a empresa |
| `POST` | `/chips/batch-activate` | Activar lote de chips |
| `GET/POST` | `/roles` | CRUD de roles (RBAC) |
| `GET/POST` | `/permissions` | CRUD de permisos granulares |
| `GET/POST` | `/users` | CRUD de usuarios del sistema |
| `GET/POST` | `/zones` | CRUD de zonas físicas |
| `GET/POST` | `/devices` | CRUD de dispositivos ESP32 |
| `GET/POST` | `/gates` | CRUD de torniquetes/puertas |
| `GET/POST` | `/tickets` | Emisión y canje de tickets QR |
| `POST` | `/operations/recharge` | Recargar saldo en billetera |
| `POST` | `/operations/scan` | Scan IoT — GO/NO-GO + deducción de saldo (sin auth) |

---

## Multi-tenancy y RBAC

- Cada empresa (`Company`) es un tenant aislado con sus propios usuarios, clientes y credenciales.
- Los usuarios tienen roles (`PLATFORM` o `COMPANY`) que definen su acceso.
- Los roles tienen permisos granulares por recurso y acción (`clients:read`, `wallets:recharge`, etc.).
- Los overrides individuales en `users_permissions` permiten conceder o denegar permisos a un usuario específico sin cambiar su rol.
- Los roles con `is_system = true` son protegidos — no pueden eliminarse ni renombrarse desde la API.

---

## Documentación técnica

| Documento | Ubicación |
|-----------|-----------|
| Diccionario de datos | [`docs-diagrams/data_dictionary.md`](./docs-diagrams/data_dictionary.md) |
| ERD (entidad-relación) | [`docs-diagrams/erd.md`](./docs-diagrams/erd.md) |
| C4 — Contexto (L1) | [`docs-diagrams/c4-context.md`](./docs-diagrams/c4-context.md) |
| C4 — Contenedores (L2) | [`docs-diagrams/c4-container.md`](./docs-diagrams/c4-container.md) |
| C4 — Componentes (L3) | [`docs-diagrams/c4-component.md`](./docs-diagrams/c4-component.md) |
