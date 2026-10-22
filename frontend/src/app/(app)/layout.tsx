import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { SessionUnavailable } from "@/components/auth/session-unavailable";
import { AppSidebar } from "@/components/shell/app-sidebar";
import { TopBar } from "@/components/shell/top-bar";
import { resolveRoute } from "@/lib/auth/guard";
import { loadSession } from "@/lib/auth/session";

// The session must be re-validated on every request; never prerender this shell.
export const dynamic = "force-dynamic";

export default async function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  const state = await loadSession();
  const pathname = (await headers()).get("x-pathname") ?? "/";
  const decision = resolveRoute(state, pathname);
  if (decision.redirectTo) redirect(decision.redirectTo);

  if (state.status === "unavailable") {
    return (
      <main className="relative min-h-screen px-6 py-10">
        <SessionUnavailable message={state.message} />
      </main>
    );
  }

  if (state.status !== "authenticated") {
    // resolveRoute() redirects anonymous visitors; this is a defensive guard.
    return null;
  }

  const { user, session } = state.session;
  const company = session.company;

  const identity = {
    displayName: user.display_name,
    email: user.email,
    companyName: company?.name ?? null,
    role: company?.role ?? null,
  };

  return (
    <div className="app-canvas relative flex min-h-screen">
      <div className="hairline-grid pointer-events-none absolute inset-0 opacity-70" aria-hidden />
      <AppSidebar identity={identity} />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <TopBar identity={identity} />
        <main className="flex-1 px-4 py-7 sm:px-6 lg:px-10 lg:py-9">{children}</main>
        <footer className="border-t border-white/[0.06] px-4 py-4 sm:px-6 lg:px-10">
          <div className="mx-auto flex max-w-[1360px] flex-wrap items-center justify-between gap-2 text-[9.5px] tracking-[0.18em] text-mist-600 uppercase">
            <span>TOUCHE COMMERCE · Internal trade platform</span>
            <span>Stage 2 · Premium commerce interface</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
