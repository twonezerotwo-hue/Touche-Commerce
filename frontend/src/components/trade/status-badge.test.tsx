import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DealStatusBadge } from "./status-badge";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import type { DealStatus } from "@/lib/trade/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const ALL: DealStatus[] = ["DRAFT", "OPEN", "NEGOTIATION", "WON", "LOST", "CANCELLED"];

describe("DealStatusBadge", () => {
  it("shows the stored status in English by default", () => {
    render(
      <>
        {ALL.map((status) => (
          <DealStatusBadge key={status} status={status} />
        ))}
      </>,
    );
    for (const word of ["Draft", "Open", "Negotiation", "Won", "Lost", "Cancelled"]) {
      expect(screen.getByText(word)).toBeInTheDocument();
    }
  });

  it("shows every status in Turkish", () => {
    render(
      <LocaleProvider initialLocale="tr">
        {ALL.map((status) => (
          <DealStatusBadge key={status} status={status} />
        ))}
      </LocaleProvider>,
    );
    for (const word of ["Taslak", "Açık", "Görüşmede", "Kazanıldı", "Kaybedildi", "İptal edildi"]) {
      expect(screen.getByText(word)).toBeInTheDocument();
    }
  });
});
