import Link from "next/link";

import { CommunicationPreflight } from "@/components/communications/preflight";
import { SuppressionPanel } from "@/components/communications/suppression-panel";
import { ApiErrorAlert } from "@/components/finance/api-error-alert";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import type { components } from "@/lib/api/schema";
import { loadSession } from "@/lib/auth/session";
import { getServerT, titleFor } from "@/lib/i18n/server";
import { draftKindLabel } from "@/lib/ai/format";
import { formatDate } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("commPageTitle");

type Channel = {
  channel: "EMAIL" | "WHATSAPP_BUSINESS";
  state: "NOT_CONFIGURED";
  can_send: false;
};

type CommunicationsStatus = {
  mode: "DRAFT_ONLY";
  external_sending_enabled: false;
  can_review_drafts: boolean;
  can_manage_suppressions: boolean;
  channels: Channel[];
};

type Draft = {
  id: string;
  title: string;
  body: string;
  draft_kind: string;
  status: "PROPOSED" | "APPROVED" | "REJECTED";
  created_at: string;
  version: number;
  sent: false;
  source_href: "/ai";
};

type DraftList = {
  items: Draft[];
  truncated: boolean;
  source: "AI_OFFICE";
};

export default async function CommunicationsPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();

  const header = (
    <PageHeader
      eyebrow={t("commEyebrow")}
      title={t("commTitle")}
      description={t("commDescription")}
      meta={<Badge variant="secondary">{t("commBadge")}</Badge>}
    />
  );

  const [status, drafts, contacts] = await Promise.all([
    serverGet<CommunicationsStatus>("/communications/status"),
    serverGet<DraftList>("/communications/drafts?limit=20"),
    serverGet<components["schemas"]["CounterpartyListResponse"]>(
      "/counterparties?status=active&limit=50",
    ),
  ]);

  const suppressions =
    status.ok && status.data.can_manage_suppressions
      ? await serverGet<components["schemas"]["SuppressionListResponse"]>(
          "/communications/suppressions?limit=50",
        )
      : null;

  return (
    <div className="mx-auto max-w-[1360px] space-y-6">
      {header}
      {!status.ok ? (
        <ApiErrorAlert title={t("commUnavailable")} failure={status} />
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2" aria-label={t("commChannelsAria")}>
            {status.data.channels.map((channel) => (
              <div
                key={channel.channel}
                className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="font-semibold text-white">
                    {channel.channel === "EMAIL" ? t("commEmail") : t("commWhatsApp")}
                  </h2>
                  <Badge variant="outline">{t("commNotConnected")}</Badge>
                </div>
                <p className="mt-3 text-sm text-mist-500">{t("commSendingDisabled")}</p>
              </div>
            ))}
          </section>
          {status.data.can_manage_suppressions && suppressions ? (
            suppressions.ok ? (
              <SuppressionPanel
                csrfToken={state.session.session.csrf_token}
                counterparties={
                  contacts.ok
                    ? contacts.data.items.map((item) => ({
                        id: item.id,
                        name: item.name,
                      }))
                    : []
                }
                saved={suppressions.data.items}
              />
            ) : (
              <ApiErrorAlert title={t("commLedgerUnavailable")} failure={suppressions} />
            )
          ) : null}
          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">{t("commPrepared")}</h2>
                <p className="mt-1 text-sm text-mist-500">{t("commPreparedBody")}</p>
              </div>
              <Link
                href="/ai"
                className="text-sm font-medium text-sky-300 underline underline-offset-4 hover:text-sky-200"
              >
                {t("commOpenAi")}
              </Link>
            </div>
            {!contacts.ok && status.data.can_review_drafts ? (
              <p className="mt-3 text-sm text-mist-300">{t("commCrmUnavailable")}</p>
            ) : null}
            {contacts.ok && contacts.data.has_more ? (
              <p className="mt-3 text-sm text-mist-300">{t("commCrmTruncated")}</p>
            ) : null}
            {!drafts.ok ? (
              <div className="mt-4">
                <ApiErrorAlert title={t("commDraftsUnavailable")} failure={drafts} />
              </div>
            ) : drafts.data.items.length === 0 ? (
              <p className="mt-5 text-sm text-mist-500">{t("commNoDrafts")}</p>
            ) : (
              <ul className="mt-5 space-y-3">
                {drafts.data.items.map((draft) => (
                  <li key={draft.id} className="rounded-xl border border-white/10 bg-black/10 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-medium text-white">{draft.title}</h3>
                      <Badge variant="outline">
                        {draft.status === "APPROVED" ? t("commReviewed") : draft.status}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-mist-500">
                      {draftKindLabel(t, draft.draft_kind)} · {formatDate(draft.created_at, locale)}
                    </p>
                    <p className="mt-3 whitespace-pre-wrap break-words text-sm text-mist-500">
                      {draft.body}
                    </p>
                    <p className="mt-3 text-xs font-medium text-mist-500">
                      {t("commNeverTransmitted")}
                    </p>
                    {status.data.can_review_drafts ? (
                      <CommunicationPreflight
                        draftId={draft.id}
                        draftVersion={draft.version}
                        csrfToken={state.session.session.csrf_token}
                        counterparties={
                          contacts.ok
                            ? contacts.data.items.map((item) => ({ id: item.id, name: item.name }))
                            : []
                        }
                      />
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
            {drafts.ok && drafts.data.truncated ? (
              <p className="mt-3 text-sm text-mist-500">{t("commTruncated")}</p>
            ) : null}
          </section>
        </>
      )}
    </div>
  );
}
