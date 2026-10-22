#!/usr/bin/env python3
"""Read-only inspection of TOUCHE FINANCE's ledger and Excel master.

This is executable evidence for Stage 5A: it never imports Finance code, never
starts the Finance HTTP server and never writes to SQLite or the workbook.  It
opens SQLite through a ``mode=ro`` URI, validates the columns the connector
relies on, and compares file hashes before and after the read.

It deliberately does **not** calculate receivables, payables or profit.  Those
are Finance's financial engine; duplicating them here would create the second
accounting engine Stage 5 forbids.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Any

EXPECTED_TABLES = (
    "faaliyetler",
    "hesaplar",
    "fisler",
    "fis_satirlari",
    "finans_islemleri",
    "karsi_taraflar",
)

EXPECTED_COLUMNS: dict[str, tuple[str, ...]] = {
    "faaliyetler": ("faaliyet_key", "ad", "aktif"),
    "hesaplar": ("kod", "ad", "hesap_tipi"),
    "fisler": ("fis_id", "faaliyet_key", "tarih", "proje", "cari", "para_birimi"),
    "fis_satirlari": ("fis_id", "satir_no", "hesap_kodu", "borc_kurus", "alacak_kurus"),
    "finans_islemleri": ("transaction_id", "document_id", "state"),
    "karsi_taraflar": ("taraf_id", "ad", "tip", "vergi_no"),
}

# Literal SQL per known table: no identifier is ever interpolated from input.
COUNT_QUERIES: dict[str, str] = {
    "faaliyetler": 'SELECT COUNT(*) FROM "faaliyetler"',
    "hesaplar": 'SELECT COUNT(*) FROM "hesaplar"',
    "fisler": 'SELECT COUNT(*) FROM "fisler"',
    "fis_satirlari": 'SELECT COUNT(*) FROM "fis_satirlari"',
    "finans_islemleri": 'SELECT COUNT(*) FROM "finans_islemleri"',
    "karsi_taraflar": 'SELECT COUNT(*) FROM "karsi_taraflar"',
}

DEFAULT_FINANCE_ROOT = Path(r"C:\ai-excel")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": _sha256(path),
    }


def _readonly_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _inspect_database(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "error": "database not found"}

    connection = _readonly_connection(path)
    try:
        tables = [
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        columns: dict[str, list[str]] = {}
        missing_tables: list[str] = []
        missing_columns: dict[str, list[str]] = {}
        counts: dict[str, int] = {}
        for table, expected in EXPECTED_COLUMNS.items():
            if table not in tables:
                missing_tables.append(table)
                continue
            present = [
                str(row["name"])
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            ]
            columns[table] = present
            absent = [name for name in expected if name not in present]
            if absent:
                missing_columns[table] = absent
            counts[table] = int(
                connection.execute(COUNT_QUERIES[table]).fetchone()[0]
            )

        companies = [
            dict(row)
            for row in connection.execute(
                "SELECT faaliyet_key, ad, aktif FROM faaliyetler ORDER BY faaliyet_key"
            )
        ]
        accounts = [
            dict(row)
            for row in connection.execute(
                "SELECT kod, ad, hesap_tipi FROM hesaplar ORDER BY kod"
            )
        ]
        schema_version = None
        if "schema_meta" in tables:
            row = connection.execute(
                "SELECT deger FROM schema_meta WHERE anahtar='surum'"
            ).fetchone()
            schema_version = row["deger"] if row is not None else None

        return {
            "path": str(path),
            "exists": True,
            "read_only_uri": True,
            "table_count": len(tables),
            "tables": tables,
            "expected_tables": list(EXPECTED_TABLES),
            "missing_tables": missing_tables,
            "missing_columns": missing_columns,
            "counts": counts,
            "companies": companies,
            "accounts": accounts,
            "schema_version": schema_version,
            "compatible": not missing_tables and not missing_columns,
        }
    finally:
        connection.close()


def _inspect_workbook(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "sheets": [], "error": "not configured"}
    if not path.exists():
        return {"path": str(path), "exists": False, "sheets": [], "error": "not found"}
    try:
        with zipfile.ZipFile(path) as archive:
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8", "replace")
            zip_parts = len(archive.namelist())
        sheet_names = re.findall(r'<sheet[^>]*name="([^"]+)"', workbook_xml)
        sheets = [html.unescape(name) for name in sheet_names]
        return {
            "path": str(path),
            "exists": True,
            "sheets": sheets,
            "zip_parts": zip_parts,
        }
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        return {
            "path": str(path),
            "exists": True,
            "sheets": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _resolve_workbook(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    configured = os.environ.get("TOUCHE_MAIN_WORKBOOK")
    if configured:
        return Path(configured)
    desktop = Path.home() / "OneDrive" / "Desktop" / "Touche"
    candidates = sorted(
        path
        for path in desktop.glob("*.xlsx")
        if "_backup" not in path.name.casefold()
    )
    return candidates[0] if candidates else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only inspection of the TOUCHE FINANCE ledger and workbook."
    )
    parser.add_argument(
        "--finance-root",
        default=str(DEFAULT_FINANCE_ROOT),
        help="Finance working tree (default: C:\\ai-excel).",
    )
    parser.add_argument("--db", default=None, help="SQLite path (default: <root>/veri/finans.db).")
    parser.add_argument("--workbook", default=None, help="Master workbook path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    finance_root = Path(args.finance_root)
    database = Path(args.db) if args.db else finance_root / "veri" / "finans.db"
    workbook = _resolve_workbook(args.workbook)

    db_before = _file_state(database)
    wal = Path(f"{database}-wal")
    wal_before = _file_state(wal)
    workbook_before = _file_state(workbook) if workbook is not None else None

    database_info = _inspect_database(database)
    workbook_info = _inspect_workbook(workbook)

    db_after = _file_state(database)
    wal_after = _file_state(wal)
    workbook_after = _file_state(workbook) if workbook is not None else None

    unchanged = {
        "database": db_before == db_after,
        "database_wal": wal_before == wal_after,
        "workbook": workbook_before == workbook_after,
    }
    payload = {
        "finance_root": str(finance_root),
        "read_only": True,
        "database": database_info,
        "workbook": workbook_info,
        "unchanged": unchanged,
        "before": {
            "database": db_before,
            "database_wal": wal_before,
            "workbook": workbook_before,
        },
        "after": {
            "database": db_after,
            "database_wal": wal_after,
            "workbook": workbook_after,
        },
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"Finance root : {finance_root}")
        print(f"Database     : {database} (exists={database_info.get('exists')})")
        print(
            "Tables       : "
            f"{database_info.get('table_count', 0)}; compatible={database_info.get('compatible')}"
        )
        if database_info.get("missing_tables"):
            print(f"Missing      : {database_info['missing_tables']}")
        if database_info.get("missing_columns"):
            print(f"Missing cols : {database_info['missing_columns']}")
        print(f"Counts       : {database_info.get('counts', {})}")
        print(f"Workbook     : {workbook}")
        print(f"Sheets       : {workbook_info.get('sheets', [])}")
        print(f"Unchanged    : {unchanged}")

    return 0 if all(unchanged.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

