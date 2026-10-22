import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { DealForm } from "@/components/trade/deal-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { CounterpartyList, ProductList } from "@/lib/trade/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "New deal" };

export default async function NewDealPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const session = state.session.session;
  const canWrite = session.company?.permissions.includes("trade.write") ?? false;

  if (!canWrite) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow="New deal"
          back={{ href: "/deals", label: "Deals" }}
          title="Read-only access"
          description="Creating a deal requires the trade.write permission, granted to the trader role."
        />
        <Alert variant="info" title="Read-only access">
          Ask an administrator for a membership with <span className="font-mono">trade.write</span>{" "}
          to open deals.
        </Alert>
      </div>
    );
  }

  const [counterparties, products] = await Promise.all([
    serverGet<CounterpartyList>("/counterparties?limit=100&status=active"),
    serverGet<ProductList>("/products?limit=100&status=active"),
  ]);

  const failure = !counterparties.ok ? counterparties : !products.ok ? products : null;

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <PageHeader
        eyebrow="New deal"
        back={{ href: "/deals", label: "Deals" }}
        meta={<Badge variant="secondary">DRAFT</Badge>}
        title="Open a trade deal"
        description="The deal and its lines are written in one transaction, together with the first history entry. A repeated submission reuses the idempotency key and cannot create a duplicate."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/deals">
              <ArrowLeft className="size-3.5" aria-hidden />
              Cancel
            </Link>
          </Button>
        }
      />

      {failure ? (
        <Alert variant="danger" title="Master data unavailable">
          {failure.message}
          {failure.requestId ? (
            <span className="ml-1 font-mono text-[11px]">({failure.requestId})</span>
          ) : null}
        </Alert>
      ) : (
        <DealForm
          counterparties={counterparties.ok ? counterparties.data.items : []}
          products={products.ok ? products.data.items : []}
          csrfToken={session.csrf_token}
          defaultCurrency={session.company?.default_currency ?? "USD"}
        />
      )}
    </div>
  );
}
