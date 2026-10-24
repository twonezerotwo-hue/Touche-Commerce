import { expect, test } from "@playwright/test";

import { gotoReady, signedInContext, type Slug } from "./support";

const CAN_IMPORT: Slug[] = ["sales", "purchasing", "operations"];
// admin ("owner") deliberately has no trade.write (ADR-003: separation of duties).
const CANNOT_IMPORT: Slug[] = ["owner", "finance", "viewer"];

test.describe("role permissions in the browser", () => {
  for (const slug of CAN_IMPORT) {
    test(`${slug} (trader) gets the import wizard`, async ({ browser, browserName }) => {
      const context = await signedInContext(browser, slug, browserName);
      const page = await context.newPage();
      await page.goto("/imports");
      await expect(page.getByRole("button", { name: "Read file" })).toBeVisible();
      await expect(page.getByText("Importing needs the trade permission")).toHaveCount(0);
      await context.close();
    });
  }

  for (const slug of CANNOT_IMPORT) {
    test(`${slug} sees the import history but cannot import`, async ({ browser, browserName }) => {
      const context = await signedInContext(browser, slug, browserName);
      const page = await context.newPage();
      await page.goto("/imports");
      await expect(page.getByText("Importing needs the trade permission")).toBeVisible();
      await expect(page.getByRole("button", { name: "Read file" })).toHaveCount(0);
      await context.close();
    });
  }

  test("a forged import request from a read-only role is refused by the API", async ({
    browser,
    browserName,
  }) => {
    const context = await signedInContext(browser, "viewer", browserName);
    const page = await context.newPage();
    await gotoReady(page, "/");
    const status = await page.evaluate(async () => {
      const form = new FormData();
      form.append("kind", "products");
      form.append("file", new File(["sku,name\nA,B\n"], "x.csv", { type: "text/csv" }));
      const response = await fetch("/api/v1/imports/inspect", {
        method: "POST",
        body: form,
        credentials: "same-origin",
      });
      return response.status;
    });
    expect([401, 403]).toContain(status);
    await context.close();
  });

  test("each role is shown under its own badge in the top bar", async ({
    browser,
    browserName,
  }) => {
    const expected: Record<Slug, string> = {
      owner: "admin",
      sales: "trader",
      purchasing: "trader",
      operations: "trader",
      finance: "approver",
      viewer: "viewer",
      outsider: "admin",
    };
    for (const slug of Object.keys(expected) as Slug[]) {
      const context = await signedInContext(browser, slug, browserName);
      const page = await context.newPage();
      await page.goto("/");
      await expect(
        page.locator("header").getByText(expected[slug], { exact: true }),
        `${slug} badge`,
      ).toBeVisible();
      await context.close();
    }
  });
});
