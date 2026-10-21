#!/usr/bin/env bash
# ===========================================================================
# Creates the runtime + migration roles and schema grants against an already
# running PostgreSQL. Used by CI and by Linux/macOS developers who manage
# PostgreSQL themselves (or via docker compose after a manual reset).
#
# Required environment (CI supplies these; .env values work locally):
#   POSTGRES_ADMIN_USER / POSTGRES_ADMIN_PASSWORD / POSTGRES_DB
#   TOUCHE_DB_APP_USER / TOUCHE_DB_APP_PASSWORD
#   TOUCHE_DB_MIGRATOR_USER / TOUCHE_DB_MIGRATOR_PASSWORD
# ===========================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

: "${POSTGRES_ADMIN_USER:?POSTGRES_ADMIN_USER is required}"
: "${POSTGRES_ADMIN_PASSWORD:?POSTGRES_ADMIN_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${TOUCHE_DB_APP_USER:?TOUCHE_DB_APP_USER is required}"
: "${TOUCHE_DB_APP_PASSWORD:?TOUCHE_DB_APP_PASSWORD is required}"
: "${TOUCHE_DB_MIGRATOR_USER:?TOUCHE_DB_MIGRATOR_USER is required}"
: "${TOUCHE_DB_MIGRATOR_PASSWORD:?TOUCHE_DB_MIGRATOR_PASSWORD is required}"

POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_ADMIN_DB="${POSTGRES_ADMIN_DB:-postgres}"

export PGPASSWORD="${POSTGRES_ADMIN_PASSWORD}"

psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_ADMIN_USER}" \
  -d "${POSTGRES_ADMIN_DB}" -v ON_ERROR_STOP=1 \
  -v app_user="${TOUCHE_DB_APP_USER}" \
  -v app_password="${TOUCHE_DB_APP_PASSWORD}" \
  -v migrator_user="${TOUCHE_DB_MIGRATOR_USER}" \
  -v migrator_password="${TOUCHE_DB_MIGRATOR_PASSWORD}" \
  -v db_name="${POSTGRES_DB}" \
  -f "${REPO_ROOT}/scripts/db/01-roles-and-database.sql"

psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_ADMIN_USER}" \
  -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
  -v app_user="${TOUCHE_DB_APP_USER}" \
  -v migrator_user="${TOUCHE_DB_MIGRATOR_USER}" \
  -f "${REPO_ROOT}/scripts/db/02-schema-grants.sql"

echo "[touche] roles and grants ready on ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
