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
import type { FxRateList } from "@/lib/sourcing/types";
import { formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "FX snapshots" };

export default async function FxRatesPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const canWrite = state.session.session.company?.permissions.includes("trade.write") ?? false;

  const result = await serverGet<FxRateList>("/fx-rates?limit=50");

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <PageHeader
        eyebrow="Sourcing"
        meta={<Badge variant="secondary">FX</Badge>}
        title="FX snapshots"
        description="Recorded observations only. Every converted price points at one of these rows, which is what makes a landed cost reproducible months later."
      />

      {canWrite ? (
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Record a rate</CardTitle>
              <CardDescription>
                The pair and effective time are unique per company; recording the same observation
                twice is rejected rather than silently duplicated.
              </CardDescription>
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
            <CardTitle>Recent snapshots</CardTitle>
            <CardDescription>Newest recording first.</CardDescription>
          </CardHeading>
        </CardHeader>
        <CardContent>
          {!result.ok ? (
            <Alert variant="danger" title="FX snapshots unavailable">
              {result.message}
            </Alert>
          ) : result.data.items.length === 0 ? (
            <p className="text-[11.5px] text-mist-600">
              No snapshots yet. Cross-currency pricing will be blocked until one exists.
            </p>
          ) : (
            <Table bare>
              <TableHeader>
                <TableRow>
                  <TableHead>Pair</TableHead>
                  <TableHead className="text-right">Rate</TableHead>
                  <TableHead>Effective</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="text-right">Recorded</TableHead>
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
                      {formatTimestamp(rate.effective_at)}
                    </TableCell>
                    <TableCell className="max-w-[260px] truncate text-[11.5px] text-mist-400">
                      {rate.source}
                    </TableCell>
                    <TableCell className="text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                      {formatTimestamp(rate.recorded_at)}
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
