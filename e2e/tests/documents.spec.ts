import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import { gotoReady, runId, signedInContext } from "./support";

test.describe("company profile and document downloads", () => {
  test("the administrator saves the profile; it persists and a trader sees it read-only", async ({
    browser,
    browserName,
  }) => {
    const legalName = `Anadolu Ticaret ${runId()} A.Ş.`;
    const owner = await signedInContext(browser, "owner", browserName);
    const page = await owner.newPage();
    await gotoReady(page, "/company");
    await page.getByLabel("Legal name").fill(legalName);
    await page.getByLabel("Tax number").fill("1234567890");
    await page.getByLabel("Address").fill("Örnek Mah. 1. Sk. No:1");
    await page.getByLabel("City").fill("İstanbul");
    await page.getByLabel("IBAN").fill("GB82 WEST 1234 5698 7654 32");
    await page.getByRole("button", { name: "Save profile" }).click();
    await expect(page.getByText("Profile saved.")).toBeVisible();
    await expect(page.getByRole("status")).toContainText("All details customers expect");

    await page.reload();
    await expect(page.getByLabel("Legal name")).toHaveValue(legalName);
    await expect(page.getByLabel("IBAN")).toHaveValue("GB82WEST12345698765432");

    const sales = await signedInContext(browser, "sales", browserName);
    const tradersPage = await sales.newPage();
    await gotoReady(tradersPage, "/company");
    await expect(tradersPage.getByLabel("Legal name")).toHaveValue(legalName);
    await expect(tradersPage.getByLabel("Legal name")).toBeDisabled();
    await expect(tradersPage.getByText("Only an administrator can change")).toBeVisible();
    await expect(tradersPage.getByRole("button", { name: "Save profile" })).toHaveCount(0);
    await owner.close();
    await sales.close();
  });

  test("an invalid IBAN is refused and marked; nothing is saved", async ({
    browser,
    browserName,
  }) => {
    const owner = await signedInContext(browser, "owner", browserName);
    const page = await owner.newPage();
    await gotoReady(page, "/company");
    await page.getByLabel("IBAN").fill("GB82 WEST 1234 5698 7654 33");
    await page.getByRole("button", { name: "Save profile" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "VALIDATION_ERROR" })).toBeVisible();
    await expect(page.getByLabel("IBAN")).toHaveAttribute("aria-invalid", "true");
    await owner.close();
  });

  test("two administrators editing at once: the second save is told, not silently lost", async ({
    browser,
    browserName,
  }) => {
    const first = await signedInContext(browser, "owner", browserName);
    const second = await signedInContext(browser, "owner", browserName);
    const a = await first.newPage();
    const b = await second.newPage();
    await Promise.all([gotoReady(a, "/company"), gotoReady(b, "/company")]);

    await a.getByLabel("City").fill(`Ankara ${runId()}`);
    await a.getByRole("button", { name: "Save profile" }).click();
    await expect(a.getByText("Profile saved.")).toBeVisible();

    await b.getByLabel("City").fill("İzmir");
    await b.getByRole("button", { name: "Save profile" }).click();
    await expect(
      b.getByRole("alert").filter({ hasText: "Someone else changed the profile" }),
    ).toBeVisible();
    await expect(b.getByLabel("City")).toHaveValue("İzmir"); // what was typed is kept
    await first.close();
    await second.close();
  });

  test("a trader downloads the shipment register as CSV and a PDF in Turkish", async ({
    browser,
    browserName,
  }) => {
    const sales = await signedInContext(browser, "sales", browserName);
    const page = await sales.newPage();
    await gotoReady(page, "/shipments");

    const csvLink = page.getByRole("link", { name: "Download Shipment register as CSV" });
    const [csv] = await Promise.all([page.waitForEvent("download"), csvLink.click()]);
    expect(csv.suggestedFilename()).toMatch(/^shipment_register-.*-en\.csv$/);
    const csvBytes = readFileSync((await csv.path()) ?? "");
    expect([...csvBytes.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]); // BOM for Excel
    expect(csvBytes.toString("utf-8")).toContain("Shipment,Sales order,Mode");

    await page.getByLabel("Document language").selectOption("tr");
    const pdfLink = page.getByRole("link", {
      name: /Sevkiyat kaydı belgesini PDF olarak indir|Download Shipment register as PDF/,
    });
    const [pdf] = await Promise.all([page.waitForEvent("download"), pdfLink.click()]);
    expect(pdf.suggestedFilename()).toMatch(/-tr\.pdf$/);
    const pdfBytes = readFileSync((await pdf.path()) ?? "");
    expect(pdfBytes.subarray(0, 5).toString("latin1")).toBe("%PDF-");
    await sales.close();
  });

  test("roles that cannot trade or review finance are not offered documents", async ({
    browser,
    browserName,
  }) => {
    for (const slug of ["viewer", "owner"] as const) {
      const context = await signedInContext(browser, slug, browserName);
      const page = await context.newPage();
      await gotoReady(page, "/shipments");
      await expect(page.getByRole("region", { name: "Documents" }), slug).toHaveCount(0);
      const direct = await page.request.get("/api/v1/generated-documents/shipment_register");
      expect(direct.status(), `${slug} must be refused by the API too`).toBe(403);
      await context.close();
    }
  });
});
