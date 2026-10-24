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

describe("Stage 12B catalogue integrity", () => {
  const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

  it("has a nonempty Turkish and English text for every key", async () => {
    const { ALL_MESSAGE_KEYS } = await import("./messages");
    expect(ALL_MESSAGE_KEYS.length).toBeGreaterThan(60);
    for (const key of ALL_MESSAGE_KEYS) {
      expect(translate("en", key).trim().length, key).toBeGreaterThan(0);
      expect(translate("tr", key).trim().length, key).toBeGreaterThan(0);
    }
  });

  it("uses the same placeholders in both languages", async () => {
    const { ALL_MESSAGE_KEYS } = await import("./messages");
    for (const key of ALL_MESSAGE_KEYS) {
      expect(placeholders(translate("tr", key)), key).toEqual(placeholders(translate("en", key)));
    }
  });

  it("does not leave a Turkish text identical to English except for names and codes", async () => {
    const { ALL_MESSAGE_KEYS } = await import("./messages");
    // Product names and acronyms that are the same word in both languages.
    const allowedSame = new Set([
      "english",
      "turkish",
      "platform",
      "documentFormatPdf",
      "documentFormatDocx",
      "documentFormatXlsx",
      "documentFormatCsv",
      "profileIban",
      "profileSwift",
    ]);
    const same = ALL_MESSAGE_KEYS.filter(
      (key) => translate("tr", key) === translate("en", key) && !allowedSame.has(key),
    );
    expect(same).toEqual([]);
  });

  it("substitutes placeholders and keeps unknown ones visible", () => {
    expect(translate("tr", "importCommit", { count: 12 })).toBe("12 kaydı içe aktar");
    expect(translate("en", "importCommit", { count: 1 })).toBe("Import 1 records");
    expect(translate("en", "importCommit")).toBe("Import {count} records");
  });
});
