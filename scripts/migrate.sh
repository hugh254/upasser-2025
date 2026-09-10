#!/usr/bin/env bash
# Ejecuta migraciones de Alembic contra cualquier entorno.
# Uso:
#   ./scripts/migrate.sh                  → usa .env local
#   ./scripts/migrate.sh --env rds        → solicita datos de RDS interactivamente
#   ./scripts/migrate.sh --env rds --dry  → muestra el comando sin ejecutarlo

set -euo pipefail

MODE="local"
DRY=false

for arg in "$@"; do
  case $arg in
    --env) shift ;;
    rds) MODE="rds" ;;
    --dry) DRY=true ;;
  esac
done

if [ "$MODE" = "rds" ]; then
  echo "── Migraciones contra Amazon RDS ────────────────────"
  read -rp "POSTGRES_SERVER (endpoint RDS): " PG_SERVER
  read -rp "POSTGRES_USER:                  " PG_USER
  read -rsp "POSTGRES_PASSWORD:              " PG_PASS
  echo
  read -rp "POSTGRES_DB   [upasser_db]:     " PG_DB
  PG_DB="${PG_DB:-upasser_db}"
  read -rp "POSTGRES_PORT [5432]:           " PG_PORT
  PG_PORT="${PG_PORT:-5432}"

  export POSTGRES_SERVER="$PG_SERVER"
  export POSTGRES_USER="$PG_USER"
  export POSTGRES_PASSWORD="$PG_PASS"
  export POSTGRES_DB="$PG_DB"
  export POSTGRES_PORT="$PG_PORT"
  export ENVIRONMENT="production"
  # SECRET_KEY requerido por Settings aunque no se use en migraciones
  export SECRET_KEY="${SECRET_KEY:-placeholder_for_migrations_only}"

  echo ""
  echo "Destino: postgresql+asyncpg://$PG_USER:***@$PG_SERVER:$PG_PORT/$PG_DB"
  echo ""
fi

CMD="alembic upgrade head"

if [ "$DRY" = true ]; then
  echo "[dry-run] $CMD"
  exit 0
fi

echo "Aplicando migraciones..."
$CMD
echo "Migraciones aplicadas correctamente."
