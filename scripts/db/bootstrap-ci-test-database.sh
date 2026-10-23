#!/usr/bin/env bash
# Prepare the isolated PostgreSQL database used by integration tests in CI.
# This script must only run against the ephemeral GitHub Actions PostgreSQL service.
set -euo pipefail

: "${CI:?CI must be set by GitHub Actions}"
: "${GITHUB_ACTIONS:?GitHub Actions runner required}"
: "${POSTGRES_HOST:?missing host}"
: "${POSTGRES_PORT:?missing port}"
: "${POSTGRES_ADMIN_USER:?missing admin username}"
: "${POSTGRES_ADMIN_PASSWORD:?missing admin password}"
: "${TOUCHE_DB_MIGRATOR_USER:?missing migrator}"
: "${TOUCHE_DB_APP_USER:?missing application role}"

if [[ "${POSTGRES_HOST}" != "127.0.0.1" || "${POSTGRES_PORT}" != "5432" ]]; then
  echo "Refusing to create a test DB against a non-local CI database" >&2
  exit 1
fi

test_db="touche_commerce_test"
export PGPASSWORD="${POSTGRES_ADMIN_PASSWORD}"

psql -X -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
  -U "${POSTGRES_ADMIN_USER}" -d postgres \
  -v ON_ERROR_STOP=1 \
  -v test_db="${test_db}" \
  -v migrator="${TOUCHE_DB_MIGRATOR_USER}" \
  -v app_user="${TOUCHE_DB_APP_USER}" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'test_db', :'migrator')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'test_db')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'test_db', :'app_user')
\gexec
SQL

psql -X -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
  -U "${POSTGRES_ADMIN_USER}" -d "${test_db}" \
  -v ON_ERROR_STOP=1 \
  -v app_user="${TOUCHE_DB_APP_USER}" \
  -v migrator_user="${TOUCHE_DB_MIGRATOR_USER}" \
  -f "$(dirname "${BASH_SOURCE[0]}")/02-schema-grants.sql"

echo "[touche] isolated CI test database ready: ${test_db}"
