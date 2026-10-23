import { describe, expect, it } from "vitest";

import {
  barShare,
  completenessTone,
  exportFilename,
  groupByCurrency,
  hasActiveFilters,
  isNegative,
  humanize,
  intelligenceQuery,
  maxAbs,
  metricLines,
  parseIntelligenceFilters,
  tooltipAlign,
  type IntelligenceMetric,
} from "./intelligence";

function metric(overrides: Partial<IntelligenceMetric> = {}): IntelligenceMetric {
  return {
    key: "accepted_value",
    label: "Accepted order value",
    kind: "MONEY",
    money: [],
    percentages: [],
    percentage: null,
    count: null,
    available: true,
    classification: "DOCUMENTED",
    completeness: "COMPLETE",
    meaning: "Documented customer acceptance.",
    as_of: "2026-10-23",
    data_through: null,
    ...overrides,
  };
}

describe("parseIntelligenceFilters", () => {
  it("keeps well-formed filters and normalises their case", () => {
    expect(
      parseIntelligenceFilters({
        from: "2026-01-01",
        to: "2026-10-23",
        currency: "usd",
        fulfilment_model: "purchase_resale",
        customer_id: "9F1B2C3D-0000-4000-8000-000000000001",
        completeness: "partial",
      }),
    ).toEqual({
      from: "2026-01-01",
      to: "2026-10-23",
      currency: "USD",
      fulfilment_model: "PURCHASE_RESALE",
      customer_id: "9f1b2c3d-0000-4000-8000-000000000001",
      completeness: "PARTIAL",
    });
  });

  it("silently drops malformed values and unknown keys", () => {
    expect(
      parseIntelligenceFilters({
        from: "23/10/2026",
        currency: "USDX",
        customer_id: "not-a-uuid",
        order_status: "bad value!",
        company_id: "11111111-1111-4111-8111-111111111111",
        view: "variance",
      }),
    ).toEqual({});
  });

  it("uses the first value of a repeated parameter", () => {
    expect(parseIntelligenceFilters({ currency: ["eur", "usd"] })).toEqual({ currency: "EUR" });
  });
});

describe("intelligenceQuery", () => {
  it("serialises only known filters, then paging", () => {
    expect(
      intelligenceQuery({ currency: "USD", from: "2026-01-01" }, { limit: 25, offset: 50 }),
    ).toBe("from=2026-01-01&currency=USD&limit=25&offset=50");
  });

  it("skips empty extras and is empty without filters", () => {
    expect(intelligenceQuery({}, { offset: null, limit: "" })).toBe("");
  });

  it("reports whether any filter is active", () => {
    expect(hasActiveFilters({})).toBe(false);
    expect(hasActiveFilters({ currency: "USD" })).toBe(true);
  });
});

describe("metricLines", () => {
  it("lists money per currency and never adds currencies together", () => {
    const lines = metricLines(
      metric({
        money: [
          { currency: "USD", amount: "250.00" },
          { currency: "EUR", amount: "100.00" },
        ],
      }),
    );
    expect(lines).toHaveLength(2);
    expect(lines.map((line) => line.currency)).toEqual(["USD", "EUR"]);
    expect(lines[0].text).toContain("250.00");
    expect(lines[1].text).toContain("100.00");
    expect(lines.some((line) => line.text.includes("350"))).toBe(false);
  });

  it("returns no lines for an unavailable metric so it can never read as zero", () => {
    expect(
      metricLines(metric({ available: false, money: [{ currency: "USD", amount: "0.00" }] })),
    ).toEqual([]);
  });

  it("formats per-currency percentages and a single percentage", () => {
    expect(
      metricLines(
        metric({
          kind: "PERCENT",
          percentages: [
            { currency: "USD", value: "32.00" },
            { currency: "EUR", value: "-4.50" },
          ],
        }),
      ).map((line) => line.text),
    ).toEqual(["32.00%", "-4.50%"]);
    expect(metricLines(metric({ kind: "PERCENT", percentage: "12.50" }))[0]).toEqual({
      currency: null,
      text: "12.50%",
      negative: false,
    });
  });

  it("renders a count and treats a missing count as unavailable", () => {
    expect(metricLines(metric({ kind: "COUNT", count: 0 }))).toEqual([
      { currency: null, text: "0", negative: false },
    ]);
    expect(metricLines(metric({ kind: "COUNT", count: null }))).toEqual([]);
  });

  it("flags a loss on its line so the card can tint it", () => {
    const money = metricLines(
      metric({
        money: [
          { currency: "USD", amount: "-1234.50" },
          { currency: "EUR", amount: "10.00" },
        ],
      }),
    );
    expect(money.map((line) => line.negative)).toEqual([true, false]);
    expect(money[0].text).toContain("-");

    const percent = metricLines(
      metric({
        kind: "PERCENT",
        percentages: [
          { currency: "USD", value: "-12.50" },
          { currency: "EUR", value: "21.75" },
        ],
      }),
    );
    expect(percent.map((line) => line.negative)).toEqual([true, false]);
  });
});

