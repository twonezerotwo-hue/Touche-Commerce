import { expect, test, type BrowserContext } from "@playwright/test";

import { gotoReady, runId, signedInContext, stack } from "./support";
import { PDF, prepareLogistics } from "./trade";

async function inTurkish(context: BrowserContext): Promise<void> {
  await context.addCookies([{ name: "touche_locale", value: "tr", url: stack().web }]);
}

test.describe("purchase orders, shipments and the document register, in both languages", () => {
  test("every logistics screen reads in Turkish and shows the same figures in English", async ({
    browser,
    browserName,
  }) => {
    const fixture = await prepareLogistics(browser, browserName);
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    // Purchase-order list and detail
    await gotoReady(page, "/purchase-orders");
    await expect(
      page.getByRole("heading", { level: 1, name: "Tedarikçi satın alma siparişleri" }),
    ).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Tedarikçi", exact: true })).toBeVisible();
    const poRow = page.getByRole("row", { name: new RegExp(fixture.purchaseOrderNumber) });
    await expect(poRow).toContainText("Tedarikçi teyit etti");
    await expect(poRow).toContainText(/160,00/);
    await expect(
      page.getByRole("row", { name: new RegExp(fixture.draftPurchaseOrderNumber) }),
    ).toContainText("Taslak");

    await gotoReady(page, `/purchase-orders/${fixture.purchaseOrderId}`);
    for (const text of [
      "Tedarikçiden sipariş edilenler",
      "Geçmiş ve kanıtlar",
      "Tedarik iş akışı",
      "Bilgiler",
    ]) {
      await expect(page.getByText(text, { exact: true }), text).toBeVisible();
    }
    await expect(page.getByText("Onaylandı → Gönderildi (kayıtlı)")).toBeVisible();
    await expect(page.getByText(/100 kg/)).toBeVisible();

    // Shipment list and detail
    await gotoReady(page, "/shipments");
    await expect(page.getByRole("heading", { level: 1, name: "Sevkiyatlar" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Güzergâh" })).toBeVisible();
    const shipmentRow = page.getByRole("row", { name: new RegExp(fixture.shipmentNumber) });
    await expect(shipmentRow).toContainText("Yolda");
    await expect(shipmentRow).toContainText("Deniz");
    await expect(shipmentRow).toContainText("Belgelenen tahmini varış içinde");

    await gotoReady(page, `/shipments/${fixture.shipmentId}`);
    for (const text of [
      "Tahsis edilen miktarlar",
      "Zaman çizelgesi",
      "Lojistik maliyetleri",
      "Referanslar",
      "Aşamalar",
      "Sevkiyat belgeleri",
    ]) {
      await expect(page.getByText(text, { exact: true }), text).toBeVisible();
    }
    await expect(page.getByText("Navlun · Gerçekleşen")).toBeVisible();
    await expect(page.getByText(/512,50/)).toBeVisible();
    await expect(page.getByText("Konteyner", { exact: true })).toBeVisible();
    await expect(page.getByText("Belge kanıtı", { exact: true })).toBeVisible();
    await expect(page.getByText(/Teslimat onayı · \d/)).toBeVisible();

    // Document register
    await gotoReady(page, "/documents");
    await expect(
      page.getByRole("heading", { level: 1, name: "Dış ticaret belge kaydı" }),
    ).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Eklendiği kayıt" })).toBeVisible();
    const documentRow = page.getByRole("row", { name: new RegExp(fixture.documentTitle) });
    await expect(documentRow).toContainText("Teslimat onayı");
    await expect(documentRow).toContainText("sevkiyat");
    await expect(documentRow).toContainText("Doğrulanmadı");
    await expect(documentRow).toContainText("Aktif");

    // Switching to English keeps the page and the figures.
    await gotoReady(page, `/shipments/${fixture.shipmentId}`);
    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByText("Allocated quantities", { exact: true })).toBeVisible();
    await expect(page.getByText("Freight · Incurred")).toBeVisible();
    await expect(page.getByText(/512\.50/)).toBeVisible();

    await gotoReady(page, "/documents");
    await expect(
      page.getByRole("heading", { level: 1, name: "Trade document register" }),
    ).toBeVisible();
    await expect(page.getByRole("row", { name: new RegExp(fixture.documentTitle) })).toContainText(
      "Delivery confirmation",
    );
    await context.close();
  });

  test("a trader plans a shipment, records a cost, uploads and verifies a document in Turkish", async ({
    browser,
    browserName,
  }) => {
    const fixture = await prepareLogistics(browser, browserName);
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    // The planner offers the 60 kg that the first shipment left unallocated.
    await gotoReady(page, "/shipments/new");
    await expect(page.getByRole("heading", { level: 1, name: "Sevkiyat planla" })).toBeVisible();
    await page
      .getByLabel("Satış siparişi", { exact: true })
      .selectOption({ label: `${fixture.orderNumber} · ${fixture.customerName}` });
    await expect(page.getByText("Kalan 60 kg")).toBeVisible();
    await page.getByRole("button", { name: "Sevkiyat planla" }).click();
    await expect(page.getByText("Hem çıkış hem varış yerini kaydedin.")).toBeVisible();

    await page.getByLabel("Taşıma modu").selectOption("ROAD");
    await page.getByLabel("Çıkış yeri").fill("İzmir, TR");
    await page.getByLabel("Varış yeri").fill("Sofia, BG");
    await page.getByRole("button", { name: "Sevkiyat planla" }).click();
    await page.waitForURL(/\/shipments\/[0-9a-f-]{36}$/);
    await expect(page.getByText("Planlandı", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: /Karayolu/ })).toBeVisible();

    // A cost keeps its own stage and is shown as words.
    await page.getByRole("button", { name: "Maliyet kaydet" }).click();
    await page.getByLabel("Maliyet türü").selectOption("INSURANCE");
    await page.getByLabel("Tutar").fill("12.50");
    await page.getByLabel("Referans (teklif veya fatura no)").fill("Sigorta teklifi");
    await page.getByRole("button", { name: "Kaydet", exact: true }).click();
    await expect(page.getByText("Sigorta · Tahmini")).toBeVisible();
    await expect(page.getByText(/12,50/)).toBeVisible();

    // A milestone, with its Turkish confirmation.
    await page.getByRole("button", { name: "İşaretle: rezerve edildi" }).click();
    await page.getByRole("button", { name: "Onayla", exact: true }).click();
    await expect(page.getByText("Sevkiyat artık: rezerve edildi.")).toBeVisible();

    // Upload a document, see it stored, then verify it.
    const title = `Konşimento ${runId()}`;
    await page.getByLabel("Belge türü").selectOption("BILL_OF_LADING");
    await page.getByLabel("Başlık (isteğe bağlı)").fill(title);
    await page
      .getByLabel("Dosya")
      .setInputFiles({ name: "bl.pdf", mimeType: "application/pdf", buffer: PDF });
    await page.getByRole("button", { name: "Belgeyi yükle", exact: true }).click();
    await expect(page.getByText(/1\. sürüm olarak saklandı/)).toBeVisible();
    await expect(page.getByText(`${title} v1`)).toBeVisible();
    await page.getByRole("button", { name: "Doğrula", exact: true }).click();
    await gotoReady(page, "/documents");
    await expect(page.getByRole("row", { name: new RegExp(title) })).toContainText("Doğrulandı");
    await context.close();
  });

  test("a draft purchase order is cancelled with a reason in Turkish, and only an approver may approve it", async ({
    browser,
    browserName,
  }) => {
    const fixture = await prepareLogistics(browser, browserName);
    const url = `/purchase-orders/${fixture.draftPurchaseOrderId}`;

    const trader = await signedInContext(browser, "sales", browserName);
    await inTurkish(trader);
    const page = await trader.newPage();
    await gotoReady(page, url);
    await expect(page.getByRole("button", { name: "Satın alma siparişini onayla" })).toHaveCount(0);
    await page.getByRole("button", { name: "İşaretle: iptal edildi" }).click();
    await page.getByRole("button", { name: "Onayla", exact: true }).click();
    await expect(
      page.getByText("İptal için en az 3 karakterlik bir gerekçe gerekir."),
    ).toBeVisible();
    await page.getByLabel("Gerekçe (zorunlu)").fill("Müşteri siparişi küçülttü");
    await page.getByRole("button", { name: "Onayla", exact: true }).click();
    await expect(page.getByText("Satın alma siparişi artık: iptal edildi.")).toBeVisible();
    await expect(page.getByText("Başka geçiş yok")).toBeVisible();
    await trader.close();

    // Another draft, seen by finance: the approval action is offered there.
    const second = await prepareLogistics(browser, browserName);
    const finance = await signedInContext(browser, "finance", browserName);
    await inTurkish(finance);
    const financePage = await finance.newPage();
    await gotoReady(financePage, `/purchase-orders/${second.draftPurchaseOrderId}`);
    await expect(
      financePage.getByRole("button", { name: "Satın alma siparişini onayla" }),
    ).toBeVisible();
    await finance.close();
  });

  test("a read-only role sees logistics screens but not their action panels", async ({
    browser,
    browserName,
  }) => {
    const fixture = await prepareLogistics(browser, browserName);
    const viewer = await signedInContext(browser, "viewer", browserName);
    await inTurkish(viewer);
    const page = await viewer.newPage();

    await gotoReady(page, `/shipments/${fixture.shipmentId}`);
    await expect(
      page.getByText("Sevkiyat aşamalarını kaydetmek için trade.write gerekir."),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Maliyet kaydet" })).toHaveCount(0);

    await gotoReady(page, "/shipments/new");
    await expect(page.getByText("Sevkiyat planlamak için trade.write gerekir.")).toBeVisible();

    await gotoReady(page, "/documents");
    await expect(page.getByText("Yüklemek için trade.write gerekir.").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Belgeyi yükle", exact: true })).toHaveCount(0);
    await viewer.close();
  });
});
