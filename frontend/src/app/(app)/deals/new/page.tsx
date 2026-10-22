import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { DealForm } from "@/components/trade/deal-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
      <div className="mx-auto max-w-[900px] space-y-5">
        <Alert variant="info" title="Read-only access">
          Creating a deal requires <span className="font-mono">trade.write</span> (trader role).
        </Alert>
        <Link href="/deals" className="inline-flex items-center gap-1.5 text-[12px] text-mist-400">
          <ArrowLeft className="size-3.5" aria-hidden />
          Back to deals
        </Link>
      </div>
    );
  }

  const [counterparties, products] = await Promise.all([
    serverGet<CounterpartyList>("/counterparties?limit=100&status=active"),
    serverGet<ProductList>("/products?limit=100&status=active"),
  ]);

  const failure = !counterparties.ok ? counterparties : !products.ok ? products : null;

  return (
    <div className="mx-auto max-w-[1100px] space-y-6">
      <header>
        <Link
          href="/deals"
          className="inline-flex items-center gap-1.5 text-[11.5px] text-mist-500 hover:text-mist-300"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          Deals
        </Link>
        <div className="mt-3 flex items-center gap-3">
          <span className="eyebrow">New deal</span>
          <Badge variant="secondary">DRAFT</Badge>
        </div>
        <h1 className="mt-2 font-display text-[28px] leading-tight tracking-tight text-mist-100">
          Open a trade deal
        </h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-mist-500">
          The deal and its lines are written in one transaction, together with the first history
          entry. A repeated submission reuses the idempotency key and cannot create a duplicate.
        </p>
      </header>

      {failure ? (
        <Alert variant="danger" title="Master data unavailable">
          {failure.message}
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
