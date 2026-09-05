from typing import Optional, List
from sqlmodel import SQLModel
from uuid import UUID
from datetime import datetime
from app.models.base import Status, RoleScope, ExpirationUnit

# --- COMPANIES ---
class CompanyBase(SQLModel):
    name: str
    description: str
    img_path: Optional[str] = None
    status: Status = Status.ACTIVE

class CompanyCreate(CompanyBase):
    pass

class CompanyUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    img_path: Optional[str] = None
    status: Optional[Status] = None
    ticket_expiration_value: Optional[int] = None
    ticket_expiration_unit: Optional[ExpirationUnit] = None

class CompanyRead(CompanyBase):
    id: UUID
    is_platform: bool
    ticket_expiration_value: Optional[int]
    ticket_expiration_unit: Optional[ExpirationUnit]
    created_at: datetime
    updated_at: datetime

# --- BRANCHES ---
class BranchBase(SQLModel):
    name: str
    description: str
    address: str
    city: str
    is_main: bool = False
    status: Status = Status.ACTIVE
    company_id: UUID

class BranchCreate(BranchBase):
    pass

class BranchUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    is_main: Optional[bool] = None
    status: Optional[Status] = None

class BranchRead(BranchBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

# --- USERS ---
class UserBase(SQLModel):
    name: str
    last_name: str
    email: str
    company_id: UUID

class UserCreate(UserBase):
    password: str  # Obligatorio al crear

class UserUpdate(SQLModel):
    name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None # Opcional al actualizar
    company_id: Optional[UUID] = None

class UserRead(UserBase):
    id: UUID
    created_at: datetime
    # ¡IMPORTANTE! No incluimos 'password' aquí por seguridad

# --- COMPANY ONBOARDING ---
class CompanyOnboardRequest(SQLModel):
    """Crea una empresa + su usuario administrador inicial en una sola operación."""
    company_name: str
    company_description: str
    admin_name: str
    admin_last_name: str
    admin_email: str
    admin_password: str

class CompanyOnboardResponse(SQLModel):
    company_id: UUID
    company_name: str
    admin_email: str

# --- TOKEN SCHEMAS ---
class Token(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenData(SQLModel):
    user_id: Optional[str] = None

# --- ROLES SCHEMAS ---
class RoleBase(SQLModel):
    name: str
    scope: RoleScope = RoleScope.COMPANY

class RoleCreate(RoleBase):
    pass

class RoleUpdate(SQLModel):
    name: Optional[str] = None
    scope: Optional[RoleScope] = None

class RoleRead(RoleBase):
    id: UUID
    is_system: bool

# --- SCHEMAS PARA GESTIÓN DE USUARIOS ---

# 1. Input: Lo que el Admin envía para crear un usuario
class UserCreateWithRoles(SQLModel):
    name: str
    last_name: str
    email: str
    password: str
    company_id: UUID
    role_ids: List[UUID] = [] # <--- La lista de IDs de roles (Ej: ["uuid-admin", "uuid-ventas"])

# 2. Output: Esquema auxiliar para mostrar el nombre y scope del rol en la respuesta
class RoleSimple(SQLModel):
    id: UUID
    name: str
    scope: RoleScope

# 3. Output: Lo que devuelve la API (El usuario con sus roles, SIN password)
class UserReadWithRoles(SQLModel):
    id: UUID
    name: str
    last_name: str
    email: str
    company_id: UUID
    created_at: datetime
    roles: List[RoleSimple] = []


# --- PERMISSIONS SCHEMAS ---
class PermissionCreate(SQLModel):
    resource: str
    action: str
    description: str

class PermissionUpdate(SQLModel):
    description: Optional[str] = None

class PermissionRead(SQLModel):
    id: UUID
    resource: str
    action: str
    description: str

class RolePermissionAssign(SQLModel):
    permission_id: UUID

class UserPermissionOverrideCreate(SQLModel):
    permission_id: UUID
    granted: bool = True

class UserPermissionOverrideRead(SQLModel):
    permission_id: UUID
    resource: str
    action: str
    description: str
    granted: bool