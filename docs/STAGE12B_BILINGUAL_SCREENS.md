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
| Purchase orders, shipments and the document register (Stage 12F) | Purchase-order list and detail (items, history and evidence, procurement workflow: approve, record the send with channel and reference, supplier confirmation, cancel with reason, facts); shipment list, planner, detail (allocated quantities, timeline, logistics costs, references, milestone workflow, movement notes, cost and reference forms, shipping documents); the trade-document register (upload, draft invoice/packing-list preview, filters, verify/reject/archive). The upload and document-action components are shared with the sales-order page, which now also shows them in the reader's language. Words for shipment events, cost stages, reference types, linked-record kinds and tracking provenance are translated; the codes the API stores are not changed. Money, quantities, dates and file sizes follow the reader's language | vitest (EN + TR), Playwright (Chromium) |
| Sourcing and pricing (Stage 12E) | RFQ list, new RFQ, RFQ detail and lifecycle panel (prepare, send with channel and evidence, cancel with reason); supplier-quote list and detail and the quote-recording form; landed-cost scenario list and detail (stats, priced lines, cost components) and the pricing form; sales-quote list and detail, approval trail and workflow panel; FX snapshot list and form. Status words, cost types, bases and verification states are translated; the codes the API stores are not changed | vitest (EN + TR), Playwright (Chromium + WebKit) |

Stored trade data (names, descriptions, notes, SKUs) is never translated. Words the API stores in
English (`active`, `buyer`, `supplier`) keep their stored value and are shown in the reader's
language (`lib/i18n/value-labels.ts`). Error text that comes from the API (`message`) is shown as
the API sent it, except for the sign-in failures, which are mapped by error code.

## Still English only

finance (ledger, reconciliation, discrepancies, intelligence), AI Office,
communications, account and select-company pages, and the public status page. Each uses fixed
English strings inside the page; they need the same treatment (catalogue keys + `getServerT()` /
`useLocale()` + a Turkish test), roughly 11 screens. Two cross-cutting gaps remain: the breadcrumb
repeats "Workspace", and the browser-tab titles of the screens translated before Stage 12E are
still English (the screens of Stages 12E and 12F use `generateMetadata` and are translated).

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

## Numbers, dates and money (Stage 12E)

`formatMoney`, `formatQuantity`, `formatPercent`, `formatDate` and `formatTimestamp` take the
interface language and use `en-GB` or `tr-TR` (`lib/i18n/intl.ts`). Only separators, symbol
placement and month names change: the amount is parsed from the same string the API sent and the
currency is always the ISO code stored with it (`1,250.50` and `1.250,50` are the same number).
Locale, currency and time zone are separate: instants are shown in UTC in both languages (there is
no company time-zone setting), and a stored date such as `2026-10-24` is formatted in UTC so the day
does not change between the server and a browser in another zone. Screens translated before Stage
12E still format with the English default until their batch is revisited; every screen touched in
12E and later passes the reader's language.

## Stage 12E evidence

| Item | Result |
|---|---|
| Screens | 10 routes and 7 components: `/rfq`, `/rfq/new`, `/rfq/[id]`, `/quotes`, `/quotes/[id]`, `/pricing`, `/pricing/[id]`, `/sales-quotes`, `/sales-quotes/[id]`, `/fx-rates` |
| Catalogue | `lib/i18n/catalog/sourcing.ts`, about 330 keys per language, typed so a missing Turkish text does not compile |
| Unit tests | `sourcing-turkish.test.tsx` (status and cost words, RFQ panel, sales-quote workflow panel, pricing form, quote form), `formats.test.ts` (English output unchanged, Turkish separators and months, UTC dates) |
| Browser tests | `e2e/tests/sourcing.spec.ts` (4 journeys: Turkish read of every sourcing screen with the same figures in English, read-only role, a half-filled form surviving the language switch, FX snapshot recorded in Turkish) and `responsive.spec.ts` (Turkish pages at 375, 768, 1024 and 1440 px, plus the sourcing pages at phone width) on Chromium and WebKit (full suite: 87 of 88 passed; the one failure was an unrelated timing flake in `concurrency.spec.ts` that passed on re-run, see `STAGE11_20_STATUS.md`) |
| Financial figures | A fixture quote (purchase 160 + freight 40 = landed 200, 20 % margin on price = sales 250) is asserted as `200,00`/`250,00` in Turkish and `200.00`/`250.00` in English; no calculation code was touched |

