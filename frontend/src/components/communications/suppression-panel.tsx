"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import { useLocale } from "@/lib/i18n/locale-provider";

type Channel = "EMAIL" | "WHATSAPP_BUSINESS";
type Reason = "CONTACT_REQUEST" | "COMPLIANCE_REVIEW" | "IMPORTED_BLOCK";

export function SuppressionPanel({
  csrfToken,
  counterparties,
  saved,
}: {
  csrfToken: string;
  counterparties: { id: string; name: string }[];
  saved: { id: string; counterparty_id: string; channel: Channel; reason: Reason }[];
}) {
  const router = useRouter();
  const { t } = useLocale();
  const [counterpartyId, setCounterpartyId] = useState("");
  const [channel, setChannel] = useState<Channel>("EMAIL");
  const [reason, setReason] = useState<Reason>("CONTACT_REQUEST");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function record(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!confirmed || !counterpartyId || busy) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const response = await fetch(`${BROWSER_API_PREFIX}/communications/suppressions`, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "content-type": "application/json",
          accept: "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({
          counterparty_id: counterpartyId,
          channel,
          reason,
        }),
      });
      if (!response.ok) {
        setError(t("supNotConfirmed"));
      } else {
        setSuccess(t("supSuccess"));
        setConfirmed(false);
        router.refresh();
      }
    } catch {
      setError(t("supUnreachable"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <h2 className="font-semibold text-white">{t("supTitle")}</h2>
      <p className="mt-2 text-sm text-mist-300">{t("supBody")}</p>
      <form className="mt-4 space-y-3" onSubmit={record}>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor="suppress-counterparty">{t("supCounterparty")}</Label>
            <select
              id="suppress-counterparty"
              value={counterpartyId}
              onChange={(event) => {
                setCounterpartyId(event.target.value);
                setConfirmed(false);
              }}
              className="h-10 w-full rounded-md border border-white/10 bg-ink-950/70 px-3 text-[13px] text-mist-100"
              required
            >
              <option value="">{t("supChoose")}</option>
              {counterparties.map((party) => (
                <option key={party.id} value={party.id}>
                  {party.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="suppress-channel">{t("supChannel")}</Label>
            <select
              id="suppress-channel"
              value={channel}
              onChange={(event) => {
                setChannel(event.target.value as Channel);
                setConfirmed(false);
              }}
              className="h-10 w-full rounded-md border border-white/10 bg-ink-950/70 px-3 text-[13px] text-mist-100"
            >
              <option value="EMAIL">{t("commEmail")}</option>
              <option value="WHATSAPP_BUSINESS">{t("commWhatsApp")}</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="suppress-reason">{t("supSource")}</Label>
            <select
              id="suppress-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value as Reason)}
              className="h-10 w-full rounded-md border border-white/10 bg-ink-950/70 px-3 text-[13px] text-mist-100"
            >
              <option value="CONTACT_REQUEST">{t("supReasonContact")}</option>
              <option value="COMPLIANCE_REVIEW">{t("supReasonCompliance")}</option>
              <option value="IMPORTED_BLOCK">{t("supReasonImported")}</option>
            </select>
          </div>
        </div>
        <label className="flex items-start gap-2 text-sm text-mist-200">
          <Input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            className="mt-1 h-4 w-4 shrink-0"
          />
          {t("supUnderstand")}
        </label>
        <Button
          type="submit"
          variant="outline"
          size="sm"
          disabled={!confirmed || !counterpartyId || busy}
        >
          {busy ? t("supRecording") : t("supRecord")}
        </Button>
      </form>
      {error ? <Alert variant="warning">{error}</Alert> : null}
      {success ? <Alert variant="success">{success}</Alert> : null}
      <div className="mt-5">
        <h3 className="text-sm font-semibold text-white">{t("supRecent")}</h3>
        {saved.length === 0 ? (
          <p className="mt-2 text-sm text-mist-300">{t("supNone")}</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {saved.map((entry) => (
              <li
                key={entry.id}
                className="rounded-lg border border-white/10 p-3 text-xs text-mist-200"
              >
                <span className="font-medium text-white">
                  {counterparties.find((x) => x.id === entry.counterparty_id)?.name ??
                    t("supPrevious")}
                </span>
                {" · "}
                {entry.channel}
                {" · "}
                {entry.reason}
                {` · ${t("supBlocked")}`}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
