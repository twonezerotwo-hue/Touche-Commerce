"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { transitionShipment } from "@/lib/operations/client";
import { operationsStatusLabel } from "@/lib/operations/format";
import type { Shipment } from "@/lib/operations/types";
import { etagFor } from "@/lib/sourcing/format";

import { ExtraRecord } from "./shipment-extra-record";

/**
 * Shipment milestones and the evidence they require.
 *
 * Dispatch needs a booking/tracking reference, arrival needs the actual arrival
 * timestamp, and delivery needs a delivery-evidence reference. The component
 * collects them; the API enforces them regardless of what the UI offers.
 */
export function ShipmentActions({
  shipment,
  csrfToken,
  canWrite,
}: {
  shipment: Shipment;
  csrfToken: string;
  canWrite: boolean;
}) {
  const router = useRouter();
  const [target, setTarget] = useState<string | null>(null);
  const [tracking, setTracking] = useState(shipment.tracking_reference ?? "");
  const [evidence, setEvidence] = useState("");
  const [reason, setReason] = useState("");
  const [location, setLocation] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function apply(): Promise<void> {
    if (!target) return;
    if (target === "DISPATCHED" && tracking.trim().length < 2) {
      setError("Record the carrier or booking reference before dispatching.");
      return;
    }
    if (target === "DELIVERED" && evidence.trim().length < 2) {
      setError("Delivery requires a signed proof-of-delivery reference.");
      return;
    }
    if (target === "CANCELLED" && reason.trim().length < 3) {
      setError("Cancelling a shipment needs a reason.");
      return;
    }

    setPending(true);
    setError(null);
    const result = await transitionShipment(
      shipment.id,
      {
        target,
        occurred_at: new Date().toISOString(),
        location: location.trim() || null,
        notes: null,
        reason: reason.trim() || null,
        tracking_reference: target === "DISPATCHED" ? tracking.trim() : null,
        tracking_source: target === "DISPATCHED" ? "MANUAL" : null,
        delivery_evidence_reference: target === "DELIVERED" ? evidence.trim() : null,
      },
      csrfToken,
      etagFor(shipment.version),
    );
    setPending(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setTarget(null);
    setEvidence("");
    setReason("");
    setNotice(`Shipment is now ${operationsStatusLabel(result.data.status).toLowerCase()}.`);
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title="Read-only access">
        Recording shipment milestones requires <span className="font-mono">trade.write</span>.
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="flex flex-wrap gap-2">
        {shipment.allowed_transitions.map((value) => (
          <Button
            key={value}
            type="button"
            size="sm"
            variant={value === "CANCELLED" ? "danger" : "outline"}
            onClick={() => setTarget(value)}
          >
            Mark {operationsStatusLabel(value).toLowerCase()}
          </Button>
        ))}
        <Button type="button" size="sm" variant="subtle" onClick={() => setTarget("_event")}>
          Record movement note
        </Button>
        <Button type="button" size="sm" variant="subtle" onClick={() => setTarget("_cost")}>
          Record cost
        </Button>
        <Button type="button" size="sm" variant="subtle" onClick={() => setTarget("_reference")}>
          Add reference
        </Button>
      </div>

      {target ? (
        <div className="rounded-lg border border-white/[0.07] bg-white/[0.015] p-3">
          {target.startsWith("_") ? (
            <ExtraRecord
              kind={target === "_event" ? "event" : target === "_cost" ? "cost" : "reference"}
              shipmentId={shipment.id}
              csrfToken={csrfToken}
              onDone={() => {
                setTarget(null);
                router.refresh();
              }}
            />
          ) : (
            <>
              <p className="text-[12.5px] text-mist-200">
                {target === "DISPATCHED"
                  ? "Dispatching records that the goods actually left. A booking reference is required."
                  : target === "ARRIVED"
                    ? "Arrival records the actual arrival timestamp; the ETA is not used."
                    : target === "DELIVERED"
                      ? "Delivery needs a signed proof-of-delivery or document reference."
                      : target === "CANCELLED"
                        ? "Cancellation releases the allocated quantities. A reason is required."
                        : `Move this shipment to ${operationsStatusLabel(target).toLowerCase()}?`}
              </p>

              {target === "DISPATCHED" ? (
                <div className="mt-2 space-y-1.5">
                  <Label htmlFor="shipment-tracking">Carrier / booking reference</Label>
                  <Input
                    id="shipment-tracking"
                    value={tracking}
                    maxLength={200}
                    onChange={(event) => setTracking(event.target.value)}
                  />
                  <p className="text-[10px] text-mist-600">
                    Provenance is recorded as MANUAL. This is not live carrier-verified tracking.
                  </p>
                </div>
              ) : null}

              {target === "DELIVERED" ? (
                <div className="mt-2 space-y-1.5">
                  <Label htmlFor="shipment-evidence">Delivery evidence reference</Label>
                  <Input
                    id="shipment-evidence"
                    value={evidence}
                    maxLength={500}
                    onChange={(event) => setEvidence(event.target.value)}
                    placeholder="Signed POD id or uploaded document"
                  />
                </div>
              ) : null}

              {target === "ARRIVED" ? (
                <div className="mt-2 space-y-1.5">
                  <Label htmlFor="shipment-location">Arrival location (optional)</Label>
                  <Input
                    id="shipment-location"
                    value={location}
                    maxLength={160}
                    onChange={(event) => setLocation(event.target.value)}
                  />
                </div>
              ) : null}

              {target === "CANCELLED" ? (
                <div className="mt-2 space-y-1.5">
                  <Label htmlFor="shipment-reason">Reason (required)</Label>
                  <Textarea
                    id="shipment-reason"
                    value={reason}
                    maxLength={500}
                    onChange={(event) => setReason(event.target.value)}
                  />
                </div>
              ) : null}

              <div className="mt-3 flex items-center gap-2">
                <Button type="button" size="sm" disabled={pending} onClick={() => void apply()}>
                  {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
                  {pending ? "Applying…" : "Confirm"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setTarget(null);
                    setError(null);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
