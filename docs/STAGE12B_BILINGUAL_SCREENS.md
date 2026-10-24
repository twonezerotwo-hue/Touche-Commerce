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
| Command Center (dashboard) | Greeting, KPI tiles, recent deals, pipeline and status cards, audit trail, platform health, execution strip; the deal status words (Draft/Open/Negotiation/Won/Lost/Cancelled) are translated wherever the badge appears | vitest, Playwright |
| Deals | List with status filters and search, new-deal page and form, detail (figures, lines, history, conversion area), edit form, status transition panel; singular/plural counts | vitest (EN + TR), Playwright (Chromium + WebKit) |
| Sales orders | Order list, order detail (accepted lines, fulfilment, shipments, trade documents, draft invoice preview, accepted commercial terms), cancel/confirm actions with the mandatory reason, the acceptance-and-conversion form; the 24 operations status codes, 14 document types, transport modes, fulfilment models and acceptance channels are shown as words | vitest (EN + TR), Playwright (Chromium + WebKit) |

Stored trade data (names, descriptions, notes, SKUs) is never translated. Words the API stores in
English (`active`, `buyer`, `supplier`) keep their stored value and are shown in the reader's
language (`lib/i18n/value-labels.ts`). Error text that comes from the API (`message`) is shown as
the API sent it, except for the sign-in failures, which are mapped by error code.

## Still English only

RFQs, supplier quotes, pricing, sales quotes, FX snapshots, purchase orders, shipments, the
trade-document register, finance (ledger, reconciliation, discrepancies, intelligence), AI Office,
communications, account and select-company pages, and the public status page. Each uses fixed
English strings inside the page; they need the same treatment (catalogue keys + `getServerT()` /
`useLocale()` + a Turkish test), roughly 25 screens. Two cross-cutting gaps remain: timestamps
still show English month names, and the breadcrumb repeats "Workspace".

## How to translate another screen

1. Add keys to a catalogue in `frontend/src/lib/i18n/catalog/` (English first; the Turkish object is
   typed `Record<keyof typeof english, string>`, so a missing translation does not compile).
2. Server component: `const { t } = await getServerT();` — client component: `const { t } = useLocale();`.
3. Add a Turkish test; `messages.test.ts` already checks key parity, placeholders and that no
   Turkish text silently equals the English one.

## Defects found while doing this

Doing the screens one by one in a real browser found five real problems, all fixed:

1. `CounterpartyForm` (shipped in Stage 1B) returned the form inside the `if (!open)` branch after an
   earlier `return`, so the form was unreachable: clicking "New counterparty" made the component
   render nothing and a trader could not create a customer or supplier from the CRM page. A
   Playwright journey (create in English, create in Turkish) now covers it in Chromium and WebKit.
2. `DealForm` had the same defect: "Open a trade deal" could never render. `allowUnreachableCode:
   false` is now enforced in `frontend/tsconfig.json`, so the compiler rejects this class of bug,
   and a Playwright journey creates a deal through the form.
3. The deal page said "Won stays disabled until sales orders exist in a later stage", which stopped
   being true when order conversion shipped. The copy now says a deal becomes Won only when a sales
   order is created from it.
4. The conversion form pre-filled the customer's acceptance time rounded *down to the minute*. A
   conversion done within the minute of the internal approval was refused by the API with "The
   acceptance cannot predate the internal approval of this revision." The default is now never
   earlier than the approval. To do this the sales-quote list API exposes `approved_at` (new,
   optional field; covered by `backend/tests/test_sales_quote_list.py` and the regenerated API
   types) and `defaultAcceptedAt` has unit tests.
5. On a phone-width WebKit (iPhone Safari) any table with rows scrolled the whole page sideways: the
   visually hidden column header text is absolutely positioned and the table's scroll container was
   not its containing block, so it escaped the clip. It had gone unnoticed because the phone-width
   check ran while the deal list was still empty. The scroll container in `ui/table.tsx` is now
   `relative`, and the phone-width spec also visits `/deals` and `/orders` with data present.
