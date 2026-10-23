import { describe, expect, it } from "vitest";

import {
  BASIS_META,
  budgetPercent,
  describeError,
  describeWarning,
  formatTokens,
  formatUsd,
  humanTool,
  isRunFinished,
  safeSourceHref,
} from "./format";

describe("ai format helpers", () => {
  it("labels every evidence basis distinctly", () => {
    const labels = Object.values(BASIS_META).map((meta) => meta.label);
    expect(new Set(labels).size).toBe(labels.length);
    expect(BASIS_META.AI_INFERENCE.label).toBe("AI inference");
    expect(BASIS_META.CONFIRMED_SOURCE.tone).toBe("success");
  });

  it("only links application-internal paths", () => {
    expect(safeSourceHref({ href: "/deals/abc" })).toBe("/deals/abc");
    expect(safeSourceHref({ href: "https://evil.example" })).toBeNull();
    expect(safeSourceHref({ href: "//evil.example" })).toBeNull();
    expect(safeSourceHref({ href: "/\\evil" })).toBeNull();
    expect(safeSourceHref({ href: "javascript:alert(1)" })).toBeNull();
    expect(safeSourceHref({ href: null })).toBeNull();
  });

  it("turns error and warning codes into calm sentences", () => {
    expect(describeError("AI_BUDGET_EXCEEDED")).toMatch(/budget/);
    expect(describeError("SOMETHING_ELSE", "Server said so")).toBe("Server said so");
    expect(describeError(null)).toBe("The request could not be completed.");
    expect(describeWarning("UNVERIFIED_NUMBER")).toMatch(/did not come from any record/);
    expect(describeWarning("SOME_NEW_CODE")).toBe("some new code");
  });

  it("formats tool names, tokens, cost and budgets", () => {
    expect(humanTool("get_order_profitability")).toBe("Get order profitability");
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(1200)).toBe("1.2k");
    expect(formatTokens(48_000)).toBe("48k");
    expect(formatTokens(2_500_000)).toBe("2.5M");
    expect(formatUsd("0.000000")).toBe("$0.00");
    expect(formatUsd("0.004")).toBe("<$0.01");
    expect(formatUsd("5.00")).toBe("$5.00");
    expect(budgetPercent(250, 1000)).toBe(25);
    expect(budgetPercent(5000, 1000)).toBe(100);
    expect(budgetPercent(1, 0)).toBe(0);
  });

  it("knows which run states are final", () => {
    expect(isRunFinished("RUNNING")).toBe(false);
    for (const state of ["COMPLETED", "FAILED", "CANCELLED"] as const) {
      expect(isRunFinished(state)).toBe(true);
    }
  });
});
