# Stage 13B — controlled local CSV/XLSX import

**Scope:** import new products and counterparties into the existing Commerce
database with one atomic transaction, under an active TRADE_WRITE membership.
This supplements Stage 13A's preview parser. The browser import wizard and
effective-dated supplier prices are still outstanding.

## Safety rules

- Runs only in LOCAL/TEST/CI. Production and staging are deliberately blocked.
- Never touches Finance accounting or E-YAY.
- Requires an existing company, active trade-writer email, exact file hash
  challenge, and an operator-attested isolated backup restore from the last week.
- File must pass the Stage 13A validation with zero invalid rows.
- Any pre-existing name/SKU blocks the entire transaction. Existing records
  cannot be overwritten. Repeat imports are safely refused, but a durable
  job-based idempotency ledger is still missing.
- Every created record has the existing transactional audit trail.
- Output summarizes counts; it does not log customers or prices.
- No messaging, accounting posting or AI transmission occurs.

## Local operator workflow

From the backend directory use Python 3.12 and the established private .env.

1. Run: python -m scripts.preview_import --kind products --file katalog.xlsx
2. Restore the latest backup on a dedicated isolated test DB, recording the date.
3. Run the dry preview: python -m scripts.apply_import --kind products --file katalog.xlsx --company "Company" --actor "trader@example.com"
4. Verify file/rows/actor/company and copy the reported IMPORT challenge.
5. Only after approval, rerun with --commit --restore-tested YYYY-MM-DD
   --confirm "IMPORT <reported-12-hex>" and the same company, actor and file.

Role ADMIN does not automatically have trade.write. Use an active TRADER.
The operator supplies private migration-role credentials locally, never in
GitHub, chat or command-line arguments.

## Still required

Authenticated TR/EN browser import, preview/mapping confirmation, secure
uploads, a durable idempotent job ledger, per-company price histories, PDF
and Office commercial document templates, and real Windows/Mac acceptance.
Do not import customer data into an unverified free cloud preview.

This code is NOT proof of Stage 13 full production acceptance.
