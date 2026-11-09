import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppError from "@/app/(app)/error";
import { AppSidebar } from "@/components/shell/app-sidebar";
import { TopBar } from "@/components/shell/top-bar";
import { ProbeCard } from "@/components/system-status/probe-card";
import { RefreshButton } from "@/components/system-status/refresh-button";
import type { AuthSession, CompanyAccess } from "@/lib/auth/types";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { translate } from "@/lib/i18n/messages";
import { roleLabel } from "@/lib/i18n/value-labels";
import { NO_DATABASE_CHECK_DETAIL, probeStateLabel } from "@/lib/status";

import { AccountSummary } from "./account-summary";
import { CompanySwitcher } from "./company-switcher";
import { LogoutButton } from "./logout-button";
import { SessionUnavailable } from "./session-unavailable";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/deals",
}));
vi.mock("@/lib/auth/client", () => ({
  switchCompany: vi.fn(),
  logout: vi.fn(),
}));

const inTurkish = (ui: React.ReactElement) =>
  render(<LocaleProvider initialLocale="tr">{ui}</LocaleProvider>);
const tTr = (key: Parameters<typeof translate>[1], params?: Record<string, string | number>) =>
  translate("tr", key, params);

const SESSION: AuthSession = {
  user: {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: "amina@touche.example",
    display_name: "Amina Haddad",
    status: "active",
  },
  session: {
    session_id: "22222222-2222-4222-8222-222222222222",
    company: {
      company_id: "33333333-3333-4333-8333-333333333333",
      name: "TOUCHE Trading",
      country: "GB",
      default_currency: "GBP",
      status: "active",
      role: "approver",
      permissions: ["company.view", "finance.approve"],
    },
    created_at: "2026-10-22T08:00:00Z",
    last_activity_at: "2026-10-22T08:10:00Z",
    idle_expires_at: "2026-10-22T08:40:00Z",
    expires_at: "2026-10-22T20:00:00Z",
    csrf_token: "csrf",
    ip_address: "127.0.0.1",
    user_agent: "vitest",
  },
  memberships: [],
};

