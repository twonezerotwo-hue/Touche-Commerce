import { describe, expect, it } from "vitest";

import { defaultAcceptedAt } from "./order-conversion";

/** Local wall-clock text -> the instant it denotes, as the form's own parsing does it. */
const instant = (value: string): number => new Date(value).getTime();

describe("the pre-filled customer acceptance time", () => {
  const now = new Date("2026-10-24T10:30:42.700Z");

  it("is now, to the minute, when the approval is older", () => {
    const value = defaultAcceptedAt("2026-10-22T09:00:00Z", now);
    expect(value).toHaveLength(16); // YYYY-MM-DDTHH:mm
    expect(instant(value)).toBe(Math.floor(now.getTime() / 60_000) * 60_000);
    expect(instant(value)).toBeLessThanOrEqual(now.getTime());
  });

  it("is never earlier than an approval made seconds ago (it was refused by the API)", () => {
    const approvedAt = "2026-10-24T10:30:15.482Z"; // earlier in the same minute
    const value = defaultAcceptedAt(approvedAt, now);
    expect(value).toHaveLength(19); // seconds are kept
    expect(instant(value)).toBeGreaterThanOrEqual(new Date(approvedAt).getTime());
    expect(instant(value)).toBeLessThanOrEqual(now.getTime());
  });

  it("falls back to the minute for a missing or unreadable approval time", () => {
    expect(defaultAcceptedAt(null, now)).toHaveLength(16);
    expect(defaultAcceptedAt("not a date", now)).toHaveLength(16);
  });
});
