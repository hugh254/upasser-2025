#!/usr/bin/env bash
# Ejecuta el seed inicial contra cualquier entorno.
# Uso:
#   ./scripts/seed.sh                  → usa .env local
#   ./scripts/seed.sh --env rds        → solicita datos de RDS interactivamente

set -euo pipefail

MODE="local"

for arg in "$@"; do
  case $arg in
    --env) shift ;;
    rds) MODE="rds" ;;
  esac
done

if [ "$MODE" = "rds" ]; then
  echo "── Seed contra Amazon RDS ───────────────────────────"
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
  export SECRET_KEY="${SECRET_KEY:-placeholder_for_seed_only}"

  echo ""
  echo "Destino: postgresql+asyncpg://$PG_USER:***@$PG_SERVER:$PG_PORT/$PG_DB"
  echo ""
fi

echo "Aplicando seed..."
python -m app.seeds.seed

echo ""
echo "⚠️  IMPORTANTE — Cambia estas contraseñas inmediatamente en producción:"
echo "   admin@upasser.io          →  upasser_admin_2025"
echo "   admin@empresademo.com     →  admin123"
echo "   manager@empresademo.com   →  manager123"
echo "   cajero@empresademo.com    →  cajero123"
