import { AiOffice } from "@/components/ai/ai-office";
import { ApiErrorAlert } from "@/components/finance/api-error-alert";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { getServerT, titleFor } from "@/lib/i18n/server";
import type {
  AiConversation,
  AiProposal,
  AiRun,
  AiStatus,
  AiSuggestion,
  AiToolList,
} from "@/lib/ai/types";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("aiPageTitle");

export default async function AiOfficePage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

  const company = state.session.session.company;
  const header = (
    <PageHeader
      eyebrow={t("aiEyebrow")}
      title={t("aiTitle")}
      description={t("aiDescription")}
      meta={
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{t("aiBadgeReadOnly")}</Badge>
          <Badge variant="outline">{t("aiBadgeApproval")}</Badge>
        </div>
      }
    />
  );

  if (!company) {
    return (
      <div className="mx-auto max-w-[1360px] space-y-5">
        {header}
        <ApiErrorAlert
          title={t("aiNoCompanyTitle")}
          failure={{
            code: "NO_COMPANY",
            message: t("aiNoCompanyMessage"),
            requestId: null,
          }}
        />
      </div>
    );
  }

  const [status, tools, suggestions, conversations, proposals, activity] = await Promise.all([
    serverGet<AiStatus>("/ai/status"),
    serverGet<AiToolList>("/ai/tools"),
    serverGet<{ items: AiSuggestion[] }>("/ai/suggestions"),
    serverGet<{ items: AiConversation[] }>("/ai/conversations"),
    serverGet<{ items: AiProposal[] }>("/ai/proposals"),
    serverGet<{ items: AiRun[] }>("/ai/activity"),
  ]);

  if (!status.ok) {
    return (
      <div className="mx-auto max-w-[1360px] space-y-5">
        {header}
        <ApiErrorAlert title={t("aiUnavailableTitle")} failure={status} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      {header}
      {/* Keyed by company: switching company remounts the workspace, so no
          conversation, draft or proposal from another company can linger. */}
      <AiOffice
        key={company.company_id}
        companyName={company.name}
        csrfToken={state.session.session.csrf_token}
        status={status.data}
        tools={tools.ok ? tools.data : null}
        suggestions={suggestions.ok ? suggestions.data.items : []}
        conversations={conversations.ok ? conversations.data.items : []}
        proposals={proposals.ok ? proposals.data.items : []}
        activity={activity.ok ? activity.data.items : []}
      />
    </div>
  );
}
