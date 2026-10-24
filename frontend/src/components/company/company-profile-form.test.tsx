import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyProfileForm } from "./company-profile-form";
import * as client from "@/lib/company/client";
import type { CompanyProfile } from "@/lib/company/client";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import type { Locale } from "@/lib/i18n/messages";

vi.mock("@/lib/company/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/company/client")>();
  return { ...original, saveCompanyProfile: vi.fn() };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const mocked = vi.mocked(client);

function profile(overrides: Partial<CompanyProfile> = {}): CompanyProfile {
  return {
    company_id: "22222222-2222-4222-8222-222222222222",
    exists: false,
    legal_name: null,
    tax_office: null,
    tax_number: null,
    address: null,
    city: null,
    postal_code: null,
    phone: null,
    email: null,
    website: null,
    bank_name: null,
    iban: null,
    swift_bic: null,
    missing_essentials: ["legal_name", "tax_number", "address"],
    version: 0,
    updated_at: null,
    ...overrides,
  };
}

function renderForm(canEdit = true, locale: Locale = "en", initial = profile()) {
  return render(
    <LocaleProvider initialLocale={locale}>
      <CompanyProfileForm profile={initial} csrfToken="csrf-token" canEdit={canEdit} />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  mocked.saveCompanyProfile.mockReset();
});

describe("company profile form", () => {
  it("lists what documents are still missing instead of inventing it", () => {
    renderForm();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Still empty on documents: Legal name, Tax number, Address",
    );
  });

  it("is read-only for anyone but an administrator", () => {
    renderForm(false);
    expect(screen.getByText("Only an administrator can change these details.")).toBeVisible();
    expect(screen.getByLabelText("Legal name")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save profile" })).not.toBeInTheDocument();
  });

  it("creates the profile on the first save and then replaces it with the returned version", async () => {
    const saved = profile({
      exists: true,
      legal_name: "Anadolu Ticaret A.Ş.",
      tax_number: "1234567890",
      address: "Örnek Mah. 1",
      missing_essentials: [],
      version: 1,
    });
    mocked.saveCompanyProfile.mockResolvedValueOnce({ ok: true, profile: saved });
    renderForm();

    await userEvent.type(screen.getByLabelText("Legal name"), "Anadolu Ticaret A.Ş.");
    await userEvent.type(screen.getByLabelText("Tax number"), "1234567890");
    await userEvent.type(screen.getByLabelText("Address"), "Örnek Mah. 1");
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(screen.getByText("Profile saved.")).toBeVisible());
    expect(mocked.saveCompanyProfile).toHaveBeenCalledWith(
      expect.objectContaining({
        legal_name: "Anadolu Ticaret A.Ş.",
        tax_number: "1234567890",
        city: null, // blank fields are cleared, not sent as empty strings
      }),
      0,
      "csrf-token",
    );
    expect(screen.getByRole("status")).toHaveTextContent("All details customers expect");

    mocked.saveCompanyProfile.mockResolvedValueOnce({
      ok: true,
      profile: { ...saved, version: 2 },
    });
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => expect(mocked.saveCompanyProfile).toHaveBeenCalledTimes(2));
    expect(mocked.saveCompanyProfile.mock.calls[1]?.[1]).toBe(1); // If-Match uses version 1
  });

  it("explains a concurrent edit and keeps what was typed", async () => {
    mocked.saveCompanyProfile.mockResolvedValueOnce({
      ok: false,
      code: "VERSION_CONFLICT",
      message: "The company profile was modified by another request.",
      conflict: true,
      fields: [],
    });
    renderForm();
    await userEvent.type(screen.getByLabelText("City"), "Ankara");
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Someone else changed the profile");
    expect(screen.getByLabelText("City")).toHaveValue("Ankara");
  });

  it("marks the fields the server rejected", async () => {
    mocked.saveCompanyProfile.mockResolvedValueOnce({
      ok: false,
      code: "VALIDATION_ERROR",
      message: "Request validation failed.",
      conflict: false,
      fields: ["iban"],
    });
    renderForm();
    await userEvent.type(screen.getByLabelText("IBAN"), "GB00");
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() =>
      expect(screen.getByLabelText("IBAN")).toHaveAttribute("aria-invalid", "true"),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Request validation failed. (VALIDATION_ERROR)",
    );
  });

  it("renders in Turkish", () => {
    renderForm(true, "tr");
    expect(screen.getByLabelText("Ticari unvan")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Belgelerde hâlâ boş");
    expect(screen.getByRole("button", { name: "Bilgileri kaydet" })).toBeInTheDocument();
  });
});
