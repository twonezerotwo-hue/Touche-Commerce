import { describe, expect, it } from "vitest";

import { NAV_ITEMS, resolveWorkspaceContext } from "./navigation";

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
