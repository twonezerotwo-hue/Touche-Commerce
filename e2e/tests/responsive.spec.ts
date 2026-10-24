import { expect, test } from "@playwright/test";

import { authFile, gotoReady, stack } from "./support";

const PAGES = ["/", "/imports", "/products", "/crm", "/deals", "/orders"];

test.describe("responsive layout and keyboard use", () => {
  test("no page scrolls sideways on a phone and the navigation menu opens", async ({
    browser,
    browserName,
  }) => {
    const context = await browser.newContext({
      baseURL: stack().web,
      storageState: authFile("sales", browserName),
      viewport: { width: 390, height: 844 },
    });
    const page = await context.newPage();
    for (const route of PAGES) {
      await page.goto(route);
      await expect(page.locator("main")).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal overflow on ${route}`).toBeLessThanOrEqual(1);
    }
    await page.goto("/");
    await page.getByRole("button", { name: /open navigation/i }).click();
    await expect(page.getByRole("navigation", { name: /primary/i }).last()).toBeVisible();
    await context.close();
  });

  test("the login form can be completed and submitted with the keyboard alone", async ({
    page,
  }) => {
    await gotoReady(page, "/login");
    await page.getByLabel("Email").focus();
    await page.keyboard.type("nobody@acceptance.touche.example");
    await page.keyboard.press("Tab");
    await page.keyboard.type("not-a-real-password");
    await page.keyboard.press("Enter");
    await expect(page.getByText("Email or password is incorrect.")).toBeVisible();
  });
});
