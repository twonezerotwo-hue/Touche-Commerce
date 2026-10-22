"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Link2, Loader2, ShieldCheck } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createReconciliationRun,
  linkReconciliationEvidence,
  resolveReconciliationDiscrepancy,
  reviewReconciliation,
} from "@/lib/finance/client";
import type {
  ReconciliationDiscrepancy,
  ReconciliationRun,
  ReconciliationSourceReference,
} from "@/lib/finance/reconciliation";
import type { OrderOption } from "@/components/finance/reconciliation-overview";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function etagOf(version: number): string {
  return `"v${version}"`;
}

function ActionError({ message }: { message: string | null }) {
  return message ? <Alert variant="danger">{message}</Alert> : null;
}

export function CreateReconciliationRun({
  orders,
  currency,
  csrfToken,
  financeReady,
}: {
  orders: OrderOption[];
  currency: string;
  csrfToken: string;
  financeReady: boolean;
}) {
  const router = useRouter();
  const eligible = orders.filter(
    (order) => order.currency === currency && order.status !== "CANCELLED",
  );
  const [orderId, setOrderId] = useState(eligible[0]?.id ?? "");
  const [asOf, setAsOf] = useState(today());
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(): Promise<void> {
    setError(null);
    if (!orderId) {
      setError("Select an accepted order in this currency.");
      return;
    }
    setPending(true);
    const result = await createReconciliationRun(
      { sales_order_id: orderId, currency, as_of: asOf },
      csrfToken,
    );
    setPending(false);
    if (!result.ok) {
      setError(`${result.message} (${result.code})`);
      return;
    }
    router.push(`/finance/reconciliation/${result.data.id}`);
    router.refresh();
  }

  return (
    <div className="panel space-y-3 p-4">
      <div>
        <p className="eyebrow">New reconciliation run</p>
        <p className="mt-1 text-[11px] leading-relaxed text-mist-500">
          Reads Finance summary and aging once, records source ids and deterministic gaps. It never
          writes to Finance.
        </p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="reconciliation-order">Accepted order</Label>
        <Select
          id="reconciliation-order"
          value={orderId}
          onChange={(event) => setOrderId(event.target.value)}
          disabled={eligible.length === 0 || pending}
        >
          {eligible.length === 0 ? <option value="">No eligible {currency} order</option> : null}
          {eligible.map((order) => (
            <option key={order.id} value={order.id}>
              {order.order_number} · {order.status.replaceAll("_", " ")}
            </option>
          ))}
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="reconciliation-as-of">As of</Label>
        <Input
          id="reconciliation-as-of"
          type="date"
          value={asOf}
          max={today()}
          onChange={(event) => setAsOf(event.target.value)}
          disabled={pending}
        />
      </div>
      <ActionError message={error} />
      {!financeReady ? (
        <p className="text-[10.5px] text-amber-400">
          Finance is not CONNECTED or DEGRADED; a run will be refused.
        </p>
      ) : null}
      <Button
        type="button"
        size="sm"
        disabled={pending || eligible.length === 0 || !financeReady}
        onClick={() => void submit()}
      >
        {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
        Create run
      </Button>
    </div>
  );
}

export function EvidenceLinkPanel({
  run,
  csrfToken,
  canLink,
}: {
  run: ReconciliationRun;
  csrfToken: string;
  canLink: boolean;
}) {
  const router = useRouter();
  const references = run.source_references.filter((item) => item.is_transaction_level);
  const [referenceId, setReferenceId] = useState(references[0]?.id ?? "");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canLink || run.status === "VERIFIED" || run.status === "DISPUTED") {
    return null;
  }
  if (references.length === 0) {
    return (
      <Alert variant="warning" title="No transaction-level Finance reference">
        Finance returned no aging source id for this currency. The run stays UNMATCHED; Commerce
        does not invent an invoice reference.
      </Alert>
    );
  }

  async function submit(): Promise<void> {
    const selected = references.find((item) => item.id === referenceId);
    if (!selected) {
      setError("Select a Finance source id.");
      return;
    }
    setPending(true);
    setError(null);
    const result = await linkReconciliationEvidence(
      {
        run_id: run.id,
        source_entity_type: "SALES_ORDER",
        source_entity_id: run.sales_order_id,
        finance_source_reference_id: selected.id,
        notes: notes.trim() || null,
      },
      csrfToken,
      etagOf(run.version),
    );
    setPending(false);
    if (!result.ok) {
      setError(`${result.message} (${result.code})`);
      return;
    }
    setNotes("");
    router.refresh();
  }

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="evidence-reference">Finance source reference</Label>
        <Select
          id="evidence-reference"
          value={referenceId}
          onChange={(event) => setReferenceId(event.target.value)}
          disabled={pending}
        >
          {references.map((reference) => (
            <option key={reference.id} value={reference.id}>
              {labelForReference(reference)}
            </option>
          ))}
        </Select>
        <p className="text-[10px] leading-relaxed text-mist-600">
          Linking is an explicit operator decision. Counterparty names are displayed, never used as
          a matching key.
        </p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="evidence-notes">Evidence note</Label>
        <Textarea
          id="evidence-notes"
          value={notes}
          maxLength={2000}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="What document or operator check supports this link?"
        />
      </div>
      <ActionError message={error} />
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={pending}
        onClick={() => void submit()}
      >
        {pending ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <Link2 className="size-3.5" aria-hidden />
        )}
        Link to accepted sales order
      </Button>
    </div>
  );
}

