#!/usr/bin/env bash
# Starts the FastAPI backend on http://127.0.0.1:8000.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-${REPO_ROOT}/backend/.venv/bin/python}"
PORT="${PORT:-8000}"

if [ ! -x "${PYTHON}" ]; then
  echo "Backend virtualenv not found at ${PYTHON}. Run scripts/setup.sh first." >&2
  exit 1
fi

cd "${REPO_ROOT}/backend"
exec "${PYTHON}" -m uvicorn app.main:create_app --factory \
  --host 127.0.0.1 --port "${PORT}" --proxy-headers --no-server-header --reload
