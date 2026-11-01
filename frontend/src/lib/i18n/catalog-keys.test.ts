import { describe, expect, it } from "vitest";

import { authEn } from "./catalog/auth";
import { commonEn } from "./catalog/common";
import { dashboardEn } from "./catalog/dashboard";
import { dealsEn } from "./catalog/deals";
import { documentsEn } from "./catalog/documents";
import { importsEn } from "./catalog/imports";
import { logisticsEn } from "./catalog/logistics";
import { ordersEn } from "./catalog/orders";
import { sourcingEn } from "./catalog/sourcing";
import { tradeEn } from "./catalog/trade";

/**
 * The catalogues are merged with object spread, so a key defined in two files would silently let
 * the later one win. This makes a collision a test failure instead of a wrong word on a screen.
 */
describe("message catalogues", () => {
  it("never define the same key twice", () => {
    const catalogues: Record<string, Record<string, string>> = {
      auth: authEn,
      common: commonEn,
      dashboard: dashboardEn,
      deals: dealsEn,
      documents: documentsEn,
      imports: importsEn,
      logistics: logisticsEn,
      orders: ordersEn,
      sourcing: sourcingEn,
      trade: tradeEn,
    };
    const owner = new Map<string, string>();
    const clashes: string[] = [];
    for (const [name, catalogue] of Object.entries(catalogues)) {
      for (const key of Object.keys(catalogue)) {
        const previous = owner.get(key);
        if (previous) clashes.push(`${key}: ${previous} and ${name}`);
        else owner.set(key, name);
      }
    }
    expect(clashes).toEqual([]);
  });
});
