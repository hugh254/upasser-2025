from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID as PgUUID
import uuid
from .base import BaseModel, Status, RoleScope, ExpirationUnit
# from .customers import Client

class RoleUserLink(SQLModel, table=True):
    __tablename__ = "roles_users"
    role_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True)
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    )

class RolePermissionLink(SQLModel, table=True):
    __tablename__ = "roles_permissions"
    role_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    )
    permission_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)
    )

class UserPermissionLink(SQLModel, table=True):
    """Override individual de permiso por usuario. granted=False deniega aunque el rol lo permita."""
    __tablename__ = "users_permissions"
    user_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    )
    permission_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)
    )
    granted: bool = Field(sa_column=Column(Boolean, nullable=False, default=True))

# --- PERMISSIONS ---
class Permission(BaseModel, table=True):
    __tablename__ = "permissions"
    resource: str
    action: str
    description: str
    roles: List["Role"] = Relationship(back_populates="permissions", link_model=RolePermissionLink)

# --- ROLES ---
class Role(BaseModel, table=True):
    __tablename__ = "roles"
    name: str
    scope: RoleScope = Field(default=RoleScope.COMPANY)
    is_system: bool = Field(default=False)
    users: List["User"] = Relationship(back_populates="roles", link_model=RoleUserLink)
    permissions: List["Permission"] = Relationship(back_populates="roles", link_model=RolePermissionLink)

# --- COMPANIES ---
class Company(BaseModel, table=True):
    __tablename__ = "companies"
    name: str
    description: str
    img_path: Optional[str] = None
    status: Status = Field(default=Status.ACTIVE)
    is_platform: bool = Field(default=False)
    ticket_expiration_value: Optional[int] = Field(default=None)
    ticket_expiration_unit: Optional[ExpirationUnit] = Field(default=None)
    
    # Relaciones
    branches: List["Branch"] = Relationship(back_populates="company")
    users: List["User"] = Relationship(back_populates="company")
    clients: List["Client"] = Relationship(back_populates="company")

# --- BRANCHES ---
class Branch(BaseModel, table=True):
    __tablename__ = "branches"
    name: str
    description: str
    address: str
    city: str
    is_main: bool = False
    status: Status = Field(default=Status.ACTIVE)
    company_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    )

    company: Company = Relationship(back_populates="branches")
    zones: List["Zone"] = Relationship(back_populates="branch")

# --- USERS (Administradores/Empleados) ---
class User(BaseModel, table=True):
    __tablename__ = "users"
    name: str
    last_name: str
    email: str = Field(unique=True, index=True)
    password: str # Recuerda hashear esto
    company_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    )

    company: Company = Relationship(back_populates="users")
    roles: List["Role"] = Relationship(back_populates="users", link_model=RoleUserLink)
    permission_overrides: List["Permission"] = Relationship(link_model=UserPermissionLink)