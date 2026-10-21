"""Export the FastAPI OpenAPI schema for frontend type generation.

Usage (from the repository root, with the backend virtualenv active)::

    python backend/scripts/export_openapi.py [output-path]

The default output path is ``frontend/openapi/openapi.json``.  The generated
schema is then converted to TypeScript with ``openapi-typescript`` so the
frontend never maintains hand-written duplicate DTOs (docs/DECISIONS.md #14).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_OUTPUT = REPO_ROOT / "frontend" / "openapi" / "openapi.json"

sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402  (import after sys.path setup)


def export_schema(output: Path) -> Path:
    """Write the OpenAPI document to ``output`` and return the path."""
    output.parent.mkdir(parents=True, exist_ok=True)
    application = create_app(get_settings())
    schema = application.openapi()
    output.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def main(argv: list[str]) -> int:
    output = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_OUTPUT
    written = export_schema(output)
    print(f"OpenAPI schema written to {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
