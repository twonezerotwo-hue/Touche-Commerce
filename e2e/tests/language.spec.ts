import { expect, test } from "@playwright/test";

import { gotoReady, signedInContext } from "./support";

test.describe("interface language", () => {
  test("the choice is stored in a cookie, survives reload and does not leak to other users", async ({
    browser,
    browserName,
  }) => {
    const sales = await signedInContext(browser, "sales", browserName);
    const page = await sales.newPage();
    await gotoReady(page, "/imports");
    await expect(page.getByRole("heading", { name: "Import data" })).toBeVisible();

    await page.getByLabel("Language").selectOption("tr");
    await expect(page.getByRole("heading", { name: "Veri içe aktar" })).toBeVisible();
    expect((await sales.cookies()).find((c) => c.name === "touche_locale")?.value).toBe("tr");
    await expect(page.locator("html")).toHaveAttribute("lang", "tr");

    await page.reload();
    await expect(page.getByRole("heading", { name: "Veri içe aktar" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Dosyayı oku" })).toBeVisible();

    const viewer = await signedInContext(browser, "viewer", browserName);
    const other = await viewer.newPage();
    await other.goto("/imports");
    await expect(other.getByRole("heading", { name: "Import data" })).toBeVisible();

    await page.getByLabel("Dil").selectOption("en");
    await expect(page.getByRole("heading", { name: "Import data" })).toBeVisible();
    await viewer.close();
    await sales.close();
  });
});
