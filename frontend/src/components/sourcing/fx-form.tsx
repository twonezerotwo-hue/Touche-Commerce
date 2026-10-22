"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import { newIdempotencyKey } from "@/lib/sourcing/client";

/**
 * Record an FX observation.
 *
 * There is deliberately no "fetch today's rate" button: a rate is a sourced,
 * timestamped fact, and pricing may only convert with a stored snapshot.
 */
export function FxRateForm({ csrfToken }: { csrfToken: string }) {
  const router = useRouter();
  const [base, setBase] = useState("EUR");
  const [quote, setQuote] = useState("USD");
  const [rate, setRate] = useState("");
  const [effectiveAt, setEffectiveAt] = useState("");
  const [source, setSource] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setNotice(null);

    if (base.length !== 3 || quote.length !== 3 || base === quote) {
      setError("Use two different three-letter currency codes.");
      return;
    }
    if (!effectiveAt) {
      setError("Record when the rate was effective.");
      return;
    }
    if (source.trim().length < 3) {
      setError("Name the source of the rate.");
      return;
    }

    setPending(true);
    try {
      const response = await fetch(`${BROWSER_API_PREFIX}/fx-rates`, {
        method: "POST",
        headers: {
          accept: "application/json",
          "content-type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": newIdempotencyKey(),
        },
        credentials: "same-origin",
        cache: "no-store",
        body: JSON.stringify({
          base_currency: base,
          quote_currency: quote,
          rate: rate.trim(),
          effective_at: new Date(`${effectiveAt}T00:00:00Z`).toISOString(),
          source: source.trim(),
        }),
      });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        setError(parseErrorEnvelope(payload)?.error.message ?? "The rate could not be recorded.");
        return;
      }
      setRate("");
      setSource("");
      setNotice("Snapshot recorded.");
      router.refresh();
    } catch {
      setError("Cannot reach the API.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      {error ? <Alert variant="danger">{error}</Alert> : null}
      {notice ? <Alert variant="success">{notice}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="fx-base">Base</Label>
          <Input
            id="fx-base"
            value={base}
            maxLength={3}
            onChange={(event) => setBase(event.target.value.toUpperCase())}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fx-quote">Quote</Label>
          <Input
            id="fx-quote"
            value={quote}
            maxLength={3}
            onChange={(event) => setQuote(event.target.value.toUpperCase())}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fx-rate">Rate</Label>
          <Input
            id="fx-rate"
            value={rate}
            inputMode="decimal"
            onChange={(event) => setRate(event.target.value)}
            placeholder="1.0875000000"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fx-effective">Effective</Label>
          <Input
            id="fx-effective"
            type="date"
            value={effectiveAt}
            onChange={(event) => setEffectiveAt(event.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="fx-source">Source</Label>
          <Input
            id="fx-source"
            value={source}
            maxLength={160}
            onChange={(event) => setSource(event.target.value)}
            placeholder="ECB reference rate 2026-10-22"
          />
        </div>
      </div>

      <Button type="submit" size="sm" disabled={pending}>
        {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
        {pending ? "Recording…" : "Record snapshot"}
      </Button>
    </form>
  );
}
