import { redirect } from "next/navigation";
import { Building2 } from "lucide-react";

import { CompanySwitcher } from "@/components/auth/company-switcher";
import { LogoutButton } from "@/components/auth/logout-button";
import { SessionUnavailable } from "@/components/auth/session-unavailable";
import { Badge } from "@/components/ui/badge";
import { resolveRoute } from "@/lib/auth/guard";
import { loadSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";
export const metadata = { title: "Select company" };

export default async function SelectCompanyPage() {
  const state = await loadSession();
  const decision = resolveRoute(state, "/select-company");
  if (decision.redirectTo) redirect(decision.redirectTo);

  if (state.status === "unavailable") {
    return <SessionUnavailable message={state.message} />;
  }
  if (state.status !== "authenticated") return null;

  const { user, session, memberships } = state.session;

  return (
    <div className="panel rounded-xl p-7">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="eyebrow">Workspace</span>
          <h2 className="mt-2 font-display text-[25px] leading-tight tracking-tight text-mist-100">
            Choose a company
          </h2>
        </div>
        <Badge variant="secondary">
          <Building2 className="size-3" aria-hidden />
          {memberships.length} available
        </Badge>
      </div>

      <p className="mt-2 text-[12.5px] leading-relaxed text-mist-500">
        Signed in as <span className="text-mist-200">{user.display_name}</span> ({user.email}).
        Sessions are bound to one company at a time; switching rotates your session token.
      </p>

      <div className="rule my-6" />

      <CompanySwitcher
        companies={memberships}
        activeCompanyId={session.company?.company_id ?? null}
        csrfToken={session.csrf_token}
      />

      <div className="rule my-6" />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[60%] text-[11px] leading-relaxed text-mist-600">
          Access is re-checked on every request. If an administrator revokes your membership, the
          session for that company ends immediately.
        </p>
        <LogoutButton csrfToken={session.csrf_token} />
      </div>
    </div>
  );
}
