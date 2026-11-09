import { expect, test, type BrowserContext } from "@playwright/test";

import { credentials, gotoReady, signedInContext, stack } from "./support";
import { prepareLogistics } from "./trade";

/**
 * The account page, the public status page, tab titles, a missing page and the dates of real
 * records, in a real browser, in both languages.
 */

async function inTurkish(context: BrowserContext): Promise<void> {
  await context.addCookies([{ name: "touche_locale", value: "tr", url: stack().web }]);
}

/** "09 Kas 2026" / "09 Nov 2026": the day, the short month and the year as the app formats them. */
function todayAs(tag: "tr-TR" | "en-GB", minutesAgo = 0): string {
  return new Intl.DateTimeFormat(tag, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.now() - minutesAgo * 60_000));
}

test.describe("account, status, titles and dates, in a real browser, in both languages", () => {
  test("the account page reads in Turkish, and changing the language keeps the session and the company", async ({
    browser,
    browserName,
  }) => {
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, "/account");
    await expect(page).toHaveTitle(/Hesap/);
    await expect(page.getByRole("heading", { level: 1, name: "Profil ve erişim" })).toBeVisible();
    for (const text of [
      "Oturum açık",
      "Oturum açan profil",
      "Şirket erişimi",
      "Oturum politikası",
      "Etkin şirketteki rol",
      "Bu üyeliğin verdiği yetkiler",
      "Hareketsizlik süresi",
      "Tarayıcı değil, API uygular",
    ]) {
      await expect(page.getByText(text, { exact: true }).first(), text).toBeVisible();
    }
    await expect(page.getByText("Ticaret yetkilisi").first()).toBeVisible();
    await expect(page.getByText("Geçerli", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Çıkış yap" })).toBeVisible();
    // The shell around the page: navigation name, breadcrumb and footer.
    await expect(page.getByRole("navigation", { name: "Ana menü" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Gezinti yolu" })).toBeVisible();
    await expect(page.getByText(/Dış ticaret yönetim platformu/)).toBeVisible();
    await expect(page.getByText(/Aşama 6 · Yapay Zekâ Ticaret Direktörü/)).toBeVisible();
    // The stored permission identifiers are not translated.
    await expect(page.getByText("trade.write", { exact: true })).toBeVisible();

    const company = credentials().sales.company;
    const header = page.locator("header");
    // The company pill in the top bar (not the breadcrumb, which also truncates).
    const companyPill = header.locator('span[class*="max-w-[220px]"] > span.truncate');
    const companyName = (await companyPill.innerText()).trim();
    expect(companyName, `a company name in the top bar for company ${company}`).not.toBe("");
    const permissionsBefore = await page.locator("li code, li .font-mono").allInnerTexts();

    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByRole("heading", { level: 1, name: "Profile & access" })).toBeVisible();
    await expect(page).toHaveTitle(/Account/);
    await expect(page.getByText("Current", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
    await expect(page.getByText(/Internal trade platform/)).toBeVisible();
    // Still signed in, still the same company, still the same permissions.
    await expect(companyPill).toHaveText(companyName);
    expect(await page.locator("li code, li .font-mono").allInnerTexts()).toEqual(permissionsBefore);
    await context.close();
  });

  test("the public status page needs no sign-in and reads in Turkish", async ({
    browser,
    browserName,
  }) => {
    void browserName;
    const context = await browser.newContext({ baseURL: stack().web });
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, "/status");
    await expect(page).toHaveTitle(/Sistem durumu/);
    await expect(page.getByRole("heading", { level: 1, name: "Sistem durumu" })).toBeVisible();
    for (const text of ["Herkese açık · salt okunur", "Canlılık", "Hazırlık", "Sözleşme"]) {
      await expect(page.getByText(text, { exact: true }).first(), text).toBeVisible();
    }
    await expect(page.getByText("Çalışıyor", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Durumu yeniden denetle" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Giriş yap/ })).toBeVisible();
    // Endpoint paths and ids are not translated.
    await expect(page.getByText("/api/v1/health/live")).toBeVisible();

    await page.context().addCookies([{ name: "touche_locale", value: "en", url: stack().web }]);
    await gotoReady(page, "/status");
    await expect(page.getByRole("heading", { level: 1, name: "System status" })).toBeVisible();
    await expect(page.getByText("Operational", { exact: true }).first()).toBeVisible();
    await context.close();
  });

  test("tab titles follow the language on every screen that had a fixed title", async ({
    browser,
    browserName,
  }) => {
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();
    const titles: [string, RegExp][] = [
      ["/", /Yönetim paneli/],
      ["/deals", /Ticari fırsatlar/],
      ["/deals/new", /Yeni fırsat/],
      ["/orders", /Satış siparişleri/],
      ["/crm", /Müşteri ve tedarikçiler/],
      ["/products", /Ürünler/],
      ["/imports", /İçe aktar/],
      ["/company", /Şirket bilgileri/],
      ["/account", /Hesap/],
    ];
    for (const [route, title] of titles) {
      await gotoReady(page, route);
      await expect(page, route).toHaveTitle(title);
      await expect(page, route).toHaveTitle(/TOUCHE COMMERCE/);
    }

    await context.addCookies([{ name: "touche_locale", value: "en", url: stack().web }]);
    await gotoReady(page, "/orders");
    await expect(page).toHaveTitle(/Sales orders/);
    await context.close();
  });

  test("a page that does not exist says so in the chosen language", async ({
    browser,
    browserName,
  }) => {
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();
    await gotoReady(page, "/this-page-does-not-exist");
    await expect(page.getByRole("heading", { level: 1, name: "Sayfa bulunamadı" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Yönetim paneline dön" })).toHaveAttribute(
      "href",
      "/",
    );
    await context.addCookies([{ name: "touche_locale", value: "en", url: stack().web }]);
    await gotoReady(page, "/this-page-does-not-exist");
    await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
    await context.close();
  });

  test("the sales order list keeps its own title, and real dates use Turkish month names", async ({
    browser,
    browserName,
  }) => {
    await prepareLogistics(browser, browserName);
    const context = await signedInContext(browser, "sales", browserName);
    await inTurkish(context);
    const page = await context.newPage();

    await gotoReady(page, "/orders");
    // The title is "Sales orders", not another screen's word (a catalogue key once collided).
    await expect(page.getByRole("heading", { level: 1, name: "Satış siparişleri" })).toBeVisible();
    const turkishDates = [todayAs("tr-TR"), todayAs("tr-TR", 30)];
    const body = await page.locator("main").innerText();
    expect(
      turkishDates.some((date) => body.includes(date)),
      `a Turkish date such as ${turkishDates[0]} on the order list`,
    ).toBe(true);

    await page.getByLabel("Arayüz dili").selectOption("en");
    await expect(page.getByRole("heading", { level: 1, name: "Sales orders" })).toBeVisible();
    const englishDates = [todayAs("en-GB"), todayAs("en-GB", 30)];
    await expect
      .poll(async () => {
        const text = await page.locator("main").innerText();
        return englishDates.some((date) => text.includes(date));
      })
      .toBe(true);
    await context.close();
  });
});
