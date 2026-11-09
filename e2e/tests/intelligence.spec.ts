import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { gotoReady, signedInContext, stack } from "./support";
import { prepareLogistics } from "./trade";

/** Financial intelligence is computed from Commerce data, so it needs no live Finance service. */

async function inTurkish(context: BrowserContext): Promise<void> {
  await context.addCookies([{ name: "touche_locale", value: "tr", url: stack().web }]);
}

/** The digits of every figure in one metric card: separators differ by language, digits must not. */
async function metricDigits(page: Page, key: string): Promise<string> {
  const figures = await page.locator(`[data-metric="${key}"] .data-value`).allInnerTexts();
  return figures.map((text) => text.replace(/\D/g, "")).join("|");
}

test.describe("financial intelligence, in a real browser, in both languages", () => {
  test("the dashboard reads in Turkish and keeps every figure when the language changes", async ({
    browser,
    browserName,
  }) => {
    await prepareLogistics(browser, browserName);
    const context = await signedInContext(browser, "finance", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, "/finance/intelligence");
    await expect(page.getByRole("heading", { level: 1, name: "Finansal analiz" })).toBeVisible();
    for (const text of [
      "Bu ekran ne, ne değil",
      "Kabul edilen satış siparişi değeri",
      "Satın alma taahhütleri",
      "Tahmini brüt kâr",
      "Taahhüt bazlı brüt kâr",
      "İnceleme bekleyen siparişler",
    ]) {
      await expect(page.getByText(text, { exact: true }).first(), text).toBeVisible();
    }
    await expect(page.getByRole("button", { name: /CSV olarak dışa aktar/ })).toBeVisible();
    await expect(page.getByText("Aylık taahhütler", { exact: true })).toBeVisible();
    await expect(page.getByText("Tablo görünümü").first()).toBeVisible();

    const accepted = await metricDigits(page, "accepted_sales_order_value");
    const commitments = await metricDigits(page, "purchase_commitments");
    expect(accepted).not.toBe("");

    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(
      page.getByRole("heading", { level: 1, name: "Financial intelligence" }),
    ).toBeVisible();
    await expect(page.getByText("What this is — and is not")).toBeVisible();
    expect(await metricDigits(page, "accepted_sales_order_value")).toBe(accepted);
    expect(await metricDigits(page, "purchase_commitments")).toBe(commitments);
    await context.close();
  });

  test("order profitability and the order analysis keep estimated, committed and documented apart", async ({
    browser,
    browserName,
  }) => {
    const f = await prepareLogistics(browser, browserName);
    const context = await signedInContext(browser, "finance", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, "/finance/intelligence/orders");
    await expect(page.getByRole("heading", { level: 1, name: "Sipariş kârlılığı" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Tüm siparişler" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Tahmini marj" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Belgelenen maliyet" })).toBeVisible();
    await expect(page.getByLabel("Sipariş durumu")).toBeVisible();

    await page.getByRole("link", { name: "Maliyet farkı" }).click();
    await expect(page).toHaveURL(/view=variance/);
    await expect(page.getByRole("link", { name: "Maliyet farkı" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    await gotoReady(page, `/finance/intelligence/orders/${f.orderId}`);
    await expect(page.getByRole("heading", { level: 1, name: f.orderNumber })).toBeVisible();
    for (const text of [
      "Tamamlanma kontrolleri",
      "Sınırlar",
      "Tahmini gider kalemleri",
      "Satın alma siparişleri",
      "Sevkiyatlar ve kaydedilen giderler",
      "Mutabakat geçmişi",
      "Finans kanıtı",
      "Bu siparişin istisnaları",
      "Bu sayfa nasıl okunur",
    ]) {
      await expect(page.getByText(text, { exact: true }).first(), text).toBeVisible();
    }
    // The supplier-confirmed purchase order is a commitment (160 = 100 kg x 1.60); the incurred
    // freight is a documented cost. Neither is merged into the other.
    await expect(page.getByRole("row", { name: new RegExp(f.purchaseOrderNumber) })).toContainText(
      "160,00",
    );
    await expect(page.getByText("Gerçek kâr").first()).toBeVisible();
    await expect(page.getByText("MEVCUT DEĞİL").first()).toBeVisible();

    // A wide, multi-table page must not widen the whole page on a phone.
    await page.setViewportSize({ width: 375, height: 900 });
    await gotoReady(page, `/finance/intelligence/orders/${f.orderId}`);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, "horizontal overflow on the order analysis at 375px").toBeLessThanOrEqual(1);
    await context.close();
  });

  test("the exception queue translates its filters and explains who may resolve", async ({
    browser,
    browserName,
  }) => {
    const viewer = await signedInContext(browser, "viewer", browserName);
    await inTurkish(viewer);
    const page = await viewer.newPage();
    await gotoReady(page, "/finance/intelligence/exceptions");
    await expect(page.getByRole("heading", { level: 1, name: "Mali istisnalar" })).toBeVisible();
    await expect(page.getByLabel("Önem")).toBeVisible();
    await expect(page.getByRole("option", { name: "Tutar uyuşmazlığı" })).toHaveAttribute(
      "value",
      "AMOUNT_MISMATCH",
    );
    await expect(
      page.getByText("Salt okunur: çözmek için finance.reconcile gerekir."),
    ).toBeVisible();
    await viewer.close();
  });
});
