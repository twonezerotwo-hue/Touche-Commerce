import fs from "node:fs";
import path from "node:path";

import { chromium, firefox, webkit, type FullConfig } from "@playwright/test";

import { authFile, credentials, loginViaUi, stack, type Slug } from "./support";

/**
 * Sign every synthetic user in once per browser engine through the real login form and
 * keep the session cookies. The specs then start already signed in, so the suite does not
 * trip the login rate limiter it is also meant to exercise.
 */
export default async function globalSetup(config: FullConfig): Promise<void> {
  const engines = { chromium, firefox, webkit } as const;
  // `config.projects` lists every project even with --project, so honour the flag here.
  const selected = [...process.argv.join(" ").matchAll(/--project[= ]([a-z]+)/g)].map(
    (match) => match[1],
  );
  const wanted = new Set(selected.length > 0 ? selected : config.projects.map((p) => p.name));
  fs.mkdirSync(path.join(__dirname, "..", ".auth"), { recursive: true });

  for (const [name, engine] of Object.entries(engines)) {
    if (!wanted.has(name)) continue;
    const browser = await engine.launch();
    try {
      for (const slug of Object.keys(credentials()) as Slug[]) {
        const context = await browser.newContext({ baseURL: stack().web });
        const page = await context.newPage();
        await loginViaUi(page, slug);
        await page.waitForURL((url) => !url.pathname.startsWith("/login"));
        await context.storageState({ path: authFile(slug, name) });
        await context.close();
      }
    } finally {
      await browser.close();
    }
  }
}
