import { expect, test, type BrowserContext } from "@playwright/test";

import { gotoReady, runId, signedInContext, stack } from "./support";
import { createMasterData, prepareApprovedQuote } from "./trade";

async function inTurkish(context: BrowserContext): Promise<void> {
  await context.addCookies([{ name: "touche_locale", value: "tr", url: stack().web }]);
}

test.describe("deals, in a real browser, in both languages", () => {
  test("a trader opens a deal, moves it forward and reads it in Turkish", async ({
    browser,
    browserName,
  }) => {
    const data = await createMasterData(browser, browserName);
    const title = `Almond shipment ${runId()}`;
    const context = await signedInContext(browser, "sales", browserName);
    const page = await context.newPage();

    // The form once rendered nothing at all, so this journey is the regression guard.
    await gotoReady(page, "/deals/new");
    await expect(page.getByRole("heading", { name: "Open a trade deal" })).toBeVisible();
    await page.getByLabel("Title", { exact: true }).fill(title);
    await page
      .getByLabel("Counterparty", { exact: true })
      .selectOption({ label: `${data.customerName} · Buyer` });
    await page
      .getByLabel("Product", { exact: true })
      .selectOption({ label: `${data.sku} · ${data.productName}` });
    await page.getByLabel(/^Quantity/).fill("250");
    await page.getByRole("button", { name: "Create deal" }).click();
    await page.waitForURL(/\/deals\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { level: 1, name: new RegExp(title) })).toBeVisible();

    await page.getByRole("button", { name: "Open", exact: true }).click();
    await page.getByRole("button", { name: "Confirm Open" }).click();
    await expect(page.getByText("Deal moved to Open.")).toBeVisible();

    await page.getByLabel("Interface language").selectOption("tr");
    await expect(page.getByText("Bu anlaşmayı ilerlet")).toBeVisible();
    await expect(page.getByText("Ticari kalemler")).toBeVisible();
    await expect(page.getByText("Kayıtlı geçişler")).toBeVisible();
    await expect(page.getByText("Satış siparişine dönüştür")).toBeVisible();
    await expect(page.locator("main").getByText("Açık", { exact: true }).first()).toBeVisible();

    await gotoReady(page, `/deals?search=${encodeURIComponent(title)}`);
    await expect(page.getByRole("heading", { level: 1, name: "Anlaşmalar" })).toBeVisible();
    const row = page.getByRole("row", { name: new RegExp(title) });
    await expect(row).toContainText("Açık");
    await expect(page.getByRole("link", { name: "Tümü" })).toBeVisible();
    await context.close();
  });

  test("a read-only role sees a deal but cannot move it", async ({ browser, browserName }) => {
    const approved = await prepareApprovedQuote(browser, browserName);
    const viewer = await signedInContext(browser, "viewer", browserName);
    const page = await viewer.newPage();
    await gotoReady(page, `/deals/${approved.dealId}`);
    await expect(page.getByText("Moving a deal requires trade.write.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Confirm Negotiation" })).toHaveCount(0);
    await viewer.close();
  });
});

test.describe("sales orders, from acceptance to cancellation", () => {
  test("the customer's acceptance converts the deal in Turkish and the order is cancelled with a reason", async ({
    browser,
    browserName,
  }) => {
    const approved = await prepareApprovedQuote(browser, browserName);
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, `/deals/${approved.dealId}`);
    await expect(page.getByText("Onay, kabul değildir")).toBeVisible();
    await expect(page.getByLabel("Onaylı teklif revizyonu")).toBeVisible();
    await page.getByLabel(/Kabul eden/).fill("Dana Buyer");
    await page.getByLabel("Kanıt referansı").fill(`İmzalı teklif ${approved.quoteNumber}`);
    await page.getByRole("button", { name: "Onayı kaydet ve dönüştür" }).click();
    await page.waitForURL(/\/orders\/[0-9a-f-]{36}$/);

    for (const text of [
      "Kabul edilen kalemler",
      "Karşılama",
      "Henüz sevkiyat yok. Siparişin bir bölümünü tahsis etmek için sevkiyat planlayıcıyı kullanın.",
      "Dış ticaret belgeleri",
      "Taslak fatura önizlemesi",
      "Kabul edilen ticari bilgiler",
    ]) {
      await expect(page.getByText(text, { exact: true }), text).toBeVisible();
    }
    await expect(
      page.locator("main").getByText("Teyit edildi", { exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByText(approved.customerName).first()).toBeVisible();

    // Cancel: the reason is mandatory, in Turkish too.
    await page.getByRole("button", { name: "Siparişi iptal et" }).click();
    await page.getByRole("button", { name: "Onayla" }).click();
    await expect(
      page.getByText("İptal için en az 3 karakterlik bir gerekçe gerekir."),
    ).toBeVisible();
    await page.getByLabel("Gerekçe (zorunlu)").fill("Müşteri siparişten vazgeçti");
    await page.getByRole("button", { name: "Onayla" }).click();
    await expect(page.getByText("Sipariş artık: iptal edildi.")).toBeVisible();
    await expect(
      page.locator("main").getByText("İptal edildi", { exact: true }).first(),
    ).toBeVisible();

    await gotoReady(page, "/orders");
    await expect(page.getByRole("heading", { level: 1, name: "Satış siparişleri" })).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(approved.customerName) })).toContainText(
      "İptal edildi",
    );

    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByRole("heading", { level: 1, name: "Sales orders" })).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(approved.customerName) })).toContainText(
      "Cancelled",
    );
    await context.close();
  });

  test("a deal that is already won opens its order, and a viewer cannot change it", async ({
    browser,
    browserName,
  }) => {
    const approved = await prepareApprovedQuote(browser, browserName);
    const sales = await signedInContext(browser, "sales", browserName);
    const page = await sales.newPage();
    await gotoReady(page, `/deals/${approved.dealId}`);
    await page.getByLabel(/Accepted by/).fill("Dana Buyer");
    await page.getByLabel("Evidence reference").fill(`Signed quote ${approved.quoteNumber}`);
    await page.getByRole("button", { name: "Record acceptance and convert" }).click();
    await page.waitForURL(/\/orders\/[0-9a-f-]{36}$/);
    const orderUrl = page.url();

    await gotoReady(page, `/deals/${approved.dealId}`);
    await expect(page.getByText("This deal is won")).toBeVisible();
    await expect(page.getByRole("link", { name: "Open the order register" })).toBeVisible();

    const viewer = await signedInContext(browser, "viewer", browserName);
    const viewerPage = await viewer.newPage();
    await gotoReady(viewerPage, new URL(orderUrl).pathname);
    await expect(viewerPage.getByText("Changing an order requires trade.write.")).toBeVisible();
    await expect(viewerPage.getByRole("button", { name: "Cancel order" })).toHaveCount(0);
    await sales.close();
    await viewer.close();
  });
});
