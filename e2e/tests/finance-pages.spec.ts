import { expect, test, type BrowserContext } from "@playwright/test";

import { gotoReady, signedInContext, stack } from "./support";
import { prepareLogistics } from "./trade";

/**
 * The Finance screens that do not need a live Finance service: the connection state, the
 * reconciliation and discrepancy lists and the order finance view are all rendered from Commerce
 * data. The live-service specs (`finance-live.spec.ts`) stay opt-in.
 */

async function inTurkish(context: BrowserContext): Promise<void> {
  await context.addCookies([{ name: "touche_locale", value: "tr", url: stack().web }]);
}

test.describe("finance screens, in a real browser, in both languages", () => {
  test("the order finance view keeps estimated, committed and documented apart, in Turkish and English", async ({
    browser,
    browserName,
  }) => {
    const f = await prepareLogistics(browser, browserName);
    const context = await signedInContext(browser, "finance", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, `/finance/orders/${f.orderId}`);
    await expect(page.getByRole("heading", { level: 1, name: f.orderNumber })).toBeVisible();
    for (const text of [
      "Kabul edilen sipariş değeri",
      "Satın alma taahhütleri",
      "Tahmini toplam ithalat maliyeti",
      "Kaydedilen giderler",
      "Belge destekli marj",
      "Kabul edilen ticari sipariş",
      "Kaydedilen operasyonel giderler",
      "Eksik kanıt ve boşluklar",
      "Marj yorumu",
    ]) {
      await expect(page.getByText(text, { exact: true }).first(), text).toBeVisible();
    }
    // One purchase order is supplier-confirmed (a commitment), the other is still a draft: both are
    // listed with their own status. The recorded freight cost is shown as a cost, and the
    // document-supported margin stays unavailable (explicit, never zero).
    await expect(page.getByRole("row", { name: new RegExp(f.purchaseOrderNumber) })).toContainText(
      "Tedarikçi teyit etti",
    );
    await expect(
      page.getByRole("row", { name: new RegExp(f.draftPurchaseOrderNumber) }),
    ).toContainText("Taslak");
    await expect(page.getByRole("row", { name: new RegExp(f.shipmentNumber) })).toContainText(
      "Navlun",
    );
    await expect(page.getByText("Mevcut değil").first()).toBeVisible();
    await expect(page.getByText("MEVCUT DEĞİL").first()).toBeVisible();
    await expect(page.getByText("Mutabakat çalıştırması yok")).toBeVisible();

    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByText("Accepted order value").first()).toBeVisible();
    await expect(page.getByText("Margin interpretation")).toBeVisible();
    await expect(page.getByText("No reconciliation run")).toBeVisible();
    await expect(page.getByText("UNAVAILABLE").first()).toBeVisible();

    // The two-column grid of this page used to widen the whole page on a phone.
    await page.setViewportSize({ width: 375, height: 900 });
    await gotoReady(page, `/finance/orders/${f.orderId}`);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, "horizontal overflow on the order finance view at 375px").toBeLessThanOrEqual(
      1,
    );
    await context.close();
  });

  test("the ledger, reconciliation list and discrepancy queue explain their state in Turkish", async ({
    browser,
    browserName,
  }) => {
    const context = await signedInContext(browser, "finance", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, "/finance");
    await expect(page.getByRole("heading", { level: 1, name: "Finans" })).toBeVisible();
    await expect(page.getByText("Salt okunur", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Mutabakat", exact: true }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Uyuşmazlıklar" }).first()).toBeVisible();

    await gotoReady(page, "/finance/reconciliation");
    await expect(page.getByRole("heading", { level: 1, name: "Mutabakat" })).toBeVisible();

    await gotoReady(page, "/finance/discrepancies");
    await expect(page.getByRole("heading", { level: 1, name: "Uyuşmazlıklar" })).toBeVisible();
    await expect(page.getByLabel("Önem")).toBeVisible();
    await expect(page.getByRole("option", { name: "Tutar uyuşmazlığı" })).toHaveAttribute(
      "value",
      "AMOUNT_MISMATCH",
    );
    await context.close();
  });

  test("a reader without finance permissions gets an explanation, not an empty page", async ({
    browser,
    browserName,
  }) => {
    const viewer = await signedInContext(browser, "viewer", browserName);
    await inTurkish(viewer);
    const page = await viewer.newPage();
    await gotoReady(page, "/finance/discrepancies");
    await expect(page.getByRole("heading", { level: 1, name: "Uyuşmazlıklar" })).toBeVisible();
    await expect(
      page.getByText("Salt okunur: çözmek için finance.reconcile gerekir."),
    ).toBeVisible();
    await viewer.close();
  });
});
