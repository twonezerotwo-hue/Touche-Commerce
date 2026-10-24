import { expect, test } from "@playwright/test";

import { signIn } from "./support";

/**
 * Opt-in: needs a running E-YAY API on 127.0.0.1:9000 (paper-only, no execution), already warm
 * (its first regime report builds a snapshot and can take several seconds) and the acceptance
 * stack started with TOUCHE_EYAY_ENABLED=true. Run with E2E_EYAY_LIVE=1. Commerce only ever sends
 * two GET requests to E-YAY; nothing here touches paper trading, portfolio or orders.
 */
test.skip(!process.env.E2E_EYAY_LIVE, "set E2E_EYAY_LIVE=1 with a live, warm E-YAY API");

test.describe("E-YAY market context, read-only, live", () => {
  test("a signed-in member gets the verified, read-only market context", async ({ page }) => {
    await signIn(page, "sales");

    const response = await page.request.get("/api/v1/integrations/eyay/market");
    expect(response.status()).toBe(200);
    expect(response.headers()["cache-control"]).toBe("no-store");
    const market = await response.json();
    expect(market.integration_state).toBe("ISOLATED_HTTP_READ_ONLY");
    expect(market.mode).toBe("READ_ONLY");
    expect(market.source).toBe("CLEAN_E_YAY");
    expect(["OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"]).toContain(market.regime);
    expect(market.assets.length).toBeGreaterThan(0);
    for (const asset of market.assets) {
      expect(["bullish", "bearish", "neutral"]).toContain(asset.direction);
      expect(["BLOCKING", "PENDING", "CONFIRMED"]).toContain(asset.status);
      expect(asset.score).toBeGreaterThanOrEqual(0);
      expect(asset.score).toBeLessThanOrEqual(100);
    }
    // Whatever E-YAY says, Commerce never turns it into an action.
    expect(market.trade_actions_enabled).toBe(false);
    expect(market.automatic_execution_enabled).toBe(false);
    expect(market.finance_writes_enabled).toBe(false);
    expect(market.source_snapshot_id).toBeTruthy();
  });

  test("it needs a session and offers no way to send anything to E-YAY", async ({
    page,
    request,
  }) => {
    const anonymous = await request.get("/api/v1/integrations/eyay/market");
    expect(anonymous.status()).toBe(401);

    await signIn(page, "viewer");
    expect((await page.request.get("/api/v1/integrations/eyay/market")).status()).toBe(200);
    for (const method of ["post", "put", "delete"] as const) {
      const refused = await page.request[method]("/api/v1/integrations/eyay/market", {
        data: {},
      });
      expect([403, 404, 405], method).toContain(refused.status());
    }
  });
});