describe("isNegative", () => {
  it("is true only for a parsable value below zero", () => {
    expect(isNegative("-0.01")).toBe(true);
    expect(isNegative("0.00")).toBe(false);
    expect(isNegative("12.50")).toBe(false);
    expect(isNegative(null)).toBe(false);
    expect(isNegative(undefined)).toBe(false);
    expect(isNegative("not a number")).toBe(false);
  });
});

describe("chart helpers", () => {
  it("sizes bars against the largest absolute value without inventing a value", () => {
    expect(barShare("50.00", 100)).toBe(50);
    expect(barShare("-100.00", 100)).toBe(100);
    expect(barShare(null, 100)).toBe(0);
    expect(barShare("abc", 100)).toBe(0);
    expect(barShare("10.00", 0)).toBe(0);
    expect(maxAbs(["10.00", "-40.00", null, undefined, "x"])).toBe(40);
  });

  it("anchors tooltips of marks near either edge to that edge", () => {
    expect(Array.from({ length: 4 }, (_, i) => tooltipAlign(i, 4))).toEqual([
      "center",
      "center",
      "center",
      "center",
    ]);
    expect(Array.from({ length: 12 }, (_, i) => tooltipAlign(i, 12))).toEqual([
      "start",
      "start",
      "start",
      "start",
      "center",
      "center",
      "center",
      "center",
      "end",
      "end",
      "end",
      "end",
    ]);
    expect(Array.from({ length: 5 }, (_, i) => tooltipAlign(i, 5))).toEqual([
      "start",
      "start",
      "center",
      "end",
      "end",
    ]);
  });

  it("groups rows by currency in first-seen order", () => {
    const groups = groupByCurrency([
      { currency: "USD", n: 1 },
      { currency: "EUR", n: 2 },
      { currency: "USD", n: 3 },
    ]);
    expect(groups.map((group) => group.currency)).toEqual(["USD", "EUR"]);
    expect(groups[0].rows.map((row) => row.n)).toEqual([1, 3]);
  });
});

describe("labels and filenames", () => {
  it("humanises enum values and picks a tone per completeness", () => {
    expect(humanize("PURCHASE_RESALE")).toBe("PURCHASE RESALE");
    expect(completenessTone("COMPLETE")).toBe("success");
    expect(completenessTone("PARTIAL")).toBe("warning");
    expect(completenessTone("MISSING")).toBe("danger");
    expect(completenessTone("UNAVAILABLE")).toBe("outline");
  });

  it("uses the server file name only when it is a plain name", () => {
    const fallback = "fallback.csv";
    expect(exportFilename('attachment; filename="analysis-20261023.csv"', fallback)).toBe(
      "analysis-20261023.csv",
    );
    expect(exportFilename('attachment; filename="../../etc/passwd"', fallback)).toBe(fallback);
    expect(exportFilename(null, fallback)).toBe(fallback);
  });
});
