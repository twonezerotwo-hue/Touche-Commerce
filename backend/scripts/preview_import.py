"""Preview trade data from CSV/XLSX locally, without posting to Commerce.

Run from backend directory:
    python -m scripts.preview_import --kind products --file catalogue.xlsx

The output can contain commercial/PII data. Keep it off shared logs.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.services.import_preview import MAX_BYTES, ImportPreviewError, preview_import


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("products", "counterparties"), required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--show-records", action="store_true", help="Show records locally (may be sensitive)")
    args = parser.parse_args()
    try:
        size = args.file.stat().st_size
        if size > MAX_BYTES or size < 1:
            raise ImportPreviewError("Import file is empty or exceeds 2MB")
        preview = preview_import(args.file.name, args.file.read_bytes(), kind=args.kind)
    except (ImportPreviewError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        return 1

    result = {
        "status": "PREVIEW_ONLY",
        "kind": preview.kind,
        "source_type": preview.source_type,
        "total_rows": preview.total_rows,
        "accepted": preview.accepted,
        "rejected": preview.rejected,
        "committed": False,
        "rows": [
            asdict(row) if args.show_records
            else {"row": row.row, "valid": row.valid, "errors": row.errors}
            for row in preview.rows
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if preview.rejected == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
