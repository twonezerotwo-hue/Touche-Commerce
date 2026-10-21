#!/usr/bin/env bash
# Starts the Next.js web shell on http://localhost:3000.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-3000}"

if [ ! -d "${REPO_ROOT}/frontend/node_modules" ]; then
  echo "Frontend dependencies are missing. Run scripts/setup.sh first." >&2
  exit 1
fi

cd "${REPO_ROOT}/frontend"
exec npm run dev -- --port "${PORT}"
