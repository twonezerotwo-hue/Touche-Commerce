import { AccountSummary } from "@/components/auth/account-summary";
import { CompanySwitcher } from "@/components/auth/company-switcher";
import { LogoutButton } from "@/components/auth/logout-button";
import { Badge } from "@/components/ui/badge";
import { loadSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";
export const metadata = { title: "Account" };

export default async function AccountPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { session, memberships } = state.session;
  const company = session.company;

  return (
    <div className="mx-auto max-w-[1100px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="eyebrow">Account</span>
            <Badge variant="secondary">Stage 1A</Badge>
          </div>
          <h1 className="mt-3 font-display text-[28px] leading-tight tracking-tight text-mist-100">
            Profile &amp; access
          </h1>
          <p className="mt-2 max-w-xl text-[13px] leading-relaxed text-mist-500">
            Your identity, the companies you may access and the exact permissions carried by the
            active membership. Permissions are derived from the role on the server, never from the
            browser.
          </p>
        </div>
        <LogoutButton csrfToken={session.csrf_token} />
      </header>

      <section className="panel rounded-xl p-6">
        <AccountSummary session={state.session} />
      </section>

      <section className="panel rounded-xl p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <span className="eyebrow">Memberships</span>
            <h2 className="mt-2 font-display text-lg text-mist-100">Company access</h2>
          </div>
          <Badge variant="secondary">{memberships.length} available</Badge>
        </div>
        <p className="mt-2 max-w-2xl text-[12px] leading-relaxed text-mist-500">
          Switching company rotates your session token and re-issues the cookie. The previous token
          stops working immediately.
        </p>
        <div className="rule my-5" />
        <CompanySwitcher
          companies={memberships}
          activeCompanyId={company?.company_id ?? null}
          csrfToken={session.csrf_token}
        />
      </section>

      <section className="panel rounded-xl p-6">
        <span className="eyebrow">Session policy</span>
        <dl className="mt-3 grid gap-3 text-[12px] text-mist-400 sm:grid-cols-2">
          <div>
            <dt className="text-[10px] uppercase tracking-[0.16em] text-mist-600">Idle timeout</dt>
            <dd className="mt-1">30 minutes without activity revokes the session.</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-[0.16em] text-mist-600">
              Absolute timeout
            </dt>
            <dd className="mt-1">12 hours after sign-in, regardless of activity.</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-[0.16em] text-mist-600">Revocation</dt>
            <dd className="mt-1">
              Removing a membership ends every session bound to that company immediately.
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-[0.16em] text-mist-600">Storage</dt>
            <dd className="mt-1">
              The session token lives only in an HttpOnly cookie; nothing is written to
              localStorage.
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
