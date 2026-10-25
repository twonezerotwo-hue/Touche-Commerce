"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Loader2, Ship } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useLocale } from "@/lib/i18n/locale-provider";
import { transportModeText } from "@/lib/i18n/value-labels";
import { planShipment } from "@/lib/operations/client";
import { TRANSPORT_MODES, type TransportMode } from "@/lib/operations/types";
import { formatQuantity } from "@/lib/trade/format";

export interface PlannableOrder {
  id: string;
  order_number: string;
  customer_name: string;
  currency: string;
  lines: {
    id: string;
    sku: string;
    description: string;
    unit: string;
    ordered: string;
    allocated: string;
    delivered: string;
    remaining: string;
  }[];
}

/**
 * Plan a (possibly partial) shipment against real order lines.
 *
 * Quantities default to what is still unallocated, and the API independently
 * refuses anything above the outstanding quantity. Leaving a line at zero omits
 * it from this shipment.
 */
export function ShipmentPlanForm({
  orders,
  csrfToken,
  canWrite,
}: {
  orders: PlannableOrder[];
  csrfToken: string;
  canWrite: boolean;
}) {
  const router = useRouter();
  const { t, locale } = useLocale();
  const [orderId, setOrderId] = useState(orders[0]?.id ?? "");
  const order = useMemo(
    () => orders.find((item) => item.id === orderId) ?? null,
    [orders, orderId],
  );
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<TransportMode>("SEA");
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [carrier, setCarrier] = useState("");
  const [forwarder, setForwarder] = useState("");
  const [plannedDispatch, setPlannedDispatch] = useState("");
  const [estimatedArrival, setEstimatedArrival] = useState("");
  const [tracking, setTracking] = useState("");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function quantityFor(line: PlannableOrder["lines"][number]): string {
    return quantities[line.id] ?? line.remaining;
  }

  async function submit(): Promise<void> {
    if (!order) return;
    if (origin.trim().length < 2 || destination.trim().length < 2) {
      setError(t("spfOriginRequired"));
      return;
    }
    const items = order.lines
      .map((line) => ({ sales_order_item_id: line.id, quantity: quantityFor(line).trim() }))
      .filter((line) => {
        const parsed = Number.parseFloat(line.quantity);
        return Number.isFinite(parsed) && parsed > 0;
      });
    if (items.length === 0) {
      setError(t("spfQuantityRequired"));
      return;
    }

    setPending(true);
    setError(null);
    const result = await planShipment(
      {
        sales_order_id: order.id,
        transport_mode: mode,
        origin: origin.trim(),
        destination: destination.trim(),
        carrier: carrier.trim() || null,
        forwarder: forwarder.trim() || null,
        planned_dispatch_at: plannedDispatch ? new Date(plannedDispatch).toISOString() : null,
        estimated_arrival_at: estimatedArrival ? new Date(estimatedArrival).toISOString() : null,
        tracking_reference: tracking.trim() || null,
        tracking_source: tracking.trim() ? "MANUAL" : null,
        notes: notes.trim() || null,
        items,
      },
      csrfToken,
    );
    setPending(false);

    if (!result.ok) {
      setError(
        result.code === "CONFLICT" || result.code === "BAD_REQUEST"
          ? t("spfCheckRemaining", { message: result.message })
          : result.message,
      );
      return;
    }
    router.push(`/shipments/${result.data.id}`);
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title={t("readOnlyAccess")}>
        {t("spfReadOnly")}
      </Alert>
    );
  }

  if (orders.length === 0) {
    return (
      <Alert variant="info" title={t("spfNoOrdersTitle")}>
        {t("spfNoOrdersBody")}
      </Alert>
    );
  }

  return (
    <div className="space-y-4">
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="shipment-order">{t("lgSalesOrder")}</Label>
          <Select
            id="shipment-order"
            value={orderId}
            onChange={(event) => {
              setOrderId(event.target.value);
              setQuantities({});
            }}
          >
            {orders.map((item) => (
              <option key={item.id} value={item.id}>
                {item.order_number} · {item.customer_name}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="shipment-mode">{t("spfMode")}</Label>
          <Select
            id="shipment-mode"
            value={mode}
            onChange={(event) => setMode(event.target.value as TransportMode)}
          >
            {TRANSPORT_MODES.map((value) => (
              <option key={value} value={value}>
                {transportModeText(t, value)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="shipment-tracking">{t("spfTracking")}</Label>
          <Input
            id="shipment-tracking"
            value={tracking}
            maxLength={200}
            onChange={(event) => setTracking(event.target.value)}
            placeholder={t("spfTrackingPlaceholder")}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="shipment-origin">{t("spfOrigin")}</Label>
          <Input
            id="shipment-origin"
            value={origin}
            maxLength={160}
            onChange={(event) => setOrigin(event.target.value)}
            placeholder="Jebel Ali, AE"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="shipment-destination">{t("spfDestination")}</Label>
          <Input
            id="shipment-destination"
            value={destination}
            maxLength={160}
            onChange={(event) => setDestination(event.target.value)}
            placeholder="Rotterdam, NL"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="shipment-carrier">{t("spfCarrier")}</Label>
          <Input
            id="shipment-carrier"
            value={carrier}
            maxLength={160}
            onChange={(event) => setCarrier(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="shipment-forwarder">{t("spfForwarder")}</Label>
          <Input
            id="shipment-forwarder"
            value={forwarder}
            maxLength={160}
            onChange={(event) => setForwarder(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="shipment-planned">{t("lgPlannedDispatch")}</Label>
          <Input
            id="shipment-planned"
            type="datetime-local"
            value={plannedDispatch}
            onChange={(event) => setPlannedDispatch(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="shipment-eta">{t("spfEta")}</Label>
          <Input
            id="shipment-eta"
            type="datetime-local"
            value={estimatedArrival}
            onChange={(event) => setEstimatedArrival(event.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="shipment-notes">{t("fieldNotes")}</Label>
          <Textarea
            id="shipment-notes"
            value={notes}
            maxLength={2000}
            onChange={(event) => setNotes(event.target.value)}
          />
        </div>
      </div>

      <div className="rounded-lg border border-white/[0.07]">
        <div className="border-b border-white/[0.06] px-3 py-2">
          <p className="eyebrow">{t("spfLines")}</p>
        </div>
        <div className="divide-y divide-white/[0.05]">
          {order?.lines.map((line) => (
            <div key={line.id} className="grid gap-2 px-3 py-2 sm:grid-cols-[1fr_120px_150px]">
              <div>
                <p className="font-mono text-[11.5px] text-accent-200">{line.sku}</p>
                <p className="text-[10.5px] text-mist-500">{line.description}</p>
              </div>
              <p className="text-[11px] text-mist-400">
                {t("spfRemaining", { quantity: formatQuantity(line.remaining, line.unit, locale) })}
              </p>
              <Input
                aria-label={t("spfQuantityFor", { sku: line.sku })}
                inputMode="decimal"
                value={quantityFor(line)}
                onChange={(event) =>
                  setQuantities((current) => ({ ...current, [line.id]: event.target.value }))
                }
              />
            </div>
          ))}
        </div>
      </div>

      <Button type="button" disabled={pending} onClick={() => void submit()}>
        {pending ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <Ship className="size-3.5" aria-hidden />
        )}
        {pending ? t("spfPlanning") : t("shpPlan")}
      </Button>
      <p className="text-[10.5px] leading-relaxed text-mist-600">{t("spfNote")}</p>
    </div>
  );
}
