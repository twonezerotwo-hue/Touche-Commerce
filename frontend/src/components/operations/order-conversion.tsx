"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertTriangle, FileCheck2, Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useLocale } from "@/lib/i18n/locale-provider";
import { acceptanceChannelText } from "@/lib/i18n/value-labels";
import { convertDealToOrder, recordCustomerAcceptance } from "@/lib/operations/client";
import { newIdempotencyKey } from "@/lib/sourcing/client";
import type { CustomerAcceptance, SalesQuoteOption } from "@/lib/operations/types";

const CHANNELS = ["SIGNED_QUOTE", "PURCHASE_ORDER", "EMAIL", "PORTAL", "OTHER"] as const;

function toLocalInput(date: Date, withSeconds: boolean): string {
  const offset = date.getTimezoneOffset() * 60_000;
  const iso = new Date(date.getTime() - offset).toISOString();
  return withSeconds ? iso.slice(0, 19) : iso.slice(0, 16);
}

/**
 * The pre-filled acceptance time: now (to the minute), but never earlier than the internal
 * approval of the selected quote. The API refuses an acceptance that predates the approval, and
 * a time rounded down to the minute can do exactly that for a conversion made right after it.
 */
export function defaultAcceptedAt(approvedAt: string | null | undefined, now = new Date()): string {
  const flooredNow = new Date(Math.floor(now.getTime() / 60_000) * 60_000);
  const approved = approvedAt ? new Date(approvedAt) : null;
  if (approved && !Number.isNaN(approved.getTime()) && approved > flooredNow) {
    // The input has whole-second precision; round up so the value is not before the approval.
    return toLocalInput(new Date(Math.ceil(approved.getTime() / 1000) * 1000), true);
  }
  return toLocalInput(flooredNow, false);
}

/**
 * Customer acceptance and the atomic conversion that wins the deal.
 *
 * The panel deliberately separates the two facts: the quote is already approved
 * internally, and acceptance is a *customer* act with a channel, a timestamp and
 * an evidence reference. The API refuses the conversion without it.
 */
