import { beforeEach, describe, expect, it, vi } from "vitest";

import { getServerT, titleFor, titleForNav } from "./server";

const cookie = vi.hoisted(() => ({ value: undefined as string | undefined }));

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "touche_locale" && cookie.value ? { name, value: cookie.value } : undefined,
  }),
}));

beforeEach(() => {
  cookie.value = undefined;
});

describe("tab titles follow the language cookie", () => {
  it("is English until Turkish is chosen", async () => {
    expect(await titleFor("acctPageTitle")).toEqual({ title: "Account" });
    expect(await titleForNav("Deals")).toEqual({ title: "Deals" });
    expect((await getServerT()).locale).toBe("en");
  });

  it("is Turkish when the cookie says so", async () => {
    cookie.value = "tr";
    expect(await titleFor("acctPageTitle")).toEqual({ title: "Hesap" });
    expect(await titleFor("stPageTitle")).toEqual({ title: "Sistem durumu" });
    expect(await titleFor("loginTitle")).toEqual({ title: "Giriş yap" });
    expect(await titleForNav("Command Center")).toEqual({ title: "Yönetim paneli" });
    expect(await titleForNav("Sales orders")).toEqual({ title: "Satış siparişleri" });
  });

  it("falls back to English for a cookie it does not know, and shows an unknown label as is", async () => {
    cookie.value = "de";
    expect(await titleFor("acctPageTitle")).toEqual({ title: "Account" });
    cookie.value = "tr";
    expect(await titleForNav("Something new")).toEqual({ title: "Something new" });
  });
});
