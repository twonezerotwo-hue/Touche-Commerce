import { expect, test, type Page } from "@playwright/test";

import { csvFile, productsCsv, reachReview, runId, signedInContext, type Slug } from "./support";

const ALL: Slug[] = ["owner", "sales", "purchasing", "operations", "finance", "viewer"];

test.describe("several people at once", () => {
  test("six signed-in users browse the main screens together without an error page", async ({
    browser,
    browserName,
  }) => {
    // Six people x seven screens at once against a dev server that compiles on demand.
    test.setTimeout(180_000);
    const routes = ["/", "/deals", "/crm", "/products", "/imports", "/orders", "/documents"];
    const contexts = await Promise.all(
      ALL.map((slug) => signedInContext(browser, slug, browserName)),
    );
    const pages = await Promise.all(contexts.map((context) => context.newPage()));
    const failures: string[] = [];

    await Promise.all(
      pages.map(async (page, index) => {
        for (const route of routes) {
          const response = await page.goto(route);
          const status = response?.status() ?? 0;
          if (status >= 500 || (await page.locator("main").count()) === 0) {
            failures.push(`${ALL[index]} ${route} -> ${status}`);
          }
        }
      }),
    );
    expect(failures).toEqual([]);
    await Promise.all(contexts.map((context) => context.close()));
  });

  test("three traders import different files at the same moment and every file lands once", async ({
    browser,
    browserName,
  }) => {
    const traders: Slug[] = ["sales", "purchasing", "operations"];
    const batch = runId();
    const jobs = await Promise.all(
      traders.map(async (slug, index) => {
        const context = await signedInContext(browser, slug, browserName);
        const page = await context.newPage();
        const prefix = `CON${batch}${index}`;
        await reachReview(page, csvFile(`${prefix}.csv`, productsCsv(prefix, 4)));
        await page.getByLabel(/I reviewed this preview/).check();
        return { context, page, prefix };
      }),
    );

    await Promise.all(
      jobs.map(({ page }) => page.getByRole("button", { name: "Import 4 records" }).click()),
    );
    for (const { page } of jobs) {
      await expect(page.getByText("4 created, 0 skipped.")).toBeVisible();
    }
    for (const { prefix } of jobs) {
      const response = await jobs[0].page.request.get(`/api/v1/products?search=${prefix}`);
      expect((await response.json()).items).toHaveLength(4);
    }
    await Promise.all(jobs.map(({ context }) => context.close()));
  });

  test("two traders submitting the identical file together create it exactly once", async ({
    browser,
    browserName,
  }) => {
    const prefix = `DUP${runId()}`;
    const content = productsCsv(prefix, 5);
    const pairs: { page: Page; close: () => Promise<void> }[] = [];
    for (const slug of ["sales", "purchasing"] as Slug[]) {
      const context = await signedInContext(browser, slug, browserName);
      const page = await context.newPage();
      await reachReview(page, csvFile("same.csv", content));
      await page.getByLabel(/I reviewed this preview/).check();
      pairs.push({ page, close: () => context.close() });
    }

    await Promise.all(
      pairs.map(({ page }) => page.getByRole("button", { name: "Import 5 records" }).click()),
    );
    // One wins; the other is told the file was already imported or could not be completed.
    for (const { page } of pairs) {
      await expect(
        page.getByText(/Import finished|could not be completed|already/i).first(),
      ).toBeVisible();
    }
    const response = await pairs[0].page.request.get(`/api/v1/products?search=${prefix}`);
    expect((await response.json()).items).toHaveLength(5);
    await Promise.all(pairs.map(({ close }) => close()));
  });
});
