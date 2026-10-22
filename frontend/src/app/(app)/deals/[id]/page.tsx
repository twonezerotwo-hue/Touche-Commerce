import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, History } from "lucide-react";

import { DealEditForm } from "@/components/trade/deal-edit-form";
import { DealStatusBadge } from "@/components/trade/status-badge";
import { TransitionPanel } from "@/components/trade/transition-panel";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { formatDate, formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";
import type { Deal } from "@/lib/trade/types";

export const dynamic = "force-dynamic";

export default async function DealDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { id } = await params;
  const result = await serverGet<Deal>(`/deals/${id}`);
  if (!result.ok) {
    if (result.code === "NOT_FOUND") notFound();
    return (
      <div className="mx-auto max-w-[1100px] space-y-4">
        <Link href="/deals" className="text-[11.5px] text-mist-500 hover:text-mist-300">
          Back to deals
        </Link>
        <Alert variant="danger" title="Deal unavailable">
          {result.message}
        </Alert>
      </div>
    );
  }

  const deal = result.data;
  const session = state.session.session;
  const canWrite = session.company?.permissions.includes("trade.write") ?? false;

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <header>
        <Link
          href="/deals"
          className="inline-flex items-center gap-1.5 text-[11.5px] text-mist-500 hover:text-mist-300"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          Deals
        </Link>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-[11.5px] tracking-[0.08em] text-gold-300">
                {deal.reference}
              </span>
              <DealStatusBadge status={deal.status} />
              <Badge variant="outline" className="font-mono">
                ETag v{deal.version}
              </Badge>
            </div>
            <h1 className="mt-2 font-display text-[28px] leading-tight tracking-tight text-mist-100">
              {deal.title}
            </h1>
            <p className="mt-2 text-[12.5px] text-mist-500">
              {deal.counterparty_name} · {formatMoney(deal.total_value, deal.currency)} · expected
              close {formatDate(deal.expected_close_date)}
            </p>
          </div>
        </div>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="panel rounded-xl p-4">
          <p className="text-[10px] uppercase tracking-[0.16em] text-mist-600">Deal value</p>
          <p className="mt-1 font-display text-xl text-mist-100">
            {formatMoney(deal.total_value, deal.currency)}
          </p>
        </div>
        <div className="panel rounded-xl p-4">
          <p className="text-[10px] uppercase tracking-[0.16em] text-mist-600">Lines</p>
          <p className="mt-1 font-display text-xl text-mist-100">{deal.items.length}</p>
        </div>
        <div className="panel rounded-xl p-4">
          <p className="text-[10px] uppercase tracking-[0.16em] text-mist-600">Version</p>
          <p className="mt-1 font-display text-xl text-mist-100">{deal.version}</p>
        </div>
        <div className="panel rounded-xl p-4">
          <p className="text-[10px] uppercase tracking-[0.16em] text-mist-600">Created</p>
          <p className="mt-1 text-[12.5px] text-mist-200">{formatTimestamp(deal.created_at)}</p>
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <div className="panel rounded-xl p-6">
            <span className="eyebrow">Lines</span>
            <div className="mt-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Unit price</TableHead>
                    <TableHead className="text-right">Line total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deal.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <span className="block text-mist-100">{item.name}</span>
                        <span className="mt-0.5 block font-mono text-[11px] text-mist-600">
                          {item.sku}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        {formatQuantity(item.quantity, item.unit)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatMoney(item.unit_price, deal.currency)}
                      </TableCell>
                      <TableCell className="text-right text-mist-100">
                        {formatMoney(item.line_total, deal.currency)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {deal.notes ? (
              <p className="mt-4 text-[12px] leading-relaxed text-mist-500">{deal.notes}</p>
            ) : null}
          </div>

          <div className="panel rounded-xl p-6">
            <span className="eyebrow">Status transitions</span>
            <div className="mt-4">
              <TransitionPanel deal={deal} csrfToken={session.csrf_token} canWrite={canWrite} />
            </div>
          </div>

          <div className="panel rounded-xl p-6">
            <span className="eyebrow">Edit header</span>
            <div className="mt-4">
              <DealEditForm deal={deal} csrfToken={session.csrf_token} canWrite={canWrite} />
            </div>
          </div>
        </div>

        <aside className="panel h-fit rounded-xl p-6">
          <div className="flex items-center gap-2">
            <History className="size-4 text-gold-400" aria-hidden />
            <span className="eyebrow">History</span>
          </div>
          <ol className="mt-4 space-y-4">
            {deal.transitions.map((transition) => (
              <li key={transition.id} className="relative border-l border-white/10 pl-4">
                <span
                  className="absolute -left-[3px] top-1.5 size-[5px] rounded-full bg-gold-400"
                  aria-hidden
                />
                <p className="text-[12.5px] text-mist-200">
                  {transition.from_status ? `${transition.from_status} → ` : "Created · "}
                  <span className="text-mist-100">{transition.to_status}</span>
                </p>
                {transition.reason ? (
                  <p className="mt-1 text-[11.5px] leading-relaxed text-mist-500">
                    “{transition.reason}”
                  </p>
                ) : null}
                <p className="mt-1 font-mono text-[10.5px] text-mist-600">
                  v{transition.version_after} · {formatTimestamp(transition.occurred_at)}
                </p>
              </li>
            ))}
          </ol>
        </aside>
      </section>
    </div>
  );
}
