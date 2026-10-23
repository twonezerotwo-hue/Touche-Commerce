import Link from "next/link";

import { CommunicationPreflight } from "@/components/communications/preflight";
import { ApiErrorAlert } from "@/components/finance/api-error-alert";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import type { components } from "@/lib/api/schema";
import { loadSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";
export const metadata = { title: "Communications" };

type Channel = {
  channel: "EMAIL" | "WHATSAPP_BUSINESS";
  state: "NOT_CONFIGURED";
  can_send: false;
};

type CommunicationsStatus = {
  mode: "DRAFT_ONLY";
  external_sending_enabled: false;
  can_review_drafts: boolean;
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

  const header = (
    <PageHeader
      eyebrow="Stage 7C · Communications"
      title="Communications"
      description="Review AI-prepared business correspondence. External email and WhatsApp sending are not connected or enabled."
      meta={<Badge variant="secondary">Draft-only · No messages sent</Badge>}
    />
  );

  const [status, drafts, contacts] = await Promise.all([
    serverGet<CommunicationsStatus>("/communications/status"),
    serverGet<DraftList>("/communications/drafts?limit=20"),
    serverGet<components["schemas"]["CounterpartyListResponse"]>(
      "/counterparties?status=active&limit=50",
    ),
  ]);

  return (
    <div className="mx-auto max-w-[1360px] space-y-6">
      {header}
      {!status.ok ? (
        <ApiErrorAlert title="Communications unavailable" failure={status} />
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-2" aria-label="Channel availability">
            {status.data.channels.map((channel) => (
              <div
                key={channel.channel}
                className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="font-semibold text-white">
                    {channel.channel === "EMAIL" ? "Email" : "WhatsApp Business"}
                  </h2>
                  <Badge variant="outline">Not connected</Badge>
                </div>
                <p className="mt-3 text-sm text-mist-500">
                  Sending is disabled. No external provider credentials or conversation data are
                  used.
                </p>
              </div>
            ))}
          </section>
          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">Prepared correspondence</h2>
                <p className="mt-1 text-sm text-mist-500">
                  Existing AI Office drafts are shown for the selected company. Approval means
                  reviewed, not sent. CRM matching is not proof of consent.
                </p>
              </div>
              <Link
                href="/ai"
                className="text-sm font-medium text-sky-300 underline underline-offset-4 hover:text-sky-200"
              >
                Open AI Office
              </Link>
            </div>
            {!contacts.ok && status.data.can_review_drafts ? (
              <p className="mt-3 text-sm text-mist-300">CRM records are unavailable; recipient readiness will remain blocked.</p>
            ) : null}
            {contacts.ok && contacts.data.has_more ? (
              <p className="mt-3 text-sm text-mist-300">Showing the latest 50 active CRM records. Use CRM to locate older contacts.</p>
            ) : null}
            {!drafts.ok ? (
              <div className="mt-4">
                <ApiErrorAlert title="Drafts unavailable" failure={drafts} />
              </div>
            ) : drafts.data.items.length === 0 ? (
              <p className="mt-5 text-sm text-mist-500">
                No correspondence drafts yet. Create a supplier follow-up or RFQ draft in the AI
                Office.
              </p>
            ) : (
              <ul className="mt-5 space-y-3">
                {drafts.data.items.map((draft) => (
                  <li key={draft.id} className="rounded-xl border border-white/10 bg-black/10 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-medium text-white">{draft.title}</h3>
                      <Badge variant="outline">
                        {draft.status === "APPROVED" ? "Reviewed · Not sent" : draft.status}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-mist-500">
                      {draft.draft_kind} · {new Date(draft.created_at).toLocaleDateString("en-GB")}
                    </p>
                    <p className="mt-3 whitespace-pre-wrap break-words text-sm text-mist-500">
                      {draft.body}
                    </p>
                    <p className="mt-3 text-xs font-medium text-mist-500">Never transmitted</p>
                    {status.data.can_review_drafts ? (
                      <CommunicationPreflight
                        draftId={draft.id}
                        draftVersion={draft.version}
                        csrfToken={state.session.session.csrf_token}
                        counterparties={contacts.ok ? contacts.data.items.map((item) => ({ id: item.id, name: item.name })) : []}
                      />
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
            {drafts.ok && drafts.data.truncated ? (
              <p className="mt-3 text-sm text-mist-500">
                Only the most recent 20 drafts are shown.
              </p>
            ) : null}
          </section>
        </>
      )}
    </div>
  );
}
