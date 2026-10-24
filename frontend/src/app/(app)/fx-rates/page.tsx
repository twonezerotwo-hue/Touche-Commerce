import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
} from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { FxRateForm } from "@/components/sourcing/fx-form";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { getServerT, titleFor } from "@/lib/i18n/server";
import type { FxRateList } from "@/lib/sourcing/types";
import { formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("fxTitle");

export default async function FxRatesPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();
  const canWrite = state.session.session.company?.permissions.includes("trade.write") ?? false;

  const result = await serverGet<FxRateList>("/fx-rates?limit=50");

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <PageHeader
        eyebrow={t("srcEyebrow")}
        meta={<Badge variant="secondary">{t("fxBadge")}</Badge>}
        title={t("fxTitle")}
        description={t("fxDescription")}
      />

      {canWrite ? (
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>{t("fxRecordRate")}</CardTitle>
              <CardDescription>{t("fxRecordRateHint")}</CardDescription>
            </CardHeading>
          </CardHeader>
          <CardContent>
            <FxRateForm csrfToken={state.session.session.csrf_token} />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>{t("fxRecent")}</CardTitle>
            <CardDescription>{t("fxRecentHint")}</CardDescription>
          </CardHeading>
        </CardHeader>
        <CardContent>
          {!result.ok ? (
            <Alert variant="danger" title={t("fxUnavailable")}>
              {result.message}
            </Alert>
          ) : result.data.items.length === 0 ? (
            <p className="text-[11.5px] text-mist-600">{t("fxNone")}</p>
          ) : (
            <Table bare>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("srcColPair")}</TableHead>
                  <TableHead className="text-right">{t("srcColRate")}</TableHead>
                  <TableHead>{t("srcColEffective")}</TableHead>
                  <TableHead>{t("srcColSource")}</TableHead>
                  <TableHead className="text-right">{t("srcColRecorded")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.data.items.map((rate) => (
                  <TableRow key={rate.id}>
                    <TableCell className="font-mono text-[11.5px] text-mist-100">
                      {rate.base_currency}/{rate.quote_currency}
                    </TableCell>
                    <TableCell className="data-value text-right text-[12px] text-mist-200">
                      {rate.rate}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-[11.5px] text-mist-400">
                      {formatTimestamp(rate.effective_at, locale)}
                    </TableCell>
                    <TableCell className="max-w-[260px] truncate text-[11.5px] text-mist-400">
                      {rate.source}
                    </TableCell>
                    <TableCell className="text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                      {formatTimestamp(rate.recorded_at, locale)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
