# Stage 13A — Excel / CSV safe import preview

**Scope:** bounded, local-only **preview** for product catalogue and customer/
supplier entries. Operators can prepare real spreadsheets without a database
write, message send, business-object creation or alteration of price history.

## Usage

From `backend` after `pip install -e ".[dev]"`:

```powershell
python -m scripts.preview_import --kind products --file .\katalog.xlsx
python -m scripts.preview_import --kind counterparties --file .\firmalar.csv
```

The CLI returns counts and per-row validation errors without showing names,
emails or prices by default. With `--show-records`, it prints commercial
content **only in the operator's local terminal**. Do not paste that output into
GitHub issues, public logs or AI prompts.

### Product columns

`sku,name,unit,currency,unit_price`. Unit must be one of `kg,mt,lb,unit,l,m3`;
currency is three letters (use TRY/USD/EUR per owner agreement); price is an
exact non-negative decimal with up to four fractional places. All columns are
required. Some Turkish aliases supported: `stok_kodu`, `ürün_adı`,
`birim`, `para_birimi`, `birim_fiyat`.

### Counterparty columns

`name` is required. Optional `type` (buyer/supplier/both), `country`
(two-letter country code), `contact_name`, `email`, `phone`, `notes`.
Turkish headers include `firma_adı`, `firma_türü`, `ülke`,
`irtibat_kişisi`, `e_posta`, `telefon`, `notlar`.

The parser uses the existing Pydantic models from Trade Core, so incompatible
records are rejected instead of silently coerced. It checks duplicate SKU /
counterparty names **within the incoming file**; comparison against existing
PostgreSQL records is not possible at this preview-only stage.

## Controls

- Input CSV is UTF-8 or UTF-8 BOM; XLSX is parsed read-only by openpyxl.
- File <=2 MB, max 500 data rows and 24 columns; XLSX member size, archive
  expanded size and compression ratio have separate ceilings.
- Formula cells, macros/XLSM, unexpected header fields and ambiguous mappings
  fail closed. No formula evaluation or external Excel link resolution.
- No DB sessions, audit writes, price overwrites, import commits or cloud uploads.
- `--show-records` intentionally includes real values; handle locally and
  according to company access controls.

## Next: Stage 13B required for operational import

Add authenticated UI/API with company-scoped `trade.write` authorization,
preflight preview, explicit review, source/hash, deduplication vs live records,
idempotent atomic batch save, append-only audit and rollback/compensating
procedure. Add multi-language mapping UI and per-company effective dated price
history. That is not completed by the CLI preview.
