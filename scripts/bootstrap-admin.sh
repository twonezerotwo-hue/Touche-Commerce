#!/usr/bin/env bash
# =============================================================================
# Creates the first TOUCHE COMMERCE administrator and company (Stage 1A).
#
# The password is requested by an interactive hidden prompt inside the CLI; it
# is never passed as an argument and never printed. There is no default password.
#
# Usage: bash scripts/bootstrap-admin.sh
# =============================================================================
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$repo_root/backend"
python="$backend_dir/.venv/bin/python"

if [[ ! -x "$python" ]]; then
  echo "Backend virtualenv not found at $python. Run scripts/setup.sh first." >&2
  exit 1
fi

if [[ -f "$repo_root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$repo_root/.env"
  set +a
fi

echo
echo "==> Creating the first administrator and company"
echo "The password is entered interactively; nothing is logged."
cd "$backend_dir"
exec "$python" -m app.cli bootstrap "$@"
