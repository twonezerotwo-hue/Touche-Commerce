import { describe, expect, it } from "vitest";

import { NAV_GROUPS, PUBLIC_NAV_ITEMS } from "../navigation";
import { localizeNavigation } from "./navigation-labels";

describe("Stage 12A localized route chrome", () => {
  it("translates known Turkish navigation labels without changing stable English route metadata", () => {
    expect(localizeNavigation("tr", "Trade core")).toBe("Ticaret yönetimi");
    expect(localizeNavigation("tr", "Sales orders")).toBe("Satış siparişleri");
    expect(localizeNavigation("tr", "FX snapshots")).toBe("Döviz kuru kayıtları");
    expect(localizeNavigation("tr", "System status")).toBe("Sistem durumu");
    expect(localizeNavigation("en", "Sales orders")).toBe("Sales orders");
    expect(NAV_GROUPS[0].items[0].href).toBe("/");
  });

  it("has Turkish labels for all current navigation items and groups except neutral acronyms", () => {
    const allowedSame = new Set(["AI", "CRM"]);
    for (const group of NAV_GROUPS) {
      if (!allowedSame.has(group.label)) {
        expect(localizeNavigation("tr", group.label)).not.toBe(group.label);
      }
      for (const item of group.items) {
        if (!allowedSame.has(item.label)) {
          expect(localizeNavigation("tr", item.label)).not.toBe(item.label);
        }
      }
    }
    for (const item of PUBLIC_NAV_ITEMS) {
      expect(localizeNavigation("tr", item.label)).not.toBe(item.label);
    }
  });

  it("never mutates or creates an unknown navigation label", () => {
    expect(localizeNavigation("tr", "Unknown custom record")).toBe("Unknown custom record");
  });
});
