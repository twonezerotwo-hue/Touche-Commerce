"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useLocale } from "@/lib/i18n/locale-provider";
import { costStageText, costTypeText, referenceTypeText } from "@/lib/i18n/value-labels";
import {
  addShipmentReference,
  recordShipmentCost,
  recordShipmentEvent,
} from "@/lib/operations/client";
import { COST_STAGES, SHIPMENT_COST_TYPES, SHIPMENT_REFERENCE_TYPES } from "@/lib/operations/types";

/**
 * Movement notes, cost provenance and booking references for one shipment.
 *
 * Costs keep their own stage (`ESTIMATED`, `QUOTED`, `INCURRED`, `DOCUMENTED`):
 * recording an incurred invoice never rewrites the Stage 3 estimate.
 */
export function ExtraRecord({
  kind,
  shipmentId,
  csrfToken,
  onDone,
}: {
  kind: "event" | "cost" | "reference";
  shipmentId: string;
  csrfToken: string;
  onDone: () => void;
}) {
  const { t } = useLocale();
  const [eventType, setEventType] = useState<"IN_TRANSIT" | "DELAY_RECORDED">("IN_TRANSIT");
  const [occurredAt, setOccurredAt] = useState(new Date().toISOString().slice(0, 16));
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [costType, setCostType] = useState<string>(SHIPMENT_COST_TYPES[0]);
  const [stage, setStage] = useState<string>(COST_STAGES[0]);
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [referenceType, setReferenceType] = useState<string>(SHIPMENT_REFERENCE_TYPES[0]);
  const [referenceValue, setReferenceValue] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(): Promise<void> {
    setPending(true);
    setError(null);
    const result =
      kind === "event"
        ? await recordShipmentEvent(
            shipmentId,
            {
              event_type: eventType,
              occurred_at: new Date(occurredAt).toISOString(),
              location: location.trim() || null,
              notes: notes.trim() || null,
              tracking_source: "MANUAL",
            },
            csrfToken,
          )
        : kind === "cost"
          ? await recordShipmentCost(
              shipmentId,
              {
                cost_type: costType,
                stage,
                amount: amount.trim(),
                currency: currency.trim().toUpperCase(),
                reference: notes.trim() || "manual entry",
              },
              csrfToken,
            )
          : await addShipmentReference(
              shipmentId,
              {
                reference_type: referenceType,
                reference_value: referenceValue.trim(),
                provenance: "MANUAL",
              },
              csrfToken,
            );
    setPending(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    onDone();
  }

  return (
    <div className="space-y-2">
      {error ? <Alert variant="danger">{error}</Alert> : null}

      {kind === "event" ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="event-type">{t("shxEvent")}</Label>
            <Select
              id="event-type"
              value={eventType}
              onChange={(event) =>
                setEventType(event.target.value as "IN_TRANSIT" | "DELAY_RECORDED")
              }
            >
              <option value="IN_TRANSIT">{t("opStatusInTransit")}</option>
              <option value="DELAY_RECORDED">{t("eventDelayRecorded")}</option>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="event-at">{t("shxOccurredAt")}</Label>
            <Input
              id="event-at"
              type="datetime-local"
              value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="event-location">{t("shxLocation")}</Label>
            <Input
              id="event-location"
              value={location}
              maxLength={160}
              onChange={(event) => setLocation(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="event-notes">{t("fieldNotes")}</Label>
            <Input
              id="event-notes"
              value={notes}
              maxLength={2000}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
        </div>
      ) : null}

      {kind === "cost" ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="cost-type">{t("shxCostType")}</Label>
            <Select
              id="cost-type"
              value={costType}
              onChange={(event) => setCostType(event.target.value)}
            >
              {SHIPMENT_COST_TYPES.map((value) => (
                <option key={value} value={value}>
                  {costTypeText(t, value)}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="cost-stage">{t("shxStage")}</Label>
            <Select
              id="cost-stage"
              value={stage}
              onChange={(event) => setStage(event.target.value)}
            >
              {COST_STAGES.map((value) => (
                <option key={value} value={value}>
                  {costStageText(t, value)}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="cost-amount">{t("shxAmount")}</Label>
            <Input
              id="cost-amount"
              inputMode="decimal"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="cost-currency">{t("columnCurrency")}</Label>
            <Input
              id="cost-currency"
              value={currency}
              maxLength={3}
              onChange={(event) => setCurrency(event.target.value)}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="cost-reference">{t("shxCostReference")}</Label>
            <Input
              id="cost-reference"
              value={notes}
              maxLength={2000}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
        </div>
      ) : null}

      {kind === "reference" ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="ref-type">{t("shxRefType")}</Label>
            <Select
              id="ref-type"
              value={referenceType}
              onChange={(event) => setReferenceType(event.target.value)}
            >
              {SHIPMENT_REFERENCE_TYPES.map((value) => (
                <option key={value} value={value}>
                  {referenceTypeText(t, value)}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="ref-value">{t("shxRefValue")}</Label>
            <Input
              id="ref-value"
              value={referenceValue}
              maxLength={120}
              onChange={(event) => setReferenceValue(event.target.value)}
            />
          </div>
        </div>
      ) : null}

      <Button type="button" size="sm" disabled={pending} onClick={() => void submit()}>
        {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
        {pending ? t("actionSaving") : t("actionSave")}
      </Button>
      <p className="text-[10px] leading-relaxed text-mist-600">{t("shxNote")}</p>
    </div>
  );
}
