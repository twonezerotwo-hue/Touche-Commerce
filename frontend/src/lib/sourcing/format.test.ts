import { describe, expect, it } from "vitest";

import { etagFor, formatPercent, statusLabel, statusTone } from "./format";

describe("sourcing status labels", () => {
  it("renders enum values as words instead of leaking the enum", () => {
    expect(statusLabel("PENDING_APPROVAL")).toBe("Pending approval");
    expect(statusLabel("VERIFIED_INPUTS")).toBe("Verified inputs");
    expect(statusLabel("RESPONDED")).toBe("Responded");
  });

  it("falls back to the raw value for an unknown status", () => {
    expect(statusLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
    expect(statusTone("SOMETHING_NEW")).toBe("secondary");
  });

  it("gives terminal and approval states distinct tones", () => {
    expect(statusTone("APPROVED")).toBe("success");
    expect(statusTone("REJECTED")).toBe("danger");
    expect(statusTone("WITHDRAWN")).toBe("outline");
  });
});

describe("formatPercent", () => {
  it("drops stored trailing zeros without rounding real precision away", () => {
    expect(formatPercent("20.0000")).toBe("20%");
    expect(formatPercent("14.9949")).toBe("14.99%");
  });

  it("renders an em dash for missing values", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent("")).toBe("—");
  });

  it("returns a non-numeric value unchanged rather than showing NaN", () => {
    expect(formatPercent("n/a")).toBe("n/a");
  });
});

describe("etagFor", () => {
  it("matches the API's strong ETag format", () => {
    expect(etagFor(7)).toBe('"v7"');
  });
});
