"""Map the ISOLATED acceptance company to a Finance company (test database only).

The privileged ``app.cli finance-map`` command reads its database from the environment. This
wrapper points it at the ``*_test`` database derived from the configured DSNs (never the
development database) and then runs the real command, which verifies the Finance company live
before it stores the mapping.

    python -m scripts.acceptance_finance_map <finance-company-key>

Needs the Finance connector variables in the environment (enabled, base URL, key id, secret).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings, get_settings  # noqa: E402

ACCEPTANCE_COMPANY = "Touche Acceptance Trading"
ACCEPTANCE_ADMIN = "owner@acceptance.touche.example"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m scripts.acceptance_finance_map <finance-company-key>")
        return 1
    loaded = Settings()
    runtime, migration = loaded.test_database_dsn, loaded.test_migration_dsn
    if runtime is None or migration is None or not runtime.rsplit("/", 1)[-1].endswith("_test"):
        print("Refusing: the target is not the isolated *_test database.")
        return 1
    os.environ["TOUCHE_DATABASE_URL"] = runtime
    os.environ["TOUCHE_DATABASE_MIGRATION_URL"] = migration
    get_settings.cache_clear()

    from app import cli

    return cli.main(
        [
            "finance-map",
            "set",
            "--company",
            ACCEPTANCE_COMPANY,
            "--finance-company",
            argv[0],
            "--actor",
            ACCEPTANCE_ADMIN,
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
