import { expect, test } from "@playwright/test";

import { csvFile, productsCsv, reachReview, runId, signedInContext } from "./support";

test.describe("company isolation", () => {
  test("another company never sees, or can fetch, this company's records", async ({
    browser,
    browserName,
  }) => {
    const prefix = `ISO${runId()}`;
    const sales = await signedInContext(browser, "sales", browserName);
    const salesPage = await sales.newPage();
    await reachReview(salesPage, csvFile("iso.csv", productsCsv(prefix, 2)));
    await salesPage.getByLabel(/I reviewed this preview/).check();
    await salesPage.getByRole("button", { name: "Import 2 records" }).click();
    await expect(salesPage.getByText("Import finished")).toBeVisible();

    const own = await salesPage.request.get(`/api/v1/products?search=${prefix}`);
    expect((await own.json()).items).toHaveLength(2);

    const outsider = await signedInContext(browser, "outsider", browserName);
    const page = await outsider.newPage();
    await page.goto(`/products?search=${prefix}`);
    await expect(page.locator("main")).not.toContainText(`${prefix}-01`);

    const foreign = await page.request.get(`/api/v1/products?search=${prefix}`);
    expect(foreign.status()).toBe(200);
    expect((await foreign.json()).items).toHaveLength(0);

    const ledger = await page.request.get("/api/v1/imports");
    const filenames = ((await ledger.json()).items as { filename: string }[]).map(
      (item) => item.filename,
    );
    expect(filenames).not.toContain("iso.csv");
    await sales.close();
    await outsider.close();
  });
});
