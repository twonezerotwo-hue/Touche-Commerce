import { describe, expect, it } from "vitest";

import {
  formatDate,
  formatMoney,
  formatQuantity,
  lineTotal,
  statusLabel,
  statusTone,
  sumTotals,
  withQuery,
} from "./format";

describe("trade formatting", () => {
  it("formats money from decimal strings without silently rounding away cents", () => {
    expect(formatMoney("122500.00", "USD")).toContain("122,500");
    expect(formatMoney("0.5", "EUR")).toContain("0.50");
    expect(formatMoney("not-a-number", "USD")).toBe("not-a-number");
  });

  it("formats quantities with their unit", () => {
    expect(formatQuantity("50.000", "mt")).toBe("50 mt");
    expect(formatQuantity("1.234", "kg")).toBe("1.234 kg");
  });

  it("computes line totals with cent rounding", () => {
    expect(lineTotal("50.000", "2450.0000")).toBe("122500.00");
    expect(lineTotal("0", "2450")).toBe("0.00");
    expect(lineTotal("abc", "1")).toBe("0.00");
    expect(sumTotals(["122500.00", "0.50", "1.25"])).toBe("122501.75");
  });

  it("labels and tones every deal status", () => {
    expect(statusLabel("NEGOTIATION")).toBe("Negotiation");
    expect(statusTone("LOST")).toBe("danger");
    expect(statusTone("WON")).toBe("success");
    expect(statusTone("DRAFT")).toBe("secondary");
  });

  it("formats dates and keeps unknown values visible", () => {
    expect(formatDate("2026-11-30")).toMatch(/2026/);
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });

  it("builds URLs while dropping empty filters", () => {
    expect(withQuery("/deals", { status: "OPEN", search: "", cursor: null })).toBe(
      "/deals?status=OPEN",
    );
    expect(withQuery("/crm", {})).toBe("/crm");
  });
});