function labelForReference(reference: ReconciliationSourceReference): string {
  const amount = reference.observed_amount ?? "no amount";
  const kind = reference.source_type === "AGING_RECEIVABLE" ? "AR" : "AP";
  return `${kind} · ${reference.source_reference} · ${reference.currency} ${amount}`;
}

export function ReviewPanel({
  run,
  csrfToken,
  canReview,
}: {
  run: ReconciliationRun;
  csrfToken: string;
  canReview: boolean;
}) {
  const router = useRouter();
  const [decision, setDecision] = useState<"CONFIRM" | "DISPUTE" | "REQUEST_CHANGES">("CONFIRM");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canReview) {
    return (
      <Alert variant="info" title="Reviewer permission required">
        Financial review needs <span className="font-mono">finance.reconcile</span>. An admin does
        not inherit it, and the run creator cannot review their own run.
      </Alert>
    );
  }
  if (run.status === "VERIFIED") {
    return (
      <Alert variant="success" title="Verified evidence">
        This run is verified. A new run is required to review later source data.
      </Alert>
    );
  }

  async function submit(): Promise<void> {
    setPending(true);
    setError(null);
    const result = await reviewReconciliation(
      { run_id: run.id, decision, notes: notes.trim() },
      csrfToken,
      etagOf(run.version),
    );
    setPending(false);
    if (!result.ok) {
      setError(`${result.message} (${result.code})`);
      return;
    }
    router.refresh();
  }

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="review-decision">Decision</Label>
        <Select
          id="review-decision"
          value={decision}
          onChange={(event) =>
            setDecision(event.target.value as "CONFIRM" | "DISPUTE" | "REQUEST_CHANGES")
          }
          disabled={pending}
        >
          <option value="CONFIRM" disabled={run.status !== "MATCHED_EVIDENCE"}>
            Confirm and verify
          </option>
          <option value="DISPUTE">Dispute</option>
          <option value="REQUEST_CHANGES">Request changes</option>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="review-notes">Reviewer notes</Label>
        <Textarea
          id="review-notes"
          value={notes}
          minLength={3}
          maxLength={2000}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="State what you checked and why this decision is justified."
        />
      </div>
      <ActionError message={error} />
      <Button
        type="button"
        size="sm"
        disabled={pending || notes.trim().length < 3}
        onClick={() => void submit()}
      >
        {pending ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <ShieldCheck className="size-3.5" aria-hidden />
        )}
        Record review
      </Button>
    </div>
  );
}

export function DiscrepancyResolutionForm({
  discrepancy,
  csrfToken,
  canReview,
}: {
  discrepancy: ReconciliationDiscrepancy;
  csrfToken: string;
  canReview: boolean;
}) {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canReview || discrepancy.status !== "OPEN") return null;

  async function submit(): Promise<void> {
    setPending(true);
    setError(null);
    const result = await resolveReconciliationDiscrepancy(
      discrepancy.id,
      notes.trim(),
      csrfToken,
      etagOf(discrepancy.version),
    );
    setPending(false);
    if (!result.ok) {
      setError(`${result.message} (${result.code})`);
      return;
    }
    setNotes("");
    router.refresh();
  }

  return (
    <div className="mt-2 space-y-2">
      <Input
        value={notes}
        minLength={3}
        maxLength={2000}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="Resolution note (what evidence resolves this?)"
        disabled={pending}
      />
      <ActionError message={error} />
      <Button
        type="button"
        size="xs"
        variant="outline"
        disabled={pending || notes.trim().length < 3}
        onClick={() => void submit()}
      >
        {pending ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
        Resolve
      </Button>
    </div>
  );
}
