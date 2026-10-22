import { Building2, ShieldCheck } from "lucide-react";

import { AccountSummary } from "@/components/auth/account-summary";
import { CompanySwitcher } from "@/components/auth/company-switcher";
import { LogoutButton } from "@/components/auth/logout-button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { loadSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";
export const metadata = { title: "Account" };

const SESSION_POLICY = [
  {
    term: "Idle timeout",
    detail: "30 minutes without activity revokes the session.",
  },
  {
    term: "Absolute timeout",
    detail: "12 hours after sign-in, regardless of activity.",
  },
  {
    term: "Revocation",
    detail: "Removing a membership ends every session bound to that company immediately.",
  },
  {
    term: "Storage",
    detail:
      "The session token lives only in an HttpOnly cookie; nothing is written to localStorage.",
  },
] as const;

export default async function AccountPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { session, memberships } = state.session;
  const company = session.company;

  return (
    <div className="mx-auto max-w-[1280px] space-y-5">
      <PageHeader
        eyebrow="Account"
        meta={
          <Badge variant="success" dot>
            Authenticated
          </Badge>
        }
        title="Profile & access"
        description="Your identity, the companies you may access and the exact permissions carried by the active membership. Permissions are derived from the role on the server, never from the browser."
        actions={<LogoutButton csrfToken={session.csrf_token} />}
      />

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="panel overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
            <div>
              <p className="eyebrow">Identity</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Signed-in profile</h2>
            </div>
            <ShieldCheck className="size-4 text-accent-300" aria-hidden />
          </div>
          <div className="hairline" />
          <div className="p-5">
            <AccountSummary session={state.session} />
          </div>
        </div>

        <div className="panel self-start overflow-hidden">
          <div className="flex items-start justify-between gap-3 px-5 pt-4.5 pb-3">
            <div>
              <p className="eyebrow">Memberships</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Company access</h2>
            </div>
            <Badge variant="secondary">{memberships.length} available</Badge>
          </div>
          <div className="hairline" />
          <div className="p-5">
            <p className="flex items-start gap-2 text-[11px] leading-relaxed text-mist-500">
              <Building2 className="mt-[2px] size-3.5 shrink-0 text-mist-600" aria-hidden />
              Switching company rotates your session token and re-issues the cookie. The previous
              token stops working immediately.
            </p>
            <div className="mt-4">
              <CompanySwitcher
                companies={memberships}
                activeCompanyId={company?.company_id ?? null}
                csrfToken={session.csrf_token}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
          <div>
            <p className="eyebrow">Security</p>
            <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Session policy</h2>
          </div>
          <span className="text-[10.5px] text-mist-600">Enforced by the API, not the browser</span>
        </div>
        <div className="hairline" />
        <dl className="grid gap-px bg-white/[0.05] sm:grid-cols-2 xl:grid-cols-4">
          {SESSION_POLICY.map((item) => (
            <div key={item.term} className="bg-ink-900/70 px-5 py-4">
              <dt className="text-[9.5px] tracking-[0.18em] text-mist-600 uppercase">
                {item.term}
              </dt>
              <dd className="mt-1.5 text-[11.5px] leading-relaxed text-mist-400">{item.detail}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
