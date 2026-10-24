import { redirect } from "next/navigation";

import { LoginForm } from "@/components/auth/login-form";
import { Badge } from "@/components/ui/badge";
import { resolveRoute } from "@/lib/auth/guard";
import { loadSession } from "@/lib/auth/session";
import { getServerT } from "@/lib/i18n/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const state = await loadSession();
  const decision = resolveRoute(state, "/login");
  if (decision.redirectTo) redirect(decision.redirectTo);

  const { t } = await getServerT();
  const params = await searchParams;
  const nextPath = typeof params.next === "string" ? params.next : "/";

  return (
    <div className="panel rounded-xl p-7">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="eyebrow">{t("loginEyebrow")}</span>
          <h2 className="mt-2 font-display text-[26px] leading-tight tracking-tight text-mist-100">
            {t("loginTitle")}
          </h2>
        </div>
        <Badge variant="secondary">{t("loginBadge")}</Badge>
      </div>
      <p className="mt-2 text-[12.5px] leading-relaxed text-mist-500">{t("loginIntro")}</p>

      <div className="rule my-6" />

      <LoginForm nextPath={nextPath} />
    </div>
  );
}