export function OrderConversionPanel({
  dealId,
  quotes,
  acceptances,
  csrfToken,
  canWrite,
  brokerage,
  onBrokerageChange,
}: {
  dealId: string;
  quotes: SalesQuoteOption[];
  acceptances: CustomerAcceptance[];
  csrfToken: string;
  canWrite: boolean;
  brokerage: boolean;
  onBrokerageChange: (value: boolean) => void;
}) {
  const router = useRouter();
  const { t, locale } = useLocale();
  const approved = quotes.filter((quote) => quote.status === "APPROVED");
  const [quoteId, setQuoteId] = useState(approved[0]?.id ?? "");
  const [channel, setChannel] = useState<string>("SIGNED_QUOTE");
  const [acceptedAt, setAcceptedAt] = useState(() => defaultAcceptedAt(approved[0]?.approved_at));
  const [acceptedAtEdited, setAcceptedAtEdited] = useState(false);
  const [acceptedBy, setAcceptedBy] = useState("");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [conversionKey] = useState(() => newIdempotencyKey());

  const existing = acceptances.find((item) => item.sales_quote_id === quoteId) ?? null;

  async function recordAndConvert(): Promise<void> {
    setError(null);
    setNotice(null);
    if (!quoteId) {
      setError(t("ocSelectQuote"));
      return;
    }
    if (!existing) {
      if (acceptedBy.trim().length < 2) {
        setError(t("ocWhoAccepted"));
        return;
      }
      if (reference.trim().length < 3) {
        setError(t("ocEvidenceRequired"));
        return;
      }
    }

    setPending(true);
    let evidenceId = existing?.id ?? null;
    if (!evidenceId) {
      const acceptance = await recordCustomerAcceptance(
        dealId,
        {
          channel,
          accepted_at: new Date(acceptedAt).toISOString(),
          accepted_by_name: acceptedBy.trim(),
          evidence_reference: reference.trim(),
          notes: notes.trim() || null,
        },
        csrfToken,
      );
      if (!acceptance.ok) {
        setPending(false);
        setError(
          acceptance.code === "CONFLICT"
            ? t("ocApproveFirst", { message: acceptance.message })
            : acceptance.message,
        );
        return;
      }
      evidenceId = acceptance.data.id;
      setNotice(t("ocRecorded"));
    }

    const conversion = await convertDealToOrder(
      dealId,
      { sales_quote_id: quoteId, acceptance_evidence_id: evidenceId },
      csrfToken,
      conversionKey,
    );
    setPending(false);

    if (!conversion.ok) {
      setError(
        conversion.code === "ALREADY_WON"
          ? t("ocAlreadyWon")
          : conversion.code === "IDEMPOTENCY_CONFLICT"
            ? t("ocIdempotency")
            : conversion.message,
      );
      return;
    }

    router.push(`/orders/${conversion.data.id}`);
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title={t("readOnlyAccess")}>
        {t("ocReadOnly")}
      </Alert>
    );
  }

  if (approved.length === 0) {
    return (
      <Alert variant="info" title={t("ocNoApprovedTitle")}>
        {t("ocNoApprovedBody")}
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      <Alert variant="warning" title={t("ocNotAcceptanceTitle")}>
        {t("ocNotAcceptanceBody")}
      </Alert>

      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="convert-quote">{t("ocApprovedQuote")}</Label>
          <Select
            id="convert-quote"
            value={quoteId}
            onChange={(event) => {
              setQuoteId(event.target.value);
              if (!acceptedAtEdited) {
                const chosen = approved.find((quote) => quote.id === event.target.value);
                setAcceptedAt(defaultAcceptedAt(chosen?.approved_at));
              }
            }}
          >
            {approved.map((quote) => (
              <option key={quote.id} value={quote.id}>
                {quote.quote_number} r{quote.revision} · {quote.currency} {quote.total_value}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="convert-model">{t("ocModel")}</Label>
          <Select
            id="convert-model"
            value={brokerage ? "BROKERAGE" : "PURCHASE_RESALE"}
            onChange={(event) => onBrokerageChange(event.target.value === "BROKERAGE")}
          >
            <option value="PURCHASE_RESALE">{t("ocModelResale")}</option>
            <option value="BROKERAGE">{t("ocModelBrokerage")}</option>
          </Select>
          <p className="text-[10.5px] leading-relaxed text-mist-600">{t("ocBrokerageNote")}</p>
        </div>
      </div>

      {existing ? (
        <Alert variant="success" title={t("ocExistingTitle")}>
          {t("ocExistingBody", {
            name: existing.accepted_by_name,
            revision: existing.sales_quote_revision,
            channel: acceptanceChannelText(t, existing.channel),
            date: new Date(existing.accepted_at).toLocaleString(
              locale === "tr" ? "tr-TR" : "en-GB",
            ),
            reference: existing.evidence_reference,
          })}
        </Alert>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="acceptance-channel">{t("ocChannel")}</Label>
            <Select
              id="acceptance-channel"
              value={channel}
              onChange={(event) => setChannel(event.target.value)}
            >
              {CHANNELS.map((option) => (
                <option key={option} value={option}>
                  {acceptanceChannelText(t, option)}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="acceptance-at">{t("ocAcceptedAt")}</Label>
            <Input
              id="acceptance-at"
              type="datetime-local"
              value={acceptedAt}
              onChange={(event) => {
                setAcceptedAt(event.target.value);
                setAcceptedAtEdited(true);
              }}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="acceptance-by">{t("ocAcceptedBy")}</Label>
            <Input
              id="acceptance-by"
              value={acceptedBy}
              maxLength={160}
              onChange={(event) => setAcceptedBy(event.target.value)}
              placeholder={t("ocAcceptedByPlaceholder")}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="acceptance-reference">{t("ocEvidenceRef")}</Label>
            <Input
              id="acceptance-reference"
              value={reference}
              maxLength={500}
              onChange={(event) => setReference(event.target.value)}
              placeholder={t("ocEvidencePlaceholder")}
            />
          </div>
          <div className="sm:col-span-2 space-y-1.5">
            <Label htmlFor="acceptance-notes">{t("ocNotesOptional")}</Label>
            <Textarea
              id="acceptance-notes"
              value={notes}
              maxLength={2000}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" disabled={pending} onClick={() => void recordAndConvert()}>
          {pending ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <FileCheck2 className="size-3.5" aria-hidden />
          )}
          {pending ? t("ocConverting") : existing ? t("ocConvert") : t("ocRecordConvert")}
        </Button>
        <span className="inline-flex items-center gap-1.5 text-[10.5px] text-mist-600">
          <AlertTriangle className="size-3 text-amber-400" aria-hidden />
          {t("ocOneTransaction")}
        </span>
      </div>
    </div>
  );
}
