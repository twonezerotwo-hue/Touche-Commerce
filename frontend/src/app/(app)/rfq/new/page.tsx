import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { RfqForm } from "@/components/sourcing/rfq-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { CounterpartyList, DealList, ProductList } from "@/lib/trade/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "New RFQ" };

export default async function NewRfqPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const session = state.session.session;
  const canWrite = session.company?.permissions.includes("trade.write") ?? false;

  if (!canWrite) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow="New RFQ"
          back={{ href: "/rfq", label: "RFQs" }}
          title="Read-only access"
          description="Creating an RFQ requires the trade.write permission."
        />
        <Alert variant="info" title="Read-only access">
          Ask an administrator for a membership with <span className="font-mono">trade.write</span>{" "}
          to request supplier quotes.
        </Alert>
      </div>
    );
  }

  const [deals, counterparties, products] = await Promise.all([
    serverGet<DealList>("/deals?limit=100"),
    serverGet<CounterpartyList>("/counterparties?limit=100&status=active"),
    serverGet<ProductList>("/products?limit=100&status=active"),
  ]);

  const failure = !deals.ok
    ? deals
    : !counterparties.ok
      ? counterparties
      : !products.ok
        ? products
        : null;
  const suppliers = counterparties.ok
    ? counterparties.data.items.filter((item) => item.type !== "buyer")
    : [];

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <PageHeader
        eyebrow="New RFQ"
        back={{ href: "/rfq", label: "RFQs" }}
        meta={<Badge variant="secondary">DRAFT</Badge>}
        title="Request supplier quotes"
        description="Select the suppliers to ask; the backend creates one RFQ per supplier in a single transaction. The request is created as a draft and is not sent by this action."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/rfq">
              <ArrowLeft className="size-3.5" aria-hidden />
              Cancel
            </Link>
          </Button>
        }
      />

      {failure ? (
        <Alert variant="danger" title="Master data unavailable">
          {failure.message}
        </Alert>
      ) : (
        <RfqForm
          deals={deals.ok ? deals.data.items : []}
          suppliers={suppliers}
          products={products.ok ? products.data.items : []}
          csrfToken={session.csrf_token}
          defaultCurrency={session.company?.default_currency ?? "USD"}
        />
      )}
    </div>
  );
}
