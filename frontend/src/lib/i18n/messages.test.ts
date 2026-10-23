import { describe, expect, it } from "vitest";

import { normalizeLocale, translate, type MessageKey } from "./messages";

describe("Stage 12A English/Turkish UI messages", () => {
  it("defaults unsupported preferences to English", () => {
    expect(normalizeLocale(null)).toBe("en");
    expect(normalizeLocale("de")).toBe("en");
    expect(normalizeLocale("tr")).toBe("tr");
    expect(normalizeLocale("en")).toBe("en");
  });

  it("translates the top-bar verification state without changing the underlying auth", () => {
    expect(translate("en", "sessionVerified")).toBe("Session verified");
    expect(translate("tr", "sessionVerified")).toBe("Oturum doğrulandı");
  });

  it("keeps an equivalent nonempty string for every supported shell key", () => {
    const keys: MessageKey[] = [
      "workspace",
      "sessionVerified",
      "systemStatus",
      "profileAccess",
      "language",
      "english",
      "turkish",
      "openNavigation",
      "closeNavigation",
      "mobilePrimary",
      "platform",
      "internalPlatform",
      "languageChanged",
    ];
    for (const key of keys) {
      expect(translate("en", key).length).toBeGreaterThan(0);
      expect(translate("tr", key).length).toBeGreaterThan(0);
    }
  });
});
