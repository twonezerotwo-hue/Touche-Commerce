import { expect, test, type BrowserContext } from "@playwright/test";

import { gotoReady, signedInContext, stack } from "./support";
import { prepareLogistics } from "./trade";

/**
 * The AI Office and Communications, in a real browser, in both languages. The acceptance stack
 * runs the offline mock provider, so a question is answered from the seeded records without any
 * network call, and nothing here can send a message.
 */

async function inTurkish(context: BrowserContext): Promise<void> {
  await context.addCookies([{ name: "touche_locale", value: "tr", url: stack().web }]);
}

test.describe("AI Office and communications, in a real browser, in both languages", () => {
  test("the AI Office reads in Turkish, answers a question and keeps it when the language changes", async ({
    browser,
    browserName,
  }) => {
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, "/ai");
    await expect(
      page.getByRole("heading", { level: 1, name: "Yapay Zekâ Ticaret Direktörü" }),
    ).toBeVisible();
    await expect(page.getByText("Salt okunur", { exact: true })).toBeVisible();
    await expect(page.getByText("İnsan onayı", { exact: true })).toBeVisible();
    await expect(page.getByRole("tab", { name: /^Önerilen işlemler/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Etkinlik" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Araçlar" })).toBeVisible();
    await expect(
      page.getByText("Hiçbir şey gönderemez, imzalayamaz", { exact: false }),
    ).toBeVisible();

    await page.getByRole("tab", { name: "Araçlar" }).click();
    await expect(page.getByText("Salt okunur araçlar")).toBeVisible();
    await expect(page.getByText("Hiçbir zaman kullanılamaz")).toBeVisible();

    await page.getByLabel("Ticaret Direktörüne sorun").fill("Sipariş ve sevkiyat durumunu özetle");
    await page.getByRole("button", { name: "Gönder" }).click();
    const answer = page.getByRole("article", { name: "Ticaret Direktörü yanıtı" });
    await expect(answer).toBeVisible({ timeout: 30_000 });
    await expect(answer.getByText("Kayıtlarınızla karşılaştırıldı")).toBeVisible();

    await page.getByRole("tab", { name: "Etkinlik" }).click();
    await expect(page.getByText("Tamamlandı").first()).toBeVisible();

    // The language changes in place: the answer stays, only the words around it change.
    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByRole("heading", { level: 1, name: "AI Trade Director" })).toBeVisible();
    await expect(page.getByRole("article", { name: "Trade Director answer" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Activity" })).toBeVisible();
    await expect(page.getByLabel("Ask the Trade Director")).toBeVisible();
    await context.close();
  });

  test("a drafted message waits for a person, is approved without being sent, and shows up in communications", async ({
    browser,
    browserName,
  }) => {
    // The assistant only drafts from records that exist, so give it an order and a shipment first.
    await prepareLogistics(browser, browserName);
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, "/ai");
    await page
      .getByLabel("Ticaret Direktörüne sorun")
      .fill("Tedarikçiye bir takip e-postası taslağı hazırla");
    await page.getByRole("button", { name: "Gönder" }).click();
    await expect(page.getByRole("article", { name: "Ticaret Direktörü yanıtı" })).toBeVisible({
      timeout: 30_000,
    });

    await page.getByRole("tab", { name: /^Önerilen işlemler/ }).click();
    await expect(page.getByText("Bir kişiyi bekliyor").first()).toBeVisible();
    await expect(page.getByText("Önizleme — gönderilmedi").first()).toBeVisible();

    const approve = page.getByRole("button", { name: "Metni onayla" }).first();
    await expect(approve).toBeVisible();
    const review = page.getByLabel("Bu metindeki doğrulanmamış rakamları inceledim.").first();
    if (await review.isVisible()) await review.check();
    await approve.click();
    await expect(page.getByText(/Bir kişi tarafından onaylandı/).first()).toBeVisible();

    await gotoReady(page, "/communications");
    await expect(page.getByRole("heading", { level: 1, name: "İletişim" })).toBeVisible();
    await expect(page.getByText("Yalnızca taslak · Hiçbir ileti gönderilmedi")).toBeVisible();
    await expect(page.getByText("Bağlı değil").first()).toBeVisible();
    await expect(page.getByText("Hazırlanan yazışmalar")).toBeVisible();
    await expect(page.getByText("İncelendi · Gönderilmedi").first()).toBeVisible();
    await expect(page.getByText("Hiçbir zaman iletilmez").first()).toBeVisible();

    // The readiness check explains what blocks sending, in Turkish, and sends nothing.
    await page.getByRole("button", { name: "Hazırlığı kontrol et (gönderim yok)" }).first().click();
    await page.getByLabel("Alıcı (saklanmaz)").first().fill("buyer@example.com");
    await page.getByRole("button", { name: "Engelleri kontrol et" }).first().click();
    await expect(page.getByText("Gönderim engellendi").first()).toBeVisible();

    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByRole("heading", { level: 1, name: "Communications" })).toBeVisible();
    await expect(page.getByText("Draft-only · No messages sent")).toBeVisible();

    // With a conversation, a decided proposal and a prepared draft on screen, a phone still fits.
    await page.getByLabel("Interface language").selectOption("tr");
    await page.setViewportSize({ width: 375, height: 812 });
    for (const route of ["/ai", "/communications"]) {
      await gotoReady(page, route);
      await expect(page.locator("main")).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal overflow on ${route} at 375px`).toBeLessThanOrEqual(1);
    }
    await context.close();
  });

  test("only an administrator sees the do-not-contact ledger, and recording a block stays deliberate", async ({
    browser,
    browserName,
  }) => {
    const owner = await signedInContext(browser, "owner", browserName);
    await inTurkish(owner);
    const ownerPage = await owner.newPage();
    await gotoReady(ownerPage, "/communications");
    await expect(ownerPage.getByText("Rahatsız etme listesi")).toBeVisible();
    const record = ownerPage.getByRole("button", { name: "Kalıcı engellemeyi kaydet" });
    await expect(record).toBeDisabled();
    await owner.close();

    const viewer = await signedInContext(browser, "viewer", browserName);
    await inTurkish(viewer);
    const viewerPage = await viewer.newPage();
    await gotoReady(viewerPage, "/communications");
    await expect(viewerPage.getByRole("heading", { level: 1, name: "İletişim" })).toBeVisible();
    await expect(viewerPage.getByText("Rahatsız etme listesi")).toHaveCount(0);
    await viewer.close();
  });

  test("a viewer reads the AI Office in Turkish and cannot decide a proposal", async ({
    browser,
    browserName,
  }) => {
    const context = await signedInContext(browser, "viewer", browserName);
    await inTurkish(context);
    const page = await context.newPage();
    await gotoReady(page, "/ai");
    await expect(
      page.getByRole("heading", { level: 1, name: "Yapay Zekâ Ticaret Direktörü" }),
    ).toBeVisible();
    await page.getByRole("tab", { name: /^Önerilen işlemler/ }).click();
    await expect(page.getByRole("button", { name: "Metni onayla" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Reddet" })).toHaveCount(0);
    await context.close();
  });
});
