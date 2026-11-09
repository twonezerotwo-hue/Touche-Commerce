import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchLiveness } from "@/lib/api/client";
import { logout } from "@/lib/auth/client";

import { browserLocale, browserT, localeFromCookieHeader } from "./runtime";

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.lang = "";
});

describe("the language of code that has no React context", () => {
  it("reads <html lang> in a browser, English when it is empty or unknown", () => {
    expect(browserLocale()).toBe("en");
    document.documentElement.lang = "tr";
    expect(browserLocale()).toBe("tr");
    expect(browserT("failGeneric")).toBe("İstek tamamlanamadı.");
    document.documentElement.lang = "de";
    expect(browserLocale()).toBe("en");
  });

  it("reads the language cookie out of a Cookie header", () => {
    expect(localeFromCookieHeader("a=1; touche_locale=tr; b=2")).toBe("tr");
    expect(localeFromCookieHeader("touche_locale=en")).toBe("en");
    expect(localeFromCookieHeader("touche_session=x")).toBe("en");
    expect(localeFromCookieHeader(null)).toBe("en");
  });
});

describe("failure messages this app writes itself", () => {
  it("says the API cannot be reached in the language of the page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
    expect(await logout("csrf")).toMatchObject({
      ok: false,
      code: "UNREACHABLE",
      message: "Cannot reach the API. Confirm the service is running and try again.",
    });
    document.documentElement.lang = "tr";
    expect(await logout("csrf")).toMatchObject({
      ok: false,
      code: "UNREACHABLE",
      message: "API'ye ulaşılamıyor. Hizmetin çalıştığını doğrulayıp yeniden deneyin.",
    });
  });

  it("translates the generic failure but shows what the API said as received", async () => {
    const reply = (body: unknown, status: number) =>
      vi.fn().mockResolvedValue({
        ok: false,
        status,
        headers: new Headers(),
        json: async () => body,
      });
    document.documentElement.lang = "tr";
    vi.stubGlobal("fetch", reply(null, 500));
    expect(await logout("csrf")).toMatchObject({
      code: "HTTP_500",
      message: "İstek tamamlanamadı.",
    });

    vi.stubGlobal(
      "fetch",
      reply(
        {
          error: {
            code: "VERSION_CONFLICT",
            message: "The record changed.",
            request_id: "r1",
            timestamp: "2026-11-09T10:00:00Z",
            details: null,
          },
        },
        409,
      ),
    );
    expect(await logout("csrf")).toMatchObject({
      code: "VERSION_CONFLICT",
      message: "The record changed.",
    });
  });

  it("gives the status-page probes the language they are asked for", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
    const english = await fetchLiveness();
    const turkish = await fetchLiveness("tr");
    expect(english).toMatchObject({ ok: false, code: "UNREACHABLE" });
    expect(turkish).toMatchObject({ ok: false, code: "UNREACHABLE" });
    if (!english.ok && !turkish.ok) {
      expect(english.message).toMatch(
        /^Cannot reach the API at .+\. Confirm FastAPI is running\.$/,
      );
      expect(turkish.message).toMatch(
        /adresindeki API'ye ulaşılamıyor\. FastAPI'nin çalıştığını doğrulayın\.$/,
      );
    }
  });
});
