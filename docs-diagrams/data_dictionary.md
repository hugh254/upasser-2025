# Diccionario de Datos — Upasser

**Base de datos:** PostgreSQL 17  
**ORM:** SQLModel (SQLAlchemy 2.0 + Pydantic)  
**Convención de IDs:** UUID v4 en todas las tablas  
**Timestamps:** `created_at` y `updated_at` automáticos en todas las tablas (heredados de `BaseModel`)

---

## Índice de tablas

| Tabla | Módulo | Descripción |
|-------|--------|-------------|
| [companies](#companies) | Organización | Empresas cliente del sistema |
| [branches](#branches) | Organización | Sucursales de cada empresa |
| [roles](#roles) | Organización | Roles de acceso al sistema |
| [permissions](#permissions) | Organización | Permisos granulares por recurso y acción |
| [roles_permissions](#roles_permissions) | Organización | Asignación de permisos a roles (M:N) |
| [users](#users) | Organización | Empleados/administradores del sistema |
| [roles_users](#roles_users) | Organización | Asignación de roles a usuarios (M:N) |
| [users_permissions](#users_permissions) | Organización | Overrides de permisos individuales por usuario |
| [zones](#zones) | IoT | Zonas físicas dentro de una sucursal |
| [devices](#devices) | IoT | Dispositivos ESP32 registrados |
| [gates](#gates) | IoT | Torniquetes/puertas de acceso |
| [clients](#clients) | Clientes | Personas con acceso al sistema |
| [chips](#chips) | Clientes | Inventario físico de chips NFC |
| [credentials](#credentials) | Clientes | Credenciales NFC/QR/BLE/PIN |
| [client_credential](#client_credential) | Clientes | Asignación de credenciales a clientes (M:N) |
| [tickets](#tickets) | Clientes | QR de un solo uso con acceso o monto pre-cargado |
| [wallets](#wallets) | Operaciones | Billeteras prepago de los clientes |
| [types](#types) | Operaciones | Tipos de transacción (COBRO_ACCESO, RECARGA…) |
| [access](#access) | Operaciones | Registro de eventos de acceso físico |
| [transactions](#transactions) | Operaciones | Movimientos de saldo en billeteras |

---

## Enumeraciones

### `Status`
Estado general de entidades del sistema.

| Valor | Descripción |
|-------|-------------|
| `ACTIVE` | Activo y operativo |
| `INACTIVE` | Desactivado temporalmente |
| `BLOCKED` | Bloqueado por incidencia |
| `LOST` | Reportado como perdido |
| `EXPIRED` | Expirado (vencimiento de fecha) |

### `CredentialType`
Tipo de tecnología de la credencial.

| Valor | Descripción |
|-------|-------------|
| `NFC` | Chip NFC / tarjeta de proximidad |
| `QR` | Código QR |
| `BLE` | Bluetooth Low Energy |
| `PIN` | Código numérico personal |

### `AccessResult`
Resultado de un intento de acceso.

| Valor | Descripción |
|-------|-------------|
| `GRANTED` | Acceso concedido |
| `DENIED` | Acceso denegado |

### `BatchStatus`
Estado de un chip en el inventario.

| Valor | Descripción |
|-------|-------------|
| `AVAILABLE` | Disponible en inventario, sin asignar |
| `ASSIGNED` | Ya vinculado a una credencial activa |
| `DEFECTIVE` | Dañado de fábrica, inutilizable |
| `LOST` | Chip perdido |

### `AssignmentStatus`
Estado de asignación de una credencial a un cliente.

| Valor | Descripción |
|-------|-------------|
| `PENDING` | Vendida sin registrar — el titular es desconocido |
| `ACTIVE` | Vinculada a un cliente registrado |

### `Direction`
Dirección del torniquete/puerta.

| Valor | Descripción |
|-------|-------------|
| `ENTRY` | Puerta de entrada |
| `EXIT` | Puerta de salida |

### `WalletType`
Tipo de billetera del cliente.

| Valor | Descripción |
|-------|-------------|
| `MAIN` | Billetera principal — usada por defecto en cobros y recargas |
| `BONUS` | Saldo bono / promocional |
| `COURTESY` | Saldo de cortesía otorgado por la empresa |

### `RoleScope`
Alcance de un rol dentro del sistema.

| Valor | Descripción |
|-------|-------------|
| `PLATFORM` | Roles internos de Upasser (platform_admin, platform_support, etc.) |
| `COMPANY` | Roles de empresas clientes (admin, manager, cajero) |

### `TicketStatus`
Estado de un ticket QR de un solo uso.

| Valor | Descripción |
|-------|-------------|
| `AVAILABLE` | Sin usar — listo para ser canjeado |
| `USED` | Ya canjeado exitosamente |
| `EXPIRED` | Venció sin ser usado |
| `CANCELLED` | Anulado manualmente |

### `ExpirationUnit`
Unidad de tiempo para la expiración de tickets.

| Valor | Descripción |
|-------|-------------|
| `HOURS` | Horas |
| `DAYS` | Días |

---

## Tablas

---

### `companies`

Empresas cliente que utilizan el sistema Upasser. Es el nivel más alto de la jerarquía multi-tenant.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `name` | VARCHAR | NO | — | Nombre de la empresa |
| `description` | VARCHAR | NO | — | Descripción de la empresa |
| `img_path` | VARCHAR | SÍ | — | Ruta a logo o imagen de la empresa |
| `status` | VARCHAR | NO | default `ACTIVE` | Estado (`Status`) |
| `is_platform` | BOOLEAN | NO | default false | `true` si es la empresa interna de Upasser (módulo Platform) |
| `ticket_expiration_value` | INTEGER | SÍ | — | Valor numérico del tiempo de expiración de tickets |
| `ticket_expiration_unit` | VARCHAR | SÍ | — | Unidad de tiempo para expiración (`ExpirationUnit`) |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- 1:N → `branches` (una empresa tiene varias sucursales)
- 1:N → `users` (una empresa tiene varios usuarios del sistema)
- 1:N → `clients` (una empresa gestiona varios clientes)
- 1:N → `credentials` (una empresa emite varias credenciales)
- 1:N → `tickets` (una empresa emite tickets QR)
- 1:N → `chips` (chips asignados a esta empresa; NULL = pool de Upasser)

---

### `branches`

Sucursales físicas de una empresa. Contienen zonas y dispositivos IoT.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `name` | VARCHAR | NO | — | Nombre de la sucursal |
| `description` | VARCHAR | NO | — | Descripción |
| `address` | VARCHAR | NO | — | Dirección física |
| `city` | VARCHAR | NO | — | Ciudad |
| `is_main` | BOOLEAN | NO | default false | Indica si es la sede principal |
| `status` | VARCHAR | NO | default `ACTIVE` | Estado (`Status`) |
| `company_id` | UUID | NO | FK → companies(id) RESTRICT | Empresa propietaria |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `companies`
- 1:N → `zones`
- 1:N → `devices`

---

### `permissions`

Permisos granulares del sistema. Cada permiso representa una acción sobre un recurso (ej. `clients:read`, `wallets:recharge`).

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `resource` | VARCHAR | NO | — | Recurso afectado (ej. `clients`, `wallets`, `roles`) |
| `action` | VARCHAR | NO | — | Acción permitida (ej. `read`, `create`, `recharge`) |
| `description` | VARCHAR | NO | — | Descripción legible del permiso |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- M:N → `roles` (a través de `roles_permissions`)
- M:N → `users` (a través de `users_permissions`, para overrides)

---

### `roles`

Roles de acceso al sistema (admin, manager, cajero). Controlan qué endpoints puede usar cada usuario.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `name` | VARCHAR | NO | — | Nombre del rol (ej. `admin`, `cajero`) |
| `scope` | VARCHAR | NO | default `COMPANY` | Alcance del rol (`RoleScope`) |
| `is_system` | BOOLEAN | NO | default false | `true` = rol de sistema protegido; no se puede eliminar ni renombrar |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

> Los roles con `is_system = true` son creados por seed/migración y no pueden ser eliminados ni modificados desde los endpoints de gestión de roles.

**Relaciones:**
- M:N → `users` (a través de `roles_users`)
- M:N → `permissions` (a través de `roles_permissions`)

---

### `roles_permissions`

Tabla de unión M:N entre roles y permisos.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `role_id` | UUID | NO | PK, FK → roles(id) CASCADE | Rol receptor del permiso |
| `permission_id` | UUID | NO | PK, FK → permissions(id) CASCADE | Permiso asignado |

> Al eliminar un rol o un permiso, sus asignaciones se eliminan en cascada.

---

### `users`

Empleados y administradores del sistema. Se autentican vía JWT para operar el backend.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `name` | VARCHAR | NO | — | Nombre |
| `last_name` | VARCHAR | NO | — | Apellido |
| `email` | VARCHAR | NO | UNIQUE, INDEX | Correo electrónico (se usa como username en login) |
| `password` | VARCHAR | NO | — | Contraseña hasheada con bcrypt |
| `company_id` | UUID | NO | FK → companies(id) RESTRICT | Empresa a la que pertenece |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `companies`
- M:N → `roles` (a través de `roles_users`)
- M:N → `permissions` (a través de `users_permissions`, overrides individuales)

---

### `roles_users`

Tabla de unión M:N entre usuarios y roles. Clave primaria compuesta.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `role_id` | UUID | NO | PK, FK → roles(id) RESTRICT | Rol asignado |
| `user_id` | UUID | NO | PK, FK → users(id) CASCADE | Usuario receptor del rol |

> Si se elimina un usuario, sus asignaciones de rol se eliminan en cascada.  
> No se puede eliminar un rol que tenga usuarios asignados (RESTRICT).

---

### `users_permissions`

Overrides de permisos individuales por usuario. Permite conceder o denegar un permiso específico a un usuario, independientemente de sus roles.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `user_id` | UUID | NO | PK, FK → users(id) CASCADE | Usuario afectado |
| `permission_id` | UUID | NO | PK, FK → permissions(id) CASCADE | Permiso sobrescrito |
| `granted` | BOOLEAN | NO | default true | `true` = concedido explícitamente; `false` = denegado aunque el rol lo permita |

> Al eliminar un usuario o permiso, sus overrides se eliminan en cascada.

---

### `zones`

Zonas físicas dentro de una sucursal. Agrupan puertas/torniquetes bajo un área lógica (ej. "Zona A", "Entrada Principal").

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `name` | VARCHAR | NO | — | Nombre de la zona |
| `code` | VARCHAR | NO | — | Código de identificación (ej. `ZONA-A`) |
| `description` | VARCHAR | NO | — | Descripción de la zona |
| `branch_id` | UUID | NO | FK → branches(id) RESTRICT | Sucursal a la que pertenece |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `branches`
- 1:N → `gates`

---

### `devices`

Dispositivos IoT (ESP32) registrados en el sistema. Cada dispositivo se identifica por su dirección MAC.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `mac_address` | VARCHAR | NO | UNIQUE | Dirección MAC del dispositivo |
| `chip_model` | VARCHAR | NO | — | Modelo del microcontrolador (ej. `ESP32-WROOM`) |
| `fw_version` | VARCHAR | NO | — | Versión del firmware instalado |
| `last_ip` | VARCHAR | NO | — | Última IP asignada por DHCP |
| `last_seen` | TIMESTAMP | NO | — | Última vez que el dispositivo reportó actividad |
| `status` | VARCHAR | NO | — | Estado del dispositivo (`Status`) |
| `branch_id` | UUID | NO | FK → branches(id) RESTRICT | Sucursal donde está instalado |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `branches`
- 1:1 → `gates` (un dispositivo controla una puerta)

---

### `gates`

Torniquetes o puertas de acceso físico. Cada gate está asociado a un dispositivo IoT y tiene un precio de paso.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `code` | VARCHAR | NO | — | Código de la puerta (ej. `GATE-01`) |
| `direction` | VARCHAR | NO | — | Dirección del paso (`Direction`) |
| `price` | DECIMAL(10,2) | NO | default 0 | Precio de paso en moneda local |
| `zone_id` | UUID | NO | FK → zones(id) RESTRICT | Zona a la que pertenece |
| `device_id` | UUID | NO | FK → devices(id) RESTRICT | Dispositivo IoT que la controla |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `zones`
- N:1 → `devices`
- 1:N → `access`

---

### `clients`

Personas que utilizan el sistema de acceso prepago. Poseen billeteras y credenciales.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `name` | VARCHAR | NO | — | Nombre |
| `last_name` | VARCHAR | NO | — | Apellido |
| `ci` | VARCHAR | NO | UNIQUE, INDEX | Cédula de identidad |
| `email` | VARCHAR | NO | UNIQUE, INDEX | Correo electrónico |
| `company_id` | UUID | NO | FK → companies(id) RESTRICT | Empresa que gestiona al cliente |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `companies`
- 1:N → `wallets` (se crea una wallet MAIN automáticamente al crear el cliente)
- 1:N → `client_credential`

---

### `chips`

Inventario físico de chips NFC. Permite rastrear el ciclo de vida de los chips desde el lote de fabricación hasta su asignación a una credencial.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `nro_batch` | VARCHAR | NO | INDEX | Número/código del lote de fabricación |
| `batch_status` | VARCHAR | NO | default `AVAILABLE` | Estado del chip (`BatchStatus`) |
| `physical_uuid` | VARCHAR | NO | UNIQUE, INDEX | UUID físico grabado en el chip (leído por hardware) |
| `upasser_uuid` | VARCHAR | NO | UNIQUE, INDEX | UUID interno de Upasser vinculado a este chip |
| `company_id` | UUID | SÍ | FK → companies(id) SET NULL | Empresa a la que fue asignado; NULL = pool de Upasser |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `companies` (nullable)
- 1:N → `credentials` (un chip puede tener una credencial activa asociada)

---

### `credentials`

Credenciales de acceso físico (NFC, QR, BLE o PIN). Vinculadas a una empresa y opcionalmente a un chip físico.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `type` | VARCHAR | NO | — | Tecnología de la credencial (`CredentialType`) |
| `public_id` | VARCHAR | NO | UNIQUE, INDEX | UID público del chip o código QR (leído por el lector) |
| `secret_data` | VARCHAR | NO | — | Dato secreto encriptado (para validaciones adicionales) |
| `status` | VARCHAR | NO | — | Estado de la credencial (`Status`) |
| `company_id` | UUID | NO | FK → companies(id) RESTRICT | Empresa emisora |
| `chip_id` | UUID | SÍ | FK → chips(id) SET NULL | Chip físico asociado (opcional) |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `companies`
- N:1 → `chips` (nullable, SET NULL al eliminar chip)
- 1:N → `client_credential`

---

### `client_credential`

Tabla de asignación M:N entre clientes y credenciales. Una credencial puede existir sin cliente asignado (tarjeta anónima en estado PENDING) o estar vinculada a un cliente registrado (ACTIVE).

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `client_id` | UUID | SÍ | FK → clients(id) CASCADE | Cliente propietario; NULL = tarjeta anónima (PENDING) |
| `credential_id` | UUID | NO | FK → credentials(id) RESTRICT | Credencial asignada |
| `state` | BOOLEAN | NO | default true | `true` = activa, `false` = inactiva/revocada |
| `assignment_status` | VARCHAR | NO | default `PENDING` | Estado de asignación (`AssignmentStatus`) |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

> Si se elimina un cliente, todas sus asignaciones se eliminan en cascada.  
> No se puede eliminar una credencial que esté asignada (RESTRICT).  
> `client_id` es nullable para soportar tarjetas vendidas sin registrar (`PENDING`); al activar la tarjeta para un cliente se rellena este campo y se actualiza `assignment_status` a `ACTIVE`.

**Relaciones:**
- N:1 → `clients` (nullable)
- N:1 → `credentials`
- 1:N → `access`
- 1:N → `transactions`

---

### `tickets`

Tickets QR de un solo uso. Pueden tener un monto pre-cargado o simplemente dar acceso libre a una zona. Se emiten por empresa y pueden tener fecha de expiración.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `qr_code` | VARCHAR | NO | UNIQUE, INDEX | Código QR único del ticket |
| `amount` | DECIMAL(10,2) | SÍ | — | Monto pre-cargado (null = acceso libre sin cobro) |
| `zone_id` | UUID | SÍ | FK → zones(id) SET NULL | Zona a la que da acceso; null = sin restricción de zona |
| `company_id` | UUID | NO | FK → companies(id) RESTRICT | Empresa emisora del ticket |
| `expires_at` | TIMESTAMP | SÍ | — | Fecha/hora de expiración; null = sin expiración |
| `used_at` | TIMESTAMP | SÍ | — | Marca de tiempo del canje; null = aún no usado |
| `status` | VARCHAR | NO | default `AVAILABLE` | Estado del ticket (`TicketStatus`) |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `companies`
- N:1 → `zones` (nullable)

---

### `wallets`

Billeteras prepago de los clientes. Un cliente puede tener hasta una billetera por tipo (MAIN, BONUS, COURTESY).

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `amount` | DECIMAL(10,2) | NO | default 0, CHECK ≥ 0 | Saldo actual en moneda local |
| `wallet_type` | VARCHAR | NO | default `MAIN` | Tipo de billetera (`WalletType`) |
| `client_id` | UUID | NO | FK → clients(id) CASCADE | Cliente propietario |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Constraints:**
- `wallet_amount_non_negative`: `amount >= 0`
- `uq_wallet_client_type`: UNIQUE(`client_id`, `wallet_type`) — un cliente no puede tener dos billeteras del mismo tipo

**Relaciones:**
- N:1 → `clients`
- 1:N → `transactions`

---

### `types`

Catálogo de tipos de transacción. Permite categorizar movimientos de saldo (cobro de acceso, recarga manual, etc.).

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `name` | VARCHAR | NO | — | Nombre del tipo (ej. `COBRO_ACCESO`, `RECARGA`) |
| `description` | VARCHAR | NO | — | Descripción del tipo de transacción |
| `created_at` | TIMESTAMP | NO | default now() | Fecha de creación |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

> **Dato crítico:** El endpoint `POST /operations/scan` requiere que exista una fila con `name = "COBRO_ACCESO"`. Se crea vía seed.

**Relaciones:**
- 1:N → `transactions`

---

### `access`

Registro inmutable de cada evento de acceso físico (paso por torniquete). Se crea antes de registrar la transacción económica.

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `result` | VARCHAR | NO | — | Resultado del acceso (`AccessResult`) |
| `reason` | VARCHAR | SÍ | default null | Motivo del resultado (ej. "Saldo insuficiente") |
| `extra_data` | VARCHAR | SÍ | default null | Datos adicionales para auditoría (JSON string, etc.) |
| `client_credential_id` | UUID | NO | FK → client_credential(id) RESTRICT | Credencial usada en el evento |
| `gate_id` | UUID | NO | FK → gates(id) RESTRICT | Puerta donde ocurrió el evento |
| `created_at` | TIMESTAMP | NO | default now() | Marca de tiempo del acceso |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Relaciones:**
- N:1 → `client_credential`
- N:1 → `gates`
- 1:1 → `transactions` (un acceso GRANTED genera exactamente una transacción de cobro)

---

### `transactions`

Movimientos de saldo en las billeteras. Convención de signo: **positivo = ingreso** (recarga), **negativo = egreso** (cobro de acceso).

| Columna | Tipo | Nulo | Restricciones | Descripción |
|---------|------|------|---------------|-------------|
| `id` | UUID | NO | PK, default uuid4 | Identificador único |
| `amount` | DECIMAL(10,2) | NO | CHECK ≠ 0 | Monto del movimiento (+ recarga / − cobro) |
| `type_id` | UUID | NO | FK → types(id) RESTRICT | Tipo de transacción |
| `wallet_id` | UUID | NO | FK → wallets(id) RESTRICT | Billetera afectada |
| `access_id` | UUID | SÍ | FK → access(id) SET NULL | Evento de acceso que originó el cobro (null en recargas) |
| `client_credential_id` | UUID | SÍ | FK → client_credential(id) SET NULL | Credencial usada (para trazabilidad en cobros) |
| `created_at` | TIMESTAMP | NO | default now() | Fecha y hora de la transacción |
| `updated_at` | TIMESTAMP | NO | default now(), onupdate | Última modificación |

**Constraints:**
- `transaction_amount_nonzero`: `amount != 0`

**Relaciones:**
- N:1 → `wallets`
- N:1 → `types`
- N:1 → `access` (nullable)
- N:1 → `client_credential` (nullable)

---

## Diagrama de relaciones (texto)

```
companies ──┬── branches ──┬── zones ──┬── gates ──┬── devices
            │              └── devices  └── tickets  └── access ── transactions
            ├── users ←──── roles_users ──── roles ←── roles_permissions ──── permissions
            │               users_permissions ──────────────────────────────────────┘
            ├── chips
            ├── tickets
            └── clients ──┬── wallets ── transactions
                          └── client_credential ──┬── credentials ── chips
                                                  └── access
```

---

## Notas de diseño

| Decisión | Justificación |
|----------|---------------|
| UUID como PK en todas las tablas | Evita enumeración de IDs, compatible con sistemas distribuidos |
| `DECIMAL(10,2)` en montos | Precisión financiera exacta, sin errores de punto flotante |
| `TIMESTAMP WITHOUT TIME ZONE` | PostgreSQL almacena en UTC naive; la app normaliza con `.replace(tzinfo=None)` |
| `amount` en `transactions` con signo | Un solo campo expresa entradas (+) y salidas (−) sin necesidad de columna `direction` |
| `access` se crea antes que `transaction` | Garantiza que el `access_id` exista antes de registrar el cobro (ACID con `flush()`) |
| `SELECT FOR UPDATE` en `wallets` al hacer scan | Previene race conditions en cobros simultáneos sobre la misma billetera |
| `ondelete=CASCADE` solo en tablas dependientes | Los datos financieros (`transactions`, `access`) son RESTRICT para preservar auditoría |
| `client_id` nullable en `client_credential` | Soporta tarjetas anónimas (PENDING) vendidas sin cliente registrado |
| `is_system` en `roles` | Single source of truth para proteger roles de sistema en backend y frontend sin lógica duplicada |
| `physical_uuid` + `upasser_uuid` en `chips` | Desacopla el UUID grabado físicamente del UUID interno de Upasser; permite reasignación sin alterar el hardware |
| `users_permissions` con `granted` | Permite tanto conceder (+) como denegar (−) permisos a nivel de usuario, sin necesidad de roles especiales |
