# Stage 12A — Bilingual shell foundation (not full translation)

**Scope delivered:** a typed EN/TR message catalog, browser-persisted language
setting, accessible language selector in the authenticated top bar, translation
of core top-bar labels and mobile navigation controls, tests for catalog
coverage.

The preferred language is stored only in the browser as
`localStorage["touche.commerce.locale"]` and may differ across devices. It
contains no user credentials, personal data or trade records. The initial SSR
language stays English; `useSyncExternalStore` applies the saved choice after
hydration and updates `html.lang`. No auth, session, database or API behavior
changes are introduced.

**Not done:** full translations of menus, forms, validations, pricing tables,
business reports, backend error messages, generated documents, emails, PDF
templates or locale-aware server rendering. Future slices must translate these
without changing stable stored identifiers, currency codes, original quotation
texts or decimal calculation logic. The current patch must never be reported
as fully bilingual product acceptance.

## Tests and acceptance

- Catalog EN/TR key parity and nonempty output.
- Existing frontend lint, typecheck, Vitest suite and Next.js build in CI.
- Actual browser: switch EN -> TR, inspect labeled top-bar controls, refresh,
  verify preference persists; switch back to EN; inspect screen reader labels
  and keyboard focus. These **interactive tests are not covered by CI here**.
- Further Stage 12 work should implement complete i18n across every workspace,
  personalized server-rendered locale and fully translated trade documents.
