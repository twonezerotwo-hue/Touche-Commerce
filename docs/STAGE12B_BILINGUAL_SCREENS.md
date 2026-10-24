# Stage 12B — Turkish/English screens (what is and is not translated)

Status: **partial, honestly scoped.** The language mechanism (Stage 12A: cookie, server-rendered,
typed catalogues with parity tests) is complete. Screen coverage is not.

## Translated end to end (TR and EN, with tests)

| Area | What is covered | Tests |
|---|---|---|
| Shell | Navigation labels, top bar, language switcher, breadcrumbs | vitest, Playwright |
| Sign-in | Page, form, validation messages, server failure messages (wrong password, rate limit), the public frame; a language switcher on the login page itself | vitest (EN + TR), Playwright |
| Import wizard | All four steps, preview/review table, history | vitest, Playwright |
| Company profile | Form, field labels, missing-information notice, conflict and read-only messages | vitest, Playwright |
| Document downloads | Panel, formats, per-download language; the documents themselves (PDF/DOCX/XLSX/CSV) are generated in the chosen language | vitest, pytest, Playwright |
| Customers & suppliers (CRM) | List, filters, empty states, columns, status/type words, create form | vitest, Playwright |
| Product catalogue | List, filters, empty states, columns, status words, create form | vitest, Playwright |

Stored trade data (names, descriptions, notes, SKUs) is never translated. Words the API stores in
English (`active`, `buyer`, `supplier`) keep their stored value and are shown in the reader's
language (`lib/i18n/value-labels.ts`). Error text that comes from the API (`message`) is shown as
the API sent it, except for the sign-in failures, which are mapped by error code.

## Still English only

Command Center (dashboard) and its cards, deals (list, detail, new), RFQs, supplier quotes,
pricing, sales quotes, FX snapshots, sales orders, purchase orders, shipments, trade documents,
finance (ledger, reconciliation, discrepancies, intelligence), AI Office, communications, account
and select-company pages, and the public status page. Each uses fixed English strings inside the
page; they need the same treatment (catalogue keys + `getServerT()` / `useLocale()` + a Turkish
test), roughly 35 screens.

## How to translate another screen

1. Add keys to a catalogue in `frontend/src/lib/i18n/catalog/` (English first; the Turkish object is
   typed `Record<keyof typeof english, string>`, so a missing translation does not compile).
2. Server component: `const { t } = await getServerT();` — client component: `const { t } = useLocale();`.
3. Add a Turkish test; `messages.test.ts` already checks key parity, placeholders and that no
   Turkish text silently equals the English one.

## Defect found while doing this

`CounterpartyForm` (shipped in Stage 1B) returned the form inside the `if (!open)` branch after an
earlier `return`, so the form was unreachable: clicking "New counterparty" made the component
render nothing and a trader could not create a customer or supplier from the CRM page. Fixed; a
Playwright journey (create in English, create in Turkish) now covers it in Chromium and WebKit.