## Stage 12F evidence

| Item | Result |
|---|---|
| Screens | 6 routes: `/purchase-orders`, `/purchase-orders/[id]`, `/shipments`, `/shipments/new`, `/shipments/[id]`, `/documents`; plus the shared upload and document-action components used on the sales-order page |
| Catalogue | `lib/i18n/catalog/logistics.ts`, 222 keys per language, typed so a missing Turkish text does not compile. `messages.test.ts` now also fails if two catalogues declare the same key (a spread silently kept the last one: `dealCountOne` was declared twice, with identical text, and one copy is removed) |
| Unit tests | `logistics-turkish.test.tsx` (every purchase-order, shipment, document-type, cost, reference and entity code has a word in both languages; purchase-order workflow, shipment milestones, cost form, planner and upload/verify components in Turkish; Turkish file sizes), `format.test.ts` (`unallocatedQuantity`). Frontend: 286 tests pass, lint, type check and Prettier clean |
| Browser tests | `e2e/tests/logistics.spec.ts` (4 journeys on a converted order with a supplier-confirmed purchase order, a draft one, an in-transit shipment with an incurred freight cost, a container reference and an uploaded document: read every screen in Turkish and the same figures in English; plan a second shipment, record a cost, book it, upload and verify a document in Turkish; cancel a draft purchase order with a reason, and only the approver is offered approval; a read-only role) and `responsive.spec.ts` (the four new list/planner pages at phone width and at 375, 768, 1024 and 1440 px in Turkish, plus the first order, purchase-order and shipment detail page at phone width in both languages). **Chromium: full suite 50 passed, 5 live-integration specs skipped, 0 failed. WebKit was not run for this batch**: the sandbox could not download the pinned WebKit build (`cdn.playwright.dev` is blocked), so the WebKit result for 12F is unverified |
| Financial figures | Purchase cost 100 kg x 1.60 = `160,00` and incurred freight `512,50` are asserted in Turkish, `512.50` in English; no calculation code was touched |

### Defects found while doing 12F

1. **The shipment planner offered the wrong quantity.** It showed and pre-filled each line's
   "remaining" quantity, which the API measures against *delivered* goods. After a first partial
   shipment of 40 of 100 kg the form still offered 100 kg, and submitting it was refused ("exceeds the
   quantity still outstanding"). The form now offers ordered minus allocated (`unallocatedQuantity`,
   unit-tested and covered by a journey).
2. **`/documents` scrolled sideways on a phone.** Fixed-width selects (320 px) plus card padding
   forced the single-column grid wider than the screen (378 px in a 375 px viewport, Chromium; the
   earlier WebKit overflow on this page has the same cause but was not re-measured in WebKit). The
   selects now fill the width on a phone and keep their fixed width from the `sm` breakpoint.
3. **Order, purchase-order and shipment detail pages scrolled sideways on a phone** (page width 501 to
   604 px at 375 px). The two-column grid had no explicit single-column track, so the widest table in a
   card set the column width. The grids now start as `grid-cols-1` and use `minmax(0, ...)` columns from
   `lg`, and a table scrolls inside its own card. These pages were not in the phone-width check
   (only lists were), so this had gone unnoticed.
4. The duplicate `dealCountOne` key noted above.

### Known gaps after 12F

* The detail pages of **quotes, pricing, sales quotes and deals** (Stages 12D/12E) have the same
  two-column grid pattern and still scroll sideways on a phone (measured at 375 px: 558, 756, 558
  and 431 px). The finance detail pages use the same pattern and have not been measured. Not changed
  here; the fix is the same one-line grid change and the responsive spec has the loop to extend.
* WebKit for 12F (see above), and the intermittent `concurrency.spec.ts` "identical file" failure
  already recorded for 12E: it failed once in a full Chromium run here and passed twice alone and in
  the final full run.
* The "occurred at" field of the shipment movement-note form defaults to the current UTC time but is
  read back as local time, so the default can be off by the browser's UTC offset. Not changed.
