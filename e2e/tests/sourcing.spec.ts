import { expect, test, type BrowserContext } from "@playwright/test";

import { gotoReady, runId, signedInContext, stack } from "./support";
import { prepareApprovedQuote } from "./trade";

async function inTurkish(context: BrowserContext): Promise<void> {
  await context.addCookies([{ name: "touche_locale", value: "tr", url: stack().web }]);
}

test.describe("sourcing and pricing, in a real browser, in both languages", () => {
  test("RFQ, supplier quote, landed cost and sales quote read in Turkish, with identical figures in English", async ({
    browser,
    browserName,
  }) => {
    const approved = await prepareApprovedQuote(browser, browserName);
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    // RFQ list and detail
    await gotoReady(page, "/rfq");
    await expect(page.getByRole("heading", { level: 1, name: "Tedarikçi talepleri" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Tedarikçi" })).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(approved.rfqReference) })).toContainText(
      "Yanıtlandı",
    );
    await gotoReady(page, `/rfq/${approved.rfqId}`);
    for (const text of [
      "İstenen kalemler",
      "Alınan teklifler",
      "Yaşam döngüsü",
      "Hazırlanan revizyonlar",
      "Gönderim kanıtı",
    ]) {
      await expect(page.getByText(text, { exact: true }), text).toBeVisible();
    }
    await expect(page.getByRole("link", { name: "revizyon 1" })).toBeVisible();

    // Supplier quote list and detail
    await gotoReady(page, "/quotes");
    await expect(
      page.getByRole("heading", { level: 1, name: "Tedarikçi teklifleri" }),
    ).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(approved.rfqReference) })).toContainText(
      "Alındı",
    );
    await gotoReady(page, `/quotes/${approved.supplierQuoteId}`);
    for (const text of ["Tekliflenen kalemler", "Bu teklifi fiyatlandır", "Kaynak bilgisi"]) {
      await expect(page.getByText(text, { exact: true }), text).toBeVisible();
    }

    // Pricing: the landed cost is 160 + 40 = 200 and the 20 % margin makes the sale 250.
    await gotoReady(page, "/pricing");
    await expect(
      page.getByRole("heading", { level: 1, name: "Toplam ithalat maliyeti senaryoları" }),
    ).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(approved.rfqReference) })).toContainText(
      "Girdiler doğrulandı",
    );
    await gotoReady(page, `/pricing/${approved.scenarioId}`);
    for (const text of ["Fiyatlanan kalemler", "Maliyet bileşenleri", "Bütünlük"]) {
      await expect(page.getByText(text, { exact: true }), text).toBeVisible();
    }
    await expect(page.getByRole("cell", { name: "Navlun" })).toBeVisible();
    await expect(page.getByText("Doğrulandı", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/250,00/).first()).toBeVisible();
    await expect(page.getByText(/200,00/).first()).toBeVisible();

    // Sales quote list and detail
    await gotoReady(page, "/sales-quotes");
    await expect(page.getByRole("heading", { level: 1, name: "Müşteri teklifleri" })).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(approved.quoteNumber) })).toContainText(
      "Onaylandı",
    );
    await gotoReady(page, `/sales-quotes/${approved.salesQuoteId}`);
    for (const text of ["Onay geçmişi", "İş akışı", "Revizyon kayıtları"]) {
      await expect(page.getByText(text, { exact: true }), text).toBeVisible();
    }

    // Switching back to English keeps the page, the session and the figures.
    const url = page.url();
    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByText("Approval trail", { exact: true })).toBeVisible();
    expect(page.url()).toBe(url);
    await expect(page.getByLabel("Interface language")).toHaveValue("en");

    await gotoReady(page, `/pricing/${approved.scenarioId}`);
    await expect(page.getByText("Priced lines", { exact: true })).toBeVisible();
    await expect(page.getByText(/250\.00/).first()).toBeVisible();
    await expect(page.getByText(/200\.00/).first()).toBeVisible();
    await context.close();
  });

  test("a read-only role sees sourcing screens but not their action panels", async ({
    browser,
    browserName,
  }) => {
    const approved = await prepareApprovedQuote(browser, browserName);
    const viewer = await signedInContext(browser, "viewer", browserName);
    await inTurkish(viewer);
    const page = await viewer.newPage();

    await gotoReady(page, "/rfq/new");
    await expect(page.getByText("Salt okunur erişim").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "RFQ oluştur" })).toHaveCount(0);

    await gotoReady(page, `/rfq/${approved.rfqId}`);
    await expect(page.getByText("Bir RFQ'yu değiştirmek için trade.write gerekir.")).toBeVisible();

    await gotoReady(page, `/sales-quotes/${approved.salesQuoteId}`);
    await expect(
      page.getByText("İş akışı için trade.write, onay için finance.approve gerekir."),
    ).toBeVisible();
    await viewer.close();
  });

  test("a trader's half-filled RFQ form survives a language switch and validates in Turkish", async ({
    browser,
    browserName,
  }) => {
    await prepareApprovedQuote(browser, browserName); // makes sure a deal and a supplier exist
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();
    await gotoReady(page, "/rfq/new");
    await expect(
      page.getByRole("heading", { level: 1, name: "Tedarikçilerden teklif iste" }),
    ).toBeVisible();

    await page.getByLabel("Teslim yeri").fill("Mersin, TR");
    await page.getByRole("button", { name: "RFQ oluştur" }).click();
    await expect(page.getByText("En az bir tedarikçi seçin.")).toBeVisible();

    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByLabel("Delivery location")).toHaveValue("Mersin, TR");
    await expect(page.getByRole("heading", { level: 1, name: "Request supplier quotes" })).toBeVisible();
    await context.close();
  });

  test("a trader records an FX snapshot in Turkish", async ({ browser, browserName }) => {
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();
    await gotoReady(page, "/fx-rates");
    await expect(page.getByRole("heading", { level: 1, name: "Döviz kuru kayıtları" })).toBeVisible();

    // The pair and the day are unique per company, so each run uses its own day and rate.
    const daysBack = 1 + (Date.now() % 4000);
    const day = new Date(Date.now() - daysBack * 86_400_000).toISOString().slice(0, 10);
    const source = `TCMB ${runId()}`;
    await page.getByLabel("Baz").fill("EUR");
    await page.getByLabel("Karşıt").fill("USD");
    await page.getByLabel("Kur", { exact: true }).fill("1.0875");
    await page.getByLabel("Geçerlilik").fill(day);
    await page.getByLabel("Kaynak", { exact: true }).fill(source);
    await page.getByRole("button", { name: "Kuru kaydet" }).click();
    await expect(page.getByText("Kur kaydedildi.")).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(source) })).toContainText("EUR/USD");
    await context.close();
  });
});