function company(overrides: Partial<CompanyAccess>): CompanyAccess {
  return {
    company_id: "c1",
    name: "TOUCHE Trading",
    country: "GB",
    default_currency: "GBP",
    status: "active",
    role: "admin",
    permissions: ["company.view"],
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());

describe("role words", () => {
  it("shows the four roles in Turkish and an unknown role as it was stored", () => {
    expect(roleLabel(tTr, "viewer")).toBe("Görüntüleyici");
    expect(roleLabel(tTr, "trader")).toBe("Ticaret yetkilisi");
    expect(roleLabel(tTr, "approver")).toBe("Onaylayıcı");
    expect(roleLabel(tTr, "admin")).toBe("Yönetici");
    expect(roleLabel(tTr, "auditor")).toBe("auditor");
  });
});

describe("account summary in Turkish", () => {
  it("shows the labels, the role word and the permissions, with the stored values unchanged", () => {
    inTurkish(<AccountSummary session={SESSION} />);
    expect(screen.getByText("Ad")).toBeInTheDocument();
    expect(screen.getByText("Etkin şirketteki rol")).toBeInTheDocument();
    expect(screen.getByText("Onaylayıcı")).toBeInTheDocument();
    expect(screen.getByText("Oturum başlangıcı")).toBeInTheDocument();
    expect(screen.getByText("Bu üyeliğin verdiği yetkiler")).toBeInTheDocument();
    // Stored identifiers and the UTC instant are never translated or shifted.
    expect(screen.getByText("finance.approve")).toBeInTheDocument();
    expect(screen.getByText("amina@touche.example")).toBeInTheDocument();
    expect(screen.getByText("2026-10-22 20:00:00 UTC")).toBeInTheDocument();
    expect(screen.getByText(/Oturum kaynağı: 127\.0\.0\.1 · vitest/)).toBeInTheDocument();
  });

  it("says plainly when no company is selected", () => {
    inTurkish(
      <AccountSummary session={{ ...SESSION, session: { ...SESSION.session, company: null } }} />,
    );
    expect(screen.getByText("Seçilmedi")).toBeInTheDocument();
    expect(screen.getByText("Etkin şirket yok")).toBeInTheDocument();
    expect(
      screen.getByText("Bir şirket seçilene kadar hiçbir yetki geçerli değildir."),
    ).toBeInTheDocument();
  });

  it("keeps the English wording when the language is English", () => {
    render(<AccountSummary session={SESSION} />);
    expect(screen.getByText("Role in active company")).toBeInTheDocument();
    expect(screen.getByText("Approver")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
  });
});

describe("company switcher in Turkish", () => {
  it("marks the current company and names every role", () => {
    inTurkish(
      <CompanySwitcher
        companies={[
          company({ company_id: "c1", role: "admin" }),
          company({ company_id: "c2", name: "Meridian", country: "AE", role: "viewer" }),
        ]}
        activeCompanyId="c1"
        csrfToken="csrf"
      />,
    );
    expect(screen.getByText("Geçerli")).toBeInTheDocument();
    expect(screen.getByText("Seç")).toBeInTheDocument();
    expect(screen.getByText(/GB · GBP · Yönetici/)).toBeInTheDocument();
    expect(screen.getByText(/AE · GBP · Görüntüleyici/)).toBeInTheDocument();
  });

  it("explains an account without any membership", () => {
    inTurkish(<CompanySwitcher companies={[]} activeCompanyId={null} csrfToken="csrf" />);
    expect(screen.getByText("Şirket erişimi yok")).toBeInTheDocument();
    expect(screen.getByText(/Bir yöneticiden erişim vermesini isteyin/)).toBeInTheDocument();
  });
});

describe("sign out and the session states in Turkish", () => {
  it("labels the sign-out button, and a caller-supplied label still wins", () => {
    const { rerender } = inTurkish(<LogoutButton csrfToken="csrf" />);
    expect(screen.getByRole("button", { name: "Çıkış yap" })).toBeInTheDocument();
    rerender(
      <LocaleProvider initialLocale="tr">
        <LogoutButton csrfToken="csrf" label="Bitir" />
      </LocaleProvider>,
    );
    expect(screen.getByRole("button", { name: "Bitir" })).toBeInTheDocument();
  });

  it("does not guess whether the visitor is signed in when the API is down", () => {
    inTurkish(<SessionUnavailable message="Cannot reach the API." />);
    expect(screen.getByText("Oturum kullanılamıyor")).toBeInTheDocument();
    expect(screen.getByText("API yanıt vermedi")).toBeInTheDocument();
    // The API's own message is shown as received.
    expect(screen.getByText("Cannot reach the API.")).toBeInTheDocument();
    expect(screen.getByText("scripts\\dev-backend.ps1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Girişe dön" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Sistem durumu" })).toHaveAttribute("href", "/status");
  });

  it("shows a failed screen with a way to try again and no error detail", async () => {
    const retry = vi.fn();
    const user = userEvent.setup();
    const error = Object.assign(new Error("secret stack detail"), { digest: "abc123" });
    inTurkish(<AppError error={error} retry={retry} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Bu ekranda bir şeyler ters gitti")).toBeInTheDocument();
    expect(screen.getByText("Referans: abc123")).toBeInTheDocument();
    expect(screen.queryByText(/secret stack detail/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Yeniden dene" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});

describe("the status page pieces in Turkish", () => {
  it("shows the three states in words and keeps the state code on the card", () => {
    expect(probeStateLabel(tTr, "operational")).toBe("Çalışıyor");
    expect(probeStateLabel(tTr, "degraded")).toBe("Düşük performans");
    expect(probeStateLabel(tTr, "unreachable")).toBe("Ulaşılamıyor");
    const { container } = inTurkish(
      <ProbeCard
        eyebrow="Hazırlık"
        title="PostgreSQL"
        state="degraded"
        value="connection timeout expired"
        rows={[{ label: "Sunucu", value: "bildirilmedi" }]}
      />,
    );
    expect(screen.getByText("Düşük performans")).toBeInTheDocument();
    expect(container.querySelector('[data-probe-state="degraded"]')).not.toBeNull();
    // What the database said is shown as received.
    expect(screen.getByText("connection timeout expired")).toBeInTheDocument();
  });

  it("translates the one sentence this app writes, not the ones the API writes", () => {
    expect(NO_DATABASE_CHECK_DETAIL).toBe("The readiness response contained no database check.");
    expect(tTr("stNoDbCheck")).toBe("Hazırlık yanıtında veritabanı denetimi yoktu.");
    expect(tTr("stLivenessAnswered", { service: "api", version: "1.0", status: 200 })).toBe(
      "api v1.0 HTTP 200 ile yanıt verdi.",
    );
  });

  it("labels the re-check button", () => {
    inTurkish(<RefreshButton />);
    expect(screen.getByRole("button", { name: "Durumu yeniden denetle" })).toBeInTheDocument();
  });
});

describe("the shell in Turkish", () => {
  const identity = {
    displayName: "Amina Haddad",
    email: "amina@touche.example",
    companyName: "TOUCHE Trading",
    role: "trader",
  };

  it("names the breadcrumb and shows the role as a word", () => {
    inTurkish(<TopBar identity={identity} />);
    expect(screen.getByRole("navigation", { name: "Gezinti yolu" })).toBeInTheDocument();
    expect(screen.getByText("Ticaret yetkilisi")).toBeInTheDocument();
  });

  it("keeps the English wording in English", () => {
    render(<TopBar identity={identity} />);
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
    expect(screen.getByText("trader")).toBeInTheDocument();
  });
});

describe("the sidebar in Turkish", () => {
  const identity = {
    displayName: "Amina Haddad",
    email: "amina@touche.example",
    companyName: "TOUCHE Trading",
    role: "approver",
  };

  it("names the primary navigation and the home link, and shows the role as a word", () => {
    inTurkish(<AppSidebar identity={identity} />);
    expect(screen.getByRole("navigation", { name: "Ana menü" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "TOUCHE COMMERCE — ana sayfa" })).toBeInTheDocument();
    expect(screen.getByText("Onaylayıcı")).toBeInTheDocument();
  });

  it("says when there is no membership, and explains the planned item in Turkish", () => {
    inTurkish(<AppSidebar identity={{ ...identity, role: null, companyName: null }} />);
    expect(screen.getByText("Üyelik yok")).toBeInTheDocument();
    expect(
      screen.getByTitle("Şirket ayarları ve yönetim — Aşama 2 için planlandı"),
    ).toBeInTheDocument();
  });

  it("keeps the English wording in English", () => {
    render(<AppSidebar identity={{ ...identity, role: null }} />);
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByText("No membership")).toBeInTheDocument();
    expect(
      screen.getByTitle("Company settings and administration — planned for Stage 2"),
    ).toBeInTheDocument();
  });
});
