import { expect, test } from "@playwright/test";

import { gotoReady, loginViaUi } from "./support";

/**
 * Opt-in: needs a running Finance service, a verified mapping for the acceptance company
 * (`python -m scripts.acceptance_finance_map <finance-company-key>` in backend/) and the
 * acceptance stack started with the Finance connector variables. Run with E2E_FINANCE_LIVE=1.
 * Finance data is only ever read; nothing here writes to Finance.
 */
test.skip(!process.env.E2E_FINANCE_LIVE, "set E2E_FINANCE_LIVE=1 with a live Finance service");

test.describe("Finance, read-only, live", () => {
  test("the mapped company reads the real ledger through Commerce", async ({ page }) => {
    await loginViaUi(page, "owner");
    await page.waitForURL((url) => !url.pathname.startsWith("/login"));

    const status = await (await page.request.get("/api/v1/finance/status")).json();
    expect(status.state).toBe("connected");
    expect(status.mapping.status).toBe("verified");
    expect(status.read_only).toBe(true);
    expect(status.available_currencies.length).toBeGreaterThan(1);

    // A company with several ledger currencies must choose one; nothing is converted.
    const missing = await page.request.get("/api/v1/finance/summary");
    expect(missing.status()).toBe(409);
    expect((await missing.json()).error.code).toBe("FINANCE_CURRENCY_REQUIRED");

    const currency = status.available_currencies[0] as string;
    const summary = await page.request.get(`/api/v1/finance/summary?currency=${currency}`);
    expect(summary.status()).toBe(200);
    expect((await summary.json()).source).toBe("finance_ledger");
    const accounts = await page.request.get(`/api/v1/finance/accounts?currency=${currency}`);
    expect(accounts.status()).toBe(200);
    for (const kind of ["receivable", "payable"]) {
      const aging = await page.request.get(
        `/api/v1/finance/aging?type=${kind}&currency=${currency}`,
      );
      expect(aging.status(), kind).toBe(200);
    }
    const invalid = await page.request.get("/api/v1/finance/summary?currency=XXX");
    expect(invalid.status()).toBe(400);

    // The page tells the person to choose a currency, then shows the ledger for it.
    await gotoReady(page, "/finance");
    await expect(page.getByText("Select one currency")).toBeVisible();
    await page.getByLabel("Currency").selectOption(currency);
    await page.getByRole("button", { name: "Apply" }).click();
    await expect(page.getByText("Select one currency")).toHaveCount(0);
    await expect(page.getByText(/never posts an invoice, payment or journal entry/)).toBeVisible();
  });

  test("a company without a mapping sees no Finance data", async ({ page }) => {
    await loginViaUi(page, "outsider");
    await page.waitForURL((url) => !url.pathname.startsWith("/login"));
    const status = await (await page.request.get("/api/v1/finance/status")).json();
    expect(status.state).toBe("not_configured");
    expect(status.mapping).toBeNull();
    const summary = await page.request.get("/api/v1/finance/summary?currency=TL");
    expect(summary.status()).toBe(409);
    expect((await summary.json()).error.code).toBe("FINANCE_NOT_CONFIGURED");
  });

  test("Commerce offers no way to write to Finance", async ({ page }) => {
    await loginViaUi(page, "owner");
    await page.waitForURL((url) => !url.pathname.startsWith("/login"));
    for (const path of ["/api/v1/finance/summary", "/api/v1/finance/accounts"]) {
      const response = await page.request.post(path, { data: {} });
      expect([404, 405, 403]).toContain(response.status());
    }
  });
});
