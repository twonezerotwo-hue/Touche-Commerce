"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
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
            <Label htmlFor="event-type">Event</Label>
            <Select
              id="event-type"
              value={eventType}
              onChange={(event) =>
                setEventType(event.target.value as "IN_TRANSIT" | "DELAY_RECORDED")
              }
            >
              <option value="IN_TRANSIT">In transit</option>
              <option value="DELAY_RECORDED">Delay recorded</option>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="event-at">Occurred at</Label>
            <Input
              id="event-at"
              type="datetime-local"
              value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="event-location">Location</Label>
            <Input
              id="event-location"
              value={location}
              maxLength={160}
              onChange={(event) => setLocation(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="event-notes">Notes</Label>
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
            <Label htmlFor="cost-type">Cost type</Label>
            <Select
              id="cost-type"
              value={costType}
              onChange={(event) => setCostType(event.target.value)}
            >
              {SHIPMENT_COST_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value.replaceAll("_", " ").toLowerCase()}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="cost-stage">Stage (never overwritten)</Label>
            <Select
              id="cost-stage"
              value={stage}
              onChange={(event) => setStage(event.target.value)}
            >
              {COST_STAGES.map((value) => (
                <option key={value} value={value}>
                  {value.toLowerCase()}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="cost-amount">Amount</Label>
            <Input
              id="cost-amount"
              inputMode="decimal"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="cost-currency">Currency</Label>
            <Input
              id="cost-currency"
              value={currency}
              maxLength={3}
              onChange={(event) => setCurrency(event.target.value)}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="cost-reference">Reference (quote or invoice id)</Label>
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
            <Label htmlFor="ref-type">Reference type</Label>
            <Select
              id="ref-type"
              value={referenceType}
              onChange={(event) => setReferenceType(event.target.value)}
            >
              {SHIPMENT_REFERENCE_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value.replaceAll("_", " ").toLowerCase()}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="ref-value">Reference value</Label>
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
        {pending ? "Saving…" : "Save"}
      </Button>
      <p className="text-[10px] leading-relaxed text-mist-600">
        Estimated, quoted and incurred costs are separate rows. Stage 3 pricing assumptions are
        never overwritten by an operational cost.
      </p>
    </div>
  );
}
