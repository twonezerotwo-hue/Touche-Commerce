import { describe, expect, it } from "vitest";

import { formatPercent } from "@/lib/sourcing/format";
import { formatDate, formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

import { intlTag } from "./intl";

/** Intl may use a no-break space between a number and a symbol; compare with a plain one. */
const plain = (text: string): string => text.replace(/[  ]/g, " ");

describe("locale-aware number and date formats", () => {
  it("maps the interface language to a number/date locale and nothing else", () => {
    expect(intlTag("en")).toBe("en-GB");
    expect(intlTag("tr")).toBe("tr-TR");
  });

  it("keeps English output exactly as it was before the language switch existed", () => {
    expect(formatMoney("1250.5", "USD")).toBe("US$1,250.50");
    expect(formatQuantity("1250.5", "kg")).toBe("1,250.5 kg");
    expect(formatPercent("14.9949")).toBe("14.99%");
    expect(formatDate("2026-10-24")).toBe("24 Oct 2026");
    expect(formatTimestamp("2026-10-24T11:06:00Z")).toBe("24 Oct 2026, 11:06");
  });

  it("uses Turkish separators and month names without changing the amount or the currency code", () => {
    expect(plain(formatMoney("1250.5", "TRY", "tr"))).toContain("1.250,50");
    expect(formatMoney("1250.5", "EUR", "tr")).toContain("€");
    expect(plain(formatQuantity("1250.5", "kg", "tr"))).toBe("1.250,5 kg");
    expect(formatPercent("14.9949", "tr")).toBe("%14,99");
    expect(formatDate("2026-10-24", "tr")).toBe("24 Eki 2026");
    expect(formatTimestamp("2026-10-24T11:06:00Z", "tr")).toContain("24 Eki 2026");
    expect(formatTimestamp("2026-10-24T11:06:00Z", "tr")).toContain("11:06");
  });

  it("shows a stored date on the same day whatever the machine's time zone is", () => {
    // 23:30 UTC on the 24th must stay the 24th; a local-zone formatter would roll it to the 25th
    // anywhere east of UTC.
    expect(formatDate("2026-10-24T23:30:00Z", "en")).toBe("24 Oct 2026");
    expect(formatDate("2026-10-24T23:30:00Z", "tr")).toBe("24 Eki 2026");
  });

  it("returns values that are not numbers or dates unchanged instead of inventing text", () => {
    expect(formatMoney("n/a", "USD", "tr")).toBe("n/a");
    expect(formatPercent("n/a", "tr")).toBe("n/a");
    expect(formatDate("soon", "tr")).toBe("soon");
    expect(formatDate(null, "tr")).toBe("—");
  });
});
