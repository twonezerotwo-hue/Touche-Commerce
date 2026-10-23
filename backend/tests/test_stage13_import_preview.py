"""Stage 13A: safe CSV/XLSX preview uses current trade validators."""

from __future__ import annotations

import io
import zipfile

import pytest
from openpyxl import Workbook

from app.services.import_preview import ImportPreviewError, preview_import


def xlsx_bytes(header: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    active = workbook.active
    assert active is not None
    active.append(header)
    for row in rows:
        active.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def test_product_csv_preview_preserves_decimal_and_never_commits() -> None:
    content = (
        "sku,name,unit,currency,unit_price\n"
        "ABC-01,Aluminium bar,kg,USD,1250.1234\n"
        "ABC-01,Duplicate,kg,USD,1240.0000\n"
        "ABC-02,Wrong unit,t,EUR,10\n"
    ).encode()
    preview = preview_import("products.csv", content, kind="products")
    assert preview.committed is False
    assert preview.total_rows == 3
    assert preview.accepted == 1
    assert preview.rejected == 2
    assert preview.rows[0].values["unit_price"] == "1250.1234"
    assert preview.rows[1].errors == ("Duplicate key within file",)
    assert "unit" in preview.rows[2].errors[0]


def test_turkish_csv_headers_and_bom_are_supported() -> None:
    content = (
        "\ufefffirma_adı,firma_türü,ülke,e_posta\n"
        "Örnek Ltd,supplier,TR,hi@example.com\n"
    ).encode()
    preview = preview_import("firmalar.csv", content, kind="counterparties")
    assert preview.accepted == 1
    assert preview.rows[0].values["name"] == "Örnek Ltd"
    assert preview.rows[0].values["country"] == "TR"


def test_xlsx_preview_reads_real_workbook() -> None:
    content = xlsx_bytes(
        ["sku", "name", "unit", "currency", "unit_price"],
        [["U-22", "Insulated cable", "unit", "TRY", 230.5]],
    )
    preview = preview_import("katalog.xlsx", content, kind="products")
    assert preview.accepted == 1
    assert preview.rows[0].values["unit_price"] == "230.5"
    assert preview.source_type == "xlsx"


def test_no_formulas_evaluated_or_silent_conversion() -> None:
    content = xlsx_bytes(
        ["sku", "name", "unit", "currency", "unit_price"],
        [["U-23", "Widget", "unit", "TRY", "=SUM(A1:A5)"]],
    )
    with pytest.raises(ImportPreviewError, match="formulas"):
        preview_import("katalog.xlsx", content, kind="products")


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("data.xlsm", b"macro"),
        ("data.xls", b"binary"),
        ("data.csv", b""),
        ("data.csv", b"x" * 2_000_001),
        ("data.xlsx", b"not-a-zip"),
        ("data.csv", b"\xff\xff"),
    ],
)
def test_unsafe_or_unsupported_files_rejected(name: str, data: bytes) -> None:
    with pytest.raises(ImportPreviewError):
        preview_import(name, data, kind="products")


def test_oversized_xlsx_payload_rejected_before_parser() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", "a" * 16_000_001)
    with pytest.raises(ImportPreviewError):
        preview_import("catalog.xlsx", stream.getvalue(), kind="products")


def test_csv_formula_and_invalid_fields_fail_closed() -> None:
    with pytest.raises(ImportPreviewError, match="formula"):
        preview_import(
            "counterparties.csv", b"name,type\n=HYPERLINK(...),supplier\n",
            kind="counterparties",
        )
    with pytest.raises(ImportPreviewError, match="Required"):
        preview_import("prices.csv", b"sku,name\na,any\n", kind="products")
    with pytest.raises(ImportPreviewError, match="Unknown column"):
        preview_import(
            "prices.csv",
            b"sku,name,unit,currency,unit_price,unexpected\na,b,kg,USD,2,x\n",
            kind="products",
        )


def test_duplicate_headers_from_alias_are_rejected() -> None:
    with pytest.raises(ImportPreviewError, match="Duplicate normalized"):
        preview_import(
            "products.csv",
            "sku,name,ürün_adı,unit,currency,unit_price\na,b,b,kg,EUR,1\n".encode(),
            kind="products",
        )


def test_500_row_cap_applies_to_data_only() -> None:
    headings = "sku,name,unit,currency,unit_price\n"
    rows = "".join(f"K{n},Cable,unit,EUR,5\n" for n in range(500))
    preview = preview_import("x.csv", (headings + rows).encode(), kind="products")
    assert preview.total_rows == 500
    with pytest.raises(ImportPreviewError, match="500"):
        preview_import(
            "x.csv", (headings + rows + "LAST,Cable,unit,EUR,5\n").encode(), kind="products"
        )
