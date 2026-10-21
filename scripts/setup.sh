#!/usr/bin/env bash
# One-time local setup for Linux/macOS/CI. Safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

for tool in python3 node npm git; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required tool '${tool}' was not found on PATH." >&2
    exit 1
  fi
done

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[ok] created .env from .env.example (development-only credentials)"
else
  echo "[ok] .env already exists (left untouched)"
fi

if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/python -m pip install --quiet --disable-pip-version-check -e './backend[dev]'
echo "[ok] backend dependencies installed"

if [ -d frontend ]; then
  (cd frontend && npm install --no-audit --no-fund)
  if [ ! -f frontend/.env.local ]; then
    cp frontend/.env.example frontend/.env.local
  fi
  echo "[ok] frontend dependencies installed"
fi

cat <<'EOF'

Setup complete. Next steps:
  1. docker compose -f infra/docker-compose.yml up -d
  2. bash scripts/migrate.sh
  3. bash scripts/dev-backend.sh     (terminal 1)
  4. bash scripts/dev-frontend.sh    (terminal 2)
EOF
