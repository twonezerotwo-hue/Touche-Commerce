import { ApiErrorAlert } from "@/components/finance/api-error-alert";
import { ImportWizard } from "@/components/imports/import-wizard";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { getServerT } from "@/lib/i18n/server";
import type { ImportBatchList } from "@/lib/imports/client";
import { formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Import" };

export default async function ImportsPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

  const company = state.session.session.company;
  const canWrite = company?.permissions.includes("trade.write") ?? false;
  const history = await serverGet<ImportBatchList>("/imports");

  return (
    <div className="mx-auto max-w-[1100px] space-y-6">
      <PageHeader
        eyebrow={t("importsEyebrow")}
        title={t("importsTitle")}
        description={t("importsDescription")}
        meta={<Badge variant="outline">trade.write</Badge>}
      />

      <ImportWizard csrfToken={state.session.session.csrf_token} canWrite={canWrite} />

      <section className="space-y-3" aria-label={t("importHistory")}>
        <p className="eyebrow">{t("importHistory")}</p>
        {!history.ok ? (
          <ApiErrorAlert title={t("importFailed")} failure={history} />
        ) : history.data.items.length === 0 ? (
          <p className="panel px-4 py-6 text-[12.5px] text-mist-500">{t("importHistoryEmpty")}</p>
        ) : (
          <div className="panel overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-[12px]">
              <thead className="text-[10.5px] tracking-[0.06em] text-mist-500 uppercase">
                <tr>
                  <th className="px-4 py-2.5 font-medium">{t("importHistoryFile")}</th>
                  <th className="px-4 py-2.5 font-medium">{t("importHistoryKind")}</th>
                  <th className="px-4 py-2.5 text-right font-medium">
                    {t("importHistoryCreated")}
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium">
                    {t("importHistorySkipped")}
                  </th>
                  <th className="px-4 py-2.5 font-medium">{t("importHistoryWhen")}</th>
                </tr>
              </thead>
              <tbody>
                {history.data.items.map((batch) => (
                  <tr key={batch.id} className="border-t border-white/5">
                    <td className="px-4 py-2.5 text-mist-200">{batch.filename}</td>
                    <td className="px-4 py-2.5 text-mist-300">
                      {batch.kind === "products"
                        ? t("importKindProducts")
                        : t("importKindCounterparties")}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-mist-200">
                      {batch.created_rows}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-mist-400">
                      {batch.skipped_rows}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-mist-400">
                      {formatTimestamp(batch.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
