#!/usr/bin/env bash
# Applies Alembic migrations with the migration role (reads .env via pydantic-settings).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-${REPO_ROOT}/backend/.venv/bin/python}"

if [ ! -x "${PYTHON}" ]; then
  echo "Backend virtualenv not found at ${PYTHON}. Run scripts/setup.sh first." >&2
  exit 1
fi

cd "${REPO_ROOT}/backend"
"${PYTHON}" -m alembic upgrade "${1:-head}"
echo "[ok] database migrated to ${1:-head}"
