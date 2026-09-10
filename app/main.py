from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from sqlalchemy import text

from .config import get_settings
from .database import engine
from app.routers import (
    auth, roles, permissions, companies, branches, users, clients,
    zones, devices, gates, credentials, transaction_types,
    operations, tickets, chips,
)

settings = get_settings()
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Upasser API iniciando!!!")
    yield
    print("Upasser API deteniéndose!!!")


app = FastAPI(
    title="Upasser API",
    version="1.0.0",
    description="API para control de acceso y cobros IoT",
    lifespan=lifespan,
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {
        "project": "Upasser API",
        "version": "1.0.0",
        "status": "Running",
    }


@app.get("/health")
async def health_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "unreachable"},
        )


app.include_router(auth.router)
app.include_router(roles.router)
app.include_router(permissions.router)
app.include_router(companies.router)
app.include_router(users.router)
app.include_router(branches.router)
app.include_router(clients.router)
app.include_router(zones.router)
app.include_router(devices.router)
app.include_router(gates.router)
app.include_router(credentials.router)
app.include_router(transaction_types.router)
app.include_router(operations.router)
app.include_router(tickets.router)
app.include_router(chips.router)
