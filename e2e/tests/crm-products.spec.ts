import { expect, test } from "@playwright/test";

import { gotoReady, runId, signedInContext } from "./support";

test.describe("CRM and product catalogue, in both languages", () => {
  test("a trader creates a counterparty and a product in English", async ({
    browser,
    browserName,
  }) => {
    const name = `Anadolu Gıda ${runId()}`;
    const sku = `E2E-${runId()}`;
    const context = await signedInContext(browser, "sales", browserName);
    const page = await context.newPage();

    await gotoReady(page, "/crm");
    await page.getByRole("button", { name: "New counterparty" }).click();
    await page.getByLabel("Name", { exact: true }).fill(name);
    await page.getByLabel("Type", { exact: true }).selectOption("supplier");
    await page.getByLabel("Country", { exact: true }).fill("TR");
    await page.getByRole("button", { name: "Create counterparty" }).click();
    await expect(page.getByText(`${name} added.`)).toBeVisible();
    await page.waitForLoadState("networkidle");
    await gotoReady(page, `/crm?search=${encodeURIComponent(name)}`);
    const row = page.getByRole("row", { name: new RegExp(name) });
    await expect(row).toContainText("Supplier");
    await expect(row).toContainText("Active");

    await gotoReady(page, "/products");
    await page.getByRole("button", { name: "New product" }).click();
    await page.getByLabel("SKU", { exact: true }).fill(sku.toLowerCase());
    await page.getByLabel("Name", { exact: true }).fill("Sugar beet pulp");
    await page.getByLabel("Unit price", { exact: true }).fill("245.5");
    await page.getByRole("button", { name: "Create product" }).click();
    await expect(page.getByText(`${sku} added.`)).toBeVisible(); // stored in upper case
    await page.waitForLoadState("networkidle");
    await gotoReady(page, `/products?search=${sku}`);
    await expect(page.getByRole("table")).toContainText("Sugar beet pulp");
    await context.close();
  });

  test("the same screens work in Turkish and keep stored values intact", async ({
    browser,
    browserName,
  }) => {
    const name = `Rotterdam Foods ${runId()}`;
    const sku = `TR-${runId()}`;
    const context = await signedInContext(browser, "purchasing", browserName);
    const page = await context.newPage();
    await gotoReady(page, "/crm");
    await page.getByLabel("Interface language", { exact: true }).selectOption("tr");
    await expect(page.getByRole("heading", { name: "Müşteriler ve tedarikçiler" })).toBeVisible();

    await page.getByRole("button", { name: "Yeni karşı taraf" }).click();
    await page.getByLabel("Ad", { exact: true }).fill(name);
    await page.getByLabel("Tür", { exact: true }).selectOption("buyer");
    await page.getByRole("button", { name: "Karşı taraf oluştur" }).click();
    await expect(page.getByText(`${name} eklendi.`)).toBeVisible();
    await page.waitForLoadState("networkidle");
    await gotoReady(page, `/crm?search=${encodeURIComponent(name)}`);
    await expect(page.getByRole("columnheader", { name: "Tür" })).toBeVisible();
    const row = page.getByRole("row", { name: new RegExp(name) });
    await expect(row).toContainText("Alıcı");
    await expect(row).toContainText("Aktif"); // the API stores "active"; the reader sees "Aktif"

    await gotoReady(page, "/products");
    await expect(page.getByRole("heading", { name: "Ürün kataloğu" })).toBeVisible();
    await page.getByRole("button", { name: "Yeni ürün" }).click();
    await page.getByLabel("Stok kodu", { exact: true }).fill(sku);
    await page.getByLabel("Ad", { exact: true }).fill("Şeker pancarı küspesi");
    await page.getByLabel("Birim fiyat", { exact: true }).fill("245.5");
    await page.getByRole("button", { name: "Ürün oluştur" }).click();
    await expect(page.getByText(`${sku} eklendi.`)).toBeVisible();
    await page.waitForLoadState("networkidle");
    await gotoReady(page, `/products?search=${sku}`);
    await expect(page.getByRole("table")).toContainText("Şeker pancarı küspesi");
    await expect(page.getByRole("columnheader", { name: "Stok kodu" })).toBeVisible();

    await context.close();
  });

  test("a read-only role sees the list but is told it cannot add records", async ({
    browser,
    browserName,
  }) => {
    const context = await signedInContext(browser, "viewer", browserName);
    const page = await context.newPage();
    await gotoReady(page, "/crm");
    await expect(page.getByText("Read-only access")).toBeVisible();
    await expect(page.getByRole("button", { name: "New counterparty" })).toHaveCount(0);
    await gotoReady(page, "/products");
    await expect(page.getByText("Read-only access")).toBeVisible();
    await context.close();
  });

  test("the sign-in page is bilingual and the choice carries into the app", async ({ page }) => {
    await gotoReady(page, "/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await page.getByLabel("Interface language", { exact: true }).selectOption("tr");
    await expect(page.getByRole("heading", { name: "Giriş yap" })).toBeVisible();
    await expect(page.getByLabel("E-posta")).toBeVisible();
    await page.getByRole("button", { name: "Giriş yap" }).click();
    await expect(page.getByText("İş e-posta adresinizi girin.")).toBeVisible();
  });
});
