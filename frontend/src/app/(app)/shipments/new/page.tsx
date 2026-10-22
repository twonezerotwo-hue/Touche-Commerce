import { ShipmentPlanForm, type PlannableOrder } from "@/components/operations/shipment-plan-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { FulfilmentSummary, SalesOrderList } from "@/lib/operations/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Plan shipment" };

export default async function NewShipmentPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const permissions = state.session.session.company?.permissions ?? [];
  const canWrite = permissions.includes("trade.write");

  const [confirmed, inFulfillment] = await Promise.all([
    serverGet<SalesOrderList>("/sales-orders?status=CONFIRMED&limit=10"),
    serverGet<SalesOrderList>("/sales-orders?status=IN_FULFILLMENT&limit=10"),
  ]);

  const orders = [
    ...(confirmed.ok ? confirmed.data.items : []),
    ...(inFulfillment.ok ? inFulfillment.data.items : []),
  ].slice(0, 10);

  const fulfilments = await Promise.all(
    orders.map((order) => serverGet<FulfilmentSummary>(`/sales-orders/${order.id}/fulfilment`)),
  );

  const plannable: PlannableOrder[] = orders
    .map((order, index) => {
      const fulfilment = fulfilments[index];
      if (!fulfilment.ok) return null;
      return {
        id: order.id,
        order_number: order.order_number,
        customer_name: order.customer_name,
        currency: order.currency,
        lines: fulfilment.data.lines.map((line) => ({
          id: line.sales_order_item_id,
          sku: line.sku,
          description: "",
          unit: line.unit,
          ordered: line.ordered,
          allocated: line.allocated,
          delivered: line.delivered,
          remaining: line.remaining,
        })),
      } satisfies PlannableOrder;
    })
    .filter((value): value is PlannableOrder => value !== null);

  return (
    <div className="mx-auto max-w-[1000px] space-y-5">
      <PageHeader
        eyebrow="Logistics"
        back={{ href: "/shipments", label: "Shipments" }}
        meta={<Badge variant="secondary">Partial shipments supported</Badge>}
        title="Plan a shipment"
        description="Allocate quantities from one confirmed order. The API refuses any line above the unallocated quantity, so a 5-tonne shipment can never mark a 20-tonne order delivered."
      />

      {!confirmed.ok || !inFulfillment.ok ? (
        <Alert variant="danger" title="Orders unavailable">
          {!confirmed.ok ? confirmed.message : !inFulfillment.ok ? inFulfillment.message : null}
        </Alert>
      ) : null}

      <div className="panel p-4">
        <ShipmentPlanForm
          orders={plannable}
          csrfToken={state.session.session.csrf_token}
          canWrite={canWrite}
        />
      </div>
    </div>
  );
}
