import { expect, test } from "@playwright/test";

import { csvFile, productsCsv, reachReview, runId, signedInContext } from "./support";

test.describe("import wizard, end to end", () => {
  test("a trader imports a product file once; the same file cannot be imported twice", async ({
    browser,
    browserName,
  }) => {
    const prefix = `E2E${runId()}`;
    const file = csvFile("katalog.csv", productsCsv(prefix, 3));
    const context = await signedInContext(browser, "sales", browserName);
    const page = await context.newPage();

    const summary = await reachReview(page, file);
    expect(summary).toContain("3 rows · 3 new · 0 already exist · 0 invalid");
    const commit = page.getByRole("button", { name: "Import 3 records" });
    await expect(commit).toBeDisabled();
    await page.getByLabel(/I reviewed this preview/).check();
    await expect(commit).toBeEnabled();
    await commit.click();

    await expect(page.getByText("Import finished")).toBeVisible();
    await expect(page.getByText("3 created, 0 skipped.")).toBeVisible();

    await page.goto(`/products?search=${prefix}`);
    await expect(page.getByRole("table")).toContainText(`${prefix}-01`);
    await expect(page.getByRole("table")).toContainText(`${prefix}-03`);

    // The very same file again: the ledger recognises it and refuses to write.
    await reachReview(page, file);
    await expect(
      page.getByText("This exact file was already imported into this company."),
    ).toBeVisible();
    await page.getByLabel(/I reviewed this preview/).check();
    await expect(page.getByRole("button", { name: /^Import \d+ records$/ })).toBeDisabled();

    await page.goto("/imports");
    await expect(page.getByRole("table")).toContainText("katalog.csv");
    await context.close();
  });

  test("existing records are flagged and must be skipped explicitly", async ({
    browser,
    browserName,
  }) => {
    const prefix = `E2E${runId()}X`;
    const context = await signedInContext(browser, "purchasing", browserName);
    const page = await context.newPage();

    await reachReview(page, csvFile("first.csv", productsCsv(prefix, 2)));
    await page.getByLabel(/I reviewed this preview/).check();
    await page.getByRole("button", { name: "Import 2 records" }).click();
    await expect(page.getByText("Import finished")).toBeVisible();

    // A different file that repeats one SKU and adds one new SKU.
    const mixed = `${productsCsv(prefix, 1)}${prefix}-99,Another,kg,USD,9.5000\n`;
    const summary = await reachReview(page, csvFile("second.csv", mixed));
    expect(summary).toContain("2 rows · 1 new · 1 already exist · 0 invalid");
    await page.getByLabel(/I reviewed this preview/).check();
    await expect(page.getByText(/Some records already exist/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Import 1 records" })).toBeDisabled();
    await page.getByLabel(/Skip records that already exist/).check();
    await page.getByRole("button", { name: "Import 1 records" }).click();
    await expect(page.getByText("1 created, 1 skipped.")).toBeVisible();
    await context.close();
  });

  test("invalid rows block the import and a formula cell never becomes a record", async ({
    browser,
    browserName,
  }) => {
    const prefix = `E2E${runId()}B`;
    const context = await signedInContext(browser, "operations", browserName);
    const page = await context.newPage();

    const bad = `sku,name,unit,currency,unit_price\n${prefix}-1,Fine,kg,USD,1.0000\n${prefix}-2,Broken,kg,USD,-5\n`;
    const summary = await reachReview(page, csvFile("bad.csv", bad));
    expect(summary).toContain("1 invalid");
    await expect(
      page.getByText("Fix the invalid rows in the file and upload it again."),
    ).toBeVisible();
    await page.getByLabel(/I reviewed this preview/).check();
    await expect(page.getByRole("button", { name: /^Import \d+ records$/ })).toBeDisabled();

    const response = await page.request.get(`/api/v1/products?search=${prefix}`);
    expect((await response.json()).items).toHaveLength(0);
    await context.close();
  });

  test("Turkish column headings are recognised and customers and suppliers import", async ({
    browser,
    browserName,
  }) => {
    const suffix = runId();
    const firms =
      `firma_adı,firma_türü,ülke,e_posta\nAnadolu Gıda ${suffix},supplier,TR,satis@example.com\n` +
      `Rotterdam Foods ${suffix},buyer,NL,buy@example.com\n`;
    const context = await signedInContext(browser, "sales", browserName);
    const page = await context.newPage();
    const summary = await reachReview(page, csvFile("firmalar.csv", firms), "counterparties");
    expect(summary).toContain("2 rows · 2 new");
    await page.getByLabel(/I reviewed this preview/).check();
    await page.getByRole("button", { name: "Import 2 records" }).click();
    await expect(page.getByText("2 created, 0 skipped.")).toBeVisible();
    await page.goto(`/crm?search=${encodeURIComponent(`Anadolu Gıda ${suffix}`)}`);
    await expect(page.locator("main")).toContainText(`Anadolu Gıda ${suffix}`);
    await context.close();
  });
});
