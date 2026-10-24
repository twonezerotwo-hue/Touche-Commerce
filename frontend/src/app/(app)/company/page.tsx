import { ApiErrorAlert } from "@/components/finance/api-error-alert";
import { CompanyProfileForm } from "@/components/company/company-profile-form";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { CompanyProfile } from "@/lib/company/client";
import { getServerT } from "@/lib/i18n/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Company profile" };

export default async function CompanyProfilePage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

  const company = state.session.session.company;
  const canEdit = company?.permissions.includes("settings.manage") ?? false;
  const result = await serverGet<CompanyProfile>("/company/profile");

  return (
    <div className="mx-auto max-w-[900px] space-y-6">
      <PageHeader
        eyebrow={t("profileEyebrow")}
        title={t("profileTitle")}
        description={t("profileDescription")}
        meta={<Badge variant="outline">settings.manage</Badge>}
      />
      {result.ok ? (
        <CompanyProfileForm
          profile={result.data}
          csrfToken={state.session.session.csrf_token}
          canEdit={canEdit}
        />
      ) : (
        <ApiErrorAlert title={t("profileFailed")} failure={result} />
      )}
    </div>
  );
}
