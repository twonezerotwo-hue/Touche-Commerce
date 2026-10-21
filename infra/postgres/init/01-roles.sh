#!/bin/bash
# ===========================================================================
# Runs once on first container initialisation (empty data volume).
# Creates the runtime and migration roles and applies schema grants.
#
# The SQL lives in scripts/db (mounted read-only) so the Docker path, the
# native portable-PostgreSQL path and CI all share the exact same statements.
# ===========================================================================
set -euo pipefail

: "${TOUCHE_DB_APP_USER:?TOUCHE_DB_APP_USER is required}"
: "${TOUCHE_DB_APP_PASSWORD:?TOUCHE_DB_APP_PASSWORD is required}"
: "${TOUCHE_DB_MIGRATOR_USER:?TOUCHE_DB_MIGRATOR_USER is required}"
: "${TOUCHE_DB_MIGRATOR_PASSWORD:?TOUCHE_DB_MIGRATOR_PASSWORD is required}"

echo "[touche] creating least-privilege roles for ${POSTGRES_DB}"

psql -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname postgres \
  -v app_user="${TOUCHE_DB_APP_USER}" \
  -v app_password="${TOUCHE_DB_APP_PASSWORD}" \
  -v migrator_user="${TOUCHE_DB_MIGRATOR_USER}" \
  -v migrator_password="${TOUCHE_DB_MIGRATOR_PASSWORD}" \
  -v db_name="${POSTGRES_DB}" \
  -f /opt/touche-db/01-roles-and-database.sql

psql -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  -v app_user="${TOUCHE_DB_APP_USER}" \
  -v migrator_user="${TOUCHE_DB_MIGRATOR_USER}" \
  -f /opt/touche-db/02-schema-grants.sql

echo "[touche] role bootstrap complete"
