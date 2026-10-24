import fs from "node:fs";
import path from "node:path";

import { expect, type Browser, type BrowserContext, type Page } from "@playwright/test";

const ROOT = path.resolve(__dirname, "..", "..");
const ACCEPTANCE = path.join(ROOT, "backend", "var", "acceptance");

export type Slug =
  "owner" | "sales" | "purchasing" | "operations" | "finance" | "viewer" | "outsider";

export interface Credential {
  email: string;
  password: string;
  role: string;
  company: "A" | "B";
}

export function credentials(): Record<Slug, Credential> {
  const file = path.join(ACCEPTANCE, "credentials.json");
  if (!fs.existsSync(file)) {
    throw new Error("Run backend scripts.seed_acceptance first: no acceptance credentials found.");
  }
  return (
    JSON.parse(fs.readFileSync(file, "utf-8")) as {
      users: Record<Slug, Credential>;
    }
  ).users;
}

export function stack(): { web: string; api: string } {
  if (process.env.E2E_WEB_URL) {
    return { web: process.env.E2E_WEB_URL, api: process.env.E2E_API_URL ?? "" };
  }
  const file = path.join(ACCEPTANCE, "stack.json");
  if (!fs.existsSync(file)) {
    throw new Error("Start the acceptance stack first (scripts/acceptance_stack.py).");
  }
  return JSON.parse(fs.readFileSync(file, "utf-8")) as {
    web: string;
    api: string;
  };
}

export const authFile = (slug: Slug, browserName: string): string =>
  path.join(__dirname, "..", ".auth", `${browserName}-${slug}.json`);

/**
 * Navigate and wait until React has hydrated, so early input is not lost (seen on WebKit).
 * A client-side refresh that is still settling can interrupt a navigation; retry that case.
 */
export async function gotoReady(page: Page, url: string): Promise<void> {
  for (let attempt = 1; ; attempt += 1) {
    try {
      await page.goto(url);
      break;
    } catch (error) {
      if (attempt >= 3 || !/interrupted by another navigation/.test(String(error))) throw error;
      await page.waitForLoadState("networkidle");
    }
  }
  await page.waitForLoadState("networkidle");
}

/** Sign in through the real login form. */
export async function loginViaUi(page: Page, slug: Slug, password?: string): Promise<void> {
  const credential = credentials()[slug];
  await gotoReady(page, "/login");
  await page.getByLabel("Email").fill(credential.email);
  await page.getByLabel("Password", { exact: true }).fill(password ?? credential.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

export async function signedInContext(
  browser: Browser,
  slug: Slug,
  browserName: string,
): Promise<BrowserContext> {
  return browser.newContext({
    baseURL: stack().web,
    storageState: authFile(slug, browserName),
  });
}

export const runId = (): string => Date.now().toString(36).toUpperCase();

export function productsCsv(prefix: string, count: number): string {
  const rows = ["sku,name,unit,currency,unit_price"];
  for (let index = 1; index <= count; index += 1) {
    rows.push(
      `${prefix}-${String(index).padStart(2, "0")},Test product ${index},kg,USD,${index}.2500`,
    );
  }
  return `${rows.join("\n")}\n`;
}

export function csvFile(name: string, content: string) {
  return { name, mimeType: "text/csv", buffer: Buffer.from(content, "utf-8") };
}

/** Walk the import wizard up to the review step and return the summary text. */
export async function reachReview(
  page: Page,
  file: ReturnType<typeof csvFile>,
  kind: "products" | "counterparties" = "products",
): Promise<string> {
  await gotoReady(page, "/imports");
  if (kind === "counterparties") {
    await page
      .getByLabel("What are you importing?")
      .selectOption({ label: "Customers and suppliers" });
  }
  await page.getByLabel(/File \(\.csv/).setInputFiles(file);
  await page.getByRole("button", { name: "Read file" }).click();
  await expect(page.getByText("Match the columns")).toBeVisible();
  await page.getByRole("button", { name: "Preview import" }).click();
  const summary = page.getByRole("status");
  await expect(summary).toContainText("rows ·");
  return (await summary.textContent()) ?? "";
}
