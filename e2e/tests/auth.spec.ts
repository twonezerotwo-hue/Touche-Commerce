import { expect, test } from "@playwright/test";

import { credentials, loginViaUi } from "./support";

test.describe("authentication", () => {
  test("a wrong password is refused with one generic message", async ({ page }) => {
    await loginViaUi(page, "viewer", "definitely-not-the-password");
    await expect(page.getByText("Email or password is incorrect.")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("an anonymous visitor is sent to the login page for every private route", async ({
    page,
  }) => {
    for (const route of ["/", "/deals", "/products", "/imports", "/account"]) {
      await page.goto(route);
      await expect(page, `route ${route}`).toHaveURL(/\/login/);
    }
  });

  test("sign-in sets an HttpOnly session cookie and sign-out ends the session", async ({
    page,
    context,
  }) => {
    const loginResponse = page.waitForResponse((r) => r.url().endsWith("/api/v1/auth/login"));
    await loginViaUi(page, "sales");
    await expect(page).toHaveTitle(/Command Center/);
    await expect(page.getByText(credentials().sales.role, { exact: false }).first()).toBeVisible();

    // Assert the header the server sent: WebKit reports SameSite=lax cookies as "None".
    const setCookie = (await (await loginResponse).headersArray())
      .filter((header) => header.name.toLowerCase() === "set-cookie")
      .map((header) => header.value)
      .join("\n");
    expect(setCookie).toMatch(/touche_session=/);
    expect(setCookie).toMatch(/HttpOnly/i);
    expect(setCookie).toMatch(/SameSite=lax/i);

    const session = (await context.cookies()).find((cookie) => cookie.name === "touche_session");
    expect(session?.httpOnly, "session cookie is hidden from page scripts").toBe(true);

    await page.goto("/account");
    await page.getByRole("button", { name: "Sign out" }).first().click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/deals");
    await expect(page).toHaveURL(/\/login/);
  });
});
