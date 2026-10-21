#!/usr/bin/env bash
# Runs backend lint/typecheck/tests and frontend format/lint/typecheck/tests/build.
# Mirrors scripts/verify.ps1 and is used by CI.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-${REPO_ROOT}/backend/.venv/bin/python}"

cd "${REPO_ROOT}/backend"
"${PYTHON}" -m ruff check .
"${PYTHON}" -m mypy
"${PYTHON}" -m pytest -q

cd "${REPO_ROOT}/frontend"
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build

echo "[ok] all verification steps passed"
