import { describe, expect, it } from "vitest";

import {
  NAV_ITEMS,
  PLATFORM_STAGE_LABEL,
  resolveActiveHref,
  resolveWorkspaceContext,
} from "./navigation";

describe("financial intelligence navigation", () => {
  it("links the intelligence workspace as a Stage 5E module", () => {
    const item = NAV_ITEMS.find((entry) => entry.href === "/finance/intelligence");
    expect(item?.label).toBe("Intelligence");
    expect(item?.stage).toBe("Stage 5E");
  });

  it("gives every intelligence route a label instead of a generic fallback", () => {
    expect(resolveWorkspaceContext("/finance/intelligence")).toEqual({
      section: "Finance",
      page: "Intelligence",
    });
    expect(resolveWorkspaceContext("/finance/intelligence/orders").page).toBe(
      "Order profitability",
    );
    expect(
      resolveWorkspaceContext("/finance/intelligence/orders/7f1c1b3e-0000-4000-8000-000000000001")
        .page,
    ).toBe("Order intelligence");
    expect(resolveWorkspaceContext("/finance/intelligence/exceptions").page).toBe(
      "Financial exceptions",
    );
  });

  it("keeps the earlier finance labels intact", () => {
    expect(resolveWorkspaceContext("/finance/reconciliation").page).toBe("Reconciliation");
    expect(resolveWorkspaceContext("/finance/discrepancies").page).toBe("Discrepancies");
  });
});

describe("AI Office navigation", () => {
  it("is a real link, not a roadmap placeholder", () => {
    const item = NAV_ITEMS.find((entry) => entry.label === "AI Office");
    expect(item?.href).toBe("/ai");
    expect(item?.stage).toBe("Stage 6");
    expect(resolveWorkspaceContext("/ai")).toEqual({ section: "AI", page: "AI Office" });
  });

  it("states the current platform stage in the footer label", () => {
    expect(PLATFORM_STAGE_LABEL).toMatch(/Stage 6/);
    expect(PLATFORM_STAGE_LABEL).not.toMatch(/5D/);
  });
});

describe("active navigation entry", () => {
  it("highlights only the most specific entry for a nested route", () => {
    expect(resolveActiveHref("/finance/intelligence")).toBe("/finance/intelligence");
    expect(resolveActiveHref("/finance/intelligence/orders/abc")).toBe("/finance/intelligence");
    expect(resolveActiveHref("/finance/reconciliation/run-1")).toBe("/finance/reconciliation");
    expect(resolveActiveHref("/finance")).toBe("/finance");
    expect(resolveActiveHref("/finance/orders/abc")).toBe("/finance");
  });

  it("matches the root only exactly and returns null for unknown paths", () => {
    expect(resolveActiveHref("/")).toBe("/");
    expect(resolveActiveHref("/deals/123")).toBe("/deals");
    expect(resolveActiveHref("/nowhere")).toBeNull();
  });
});
