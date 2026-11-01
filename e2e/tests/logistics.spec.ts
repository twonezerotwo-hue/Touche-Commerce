import { expect, test, type BrowserContext } from "@playwright/test";

import { gotoReady, runId, signedInContext, stack } from "./support";
import { prepareFulfilment } from "./trade";

async function inTurkish(context: BrowserContext): Promise<void> {
  await context.addCookies([{ name: "touche_locale", value: "tr", url: stack().web }]);
}

test.describe("procurement and logistics, in a real browser, in both languages", () => {
  test("a purchase order is read in Turkish and approved by a second person", async ({
    browser,
    browserName,
  }) => {
    const f = await prepareFulfilment(browser, browserName);
    const sales = await signedInContext(browser, "sales", browserName);
    await inTurkish(sales);
    const page = await sales.newPage();

    await gotoReady(page, "/purchase-orders");
    await expect(
      page.getByRole("heading", { level: 1, name: "Tedarikçi satın alma siparişleri" }),
    ).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Satın alma no" })).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(f.purchaseOrderNumber) })).toContainText(
      "Taslak",
    );

    await gotoReady(page, `/purchase-orders/${f.purchaseOrderId}`);
    for (const text of [
      "Tedarikçiden sipariş edilenler",
      "Geçmiş ve kanıtlar",
      "Satın alma iş akışı",
      "Bilgiler",
    ]) {
      await expect(page.getByText(text, { exact: true }), text).toBeVisible();
    }
    // The creator cannot approve their own order, and the screen does not even offer it.
    await expect(page.getByRole("button", { name: "Satın alma siparişini onayla" })).toHaveCount(0);

    const finance = await signedInContext(browser, "finance", browserName);
    await inTurkish(finance);
    const approver = await finance.newPage();
    await gotoReady(approver, `/purchase-orders/${f.purchaseOrderId}`);
    await approver.getByRole("button", { name: "Satın alma siparişini onayla" }).click();
    await approver.getByRole("button", { name: "Onayla", exact: true }).click();
    await expect(
      approver.getByText("Satın alma siparişinin yeni durumu: onaylandı."),
    ).toBeVisible();
    await expect(
      approver.locator("main").getByText("Onaylandı", { exact: true }).first(),
    ).toBeVisible();

    await finance.close();
    await sales.close();
  });

  test("a shipment moves through booking and dispatch with its evidence rules intact", async ({
    browser,
    browserName,
  }) => {
    const f = await prepareFulfilment(browser, browserName);
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, "/shipments");
    await expect(page.getByRole("heading", { level: 1, name: "Sevkiyatlar" })).toBeVisible();
    const row = page.getByRole("row", { name: new RegExp(f.shipmentNumber) });
    await expect(row).toContainText("Planlandı");
    await expect(row).toContainText("Deniz");
    await expect(row).toContainText("Mersin, TR → Rotterdam, NL");

    await gotoReady(page, `/shipments/${f.shipmentId}`);
    for (const text of [
      "Tahsis edilen miktarlar",
      "Zaman çizelgesi",
      "Lojistik giderleri",
      "Referanslar",
      "Aşamalar",
      "Sevkiyat belgeleri",
    ]) {
      await expect(page.getByText(text, { exact: true }), text).toBeVisible();
    }

    await page.getByRole("button", { name: "Şu olarak işaretle: rezerve edildi" }).click();
    await page.getByRole("button", { name: "Onayla", exact: true }).click();
    await expect(page.getByText("Sevkiyatın yeni durumu: rezerve edildi.")).toBeVisible();

    // Dispatch needs a booking reference; the rule holds in Turkish too.
    await page.getByRole("button", { name: "Şu olarak işaretle: sevk edildi" }).click();
    await page.getByRole("button", { name: "Onayla", exact: true }).click();
    await expect(
      page.getByText("Sevk etmeden önce taşıyıcı veya rezervasyon referansını kaydedin."),
    ).toBeVisible();
    await page.getByLabel("Taşıyıcı / rezervasyon referansı").fill("BKG-TR-0001");
    await page.getByRole("button", { name: "Onayla", exact: true }).click();
    await expect(page.getByText("Sevkiyatın yeni durumu: sevk edildi.")).toBeVisible();
    await expect(page.getByText("Sevk edildi", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/Elle giriş/).first()).toBeVisible();

    // A logistics cost keeps its own stage and is formatted in the reader's language.
    await page.getByRole("button", { name: "Gider kaydet" }).click();
    await page.getByLabel("Tutar").fill("12.50");
    await page.getByLabel("Referans (teklif veya fatura numarası)").fill(`FTR-${runId()}`);
    await page.getByRole("button", { name: "Kaydet", exact: true }).click();
    await expect(page.getByText("Navlun · Tahmini")).toBeVisible();
    await expect(page.getByText(/12,50/).first()).toBeVisible();

    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByText("Freight · Estimated")).toBeVisible();
    await expect(page.getByText(/12\.50/).first()).toBeVisible();
    await expect(page.getByText("Timeline", { exact: true })).toBeVisible();
    await context.close();
  });

  test("the document register stores, lists and verifies an uploaded file in Turkish", async ({
    browser,
    browserName,
  }) => {
    await prepareFulfilment(browser, browserName); // an order and a shipment to attach to
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();
    await gotoReady(page, "/documents");
    await expect(
      page.getByRole("heading", { level: 1, name: "Dış ticaret belge kaydı" }),
    ).toBeVisible();

    const title = `İmzalı teslim belgesi ${runId()}`;
    await page.getByLabel("Başlık (isteğe bağlı)").fill(title);
    await page.getByLabel("Dosya", { exact: true }).setInputFiles({
      name: "pod.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(`Signed proof of delivery ${title}\n`),
    });
    await page.getByRole("button", { name: "Belgeyi yükle" }).click();
    await expect(page.getByText(/sürüm olarak saklandı/)).toBeVisible();

    const row = page.getByRole("row", { name: new RegExp(title) });
    await expect(row).toContainText("Teslimat onayı");
    await expect(row).toContainText("Aktif");
    await expect(row).toContainText("Doğrulanmadı");
    await expect(row.getByRole("link", { name: "İndir" })).toBeVisible();
    await row.getByRole("button", { name: "Doğrula" }).click();
    await expect(row).toContainText("Doğrulandı");
    await context.close();
  });

  test("a read-only role gets Turkish explanations instead of working controls", async ({
    browser,
    browserName,
  }) => {
    const f = await prepareFulfilment(browser, browserName);
    const viewer = await signedInContext(browser, "viewer", browserName);
    await inTurkish(viewer);
    const page = await viewer.newPage();

    await gotoReady(page, "/shipments/new");
    await expect(page.getByText("Sevkiyat planlamak için trade.write gerekir.")).toBeVisible();

    await gotoReady(page, `/shipments/${f.shipmentId}`);
    await expect(
      page.getByText("Sevkiyat aşamalarını kaydetmek için trade.write gerekir."),
    ).toBeVisible();
    await expect(page.getByText("Belge yüklemek için trade.write gerekir.")).toBeVisible();
    await viewer.close();
  });
});
