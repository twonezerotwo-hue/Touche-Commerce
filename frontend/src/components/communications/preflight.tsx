"use client";

import { useId, useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import type { components } from "@/lib/api/schema";
import { useLocale } from "@/lib/i18n/locale-provider";

type PreflightResponse = components["schemas"]["CommunicationPreflightResponse"];
type Channel = "EMAIL" | "WHATSAPP_BUSINESS";

const EXPLANATION_KEYS = {
  DRAFT_NOT_APPROVED: "pfDraftNotApproved",
  DRAFT_VERSION_MISMATCH: "pfDraftVersion",
  CHANNEL_NOT_CONFIGURED: "pfChannelNotConfigured",
  SEND_PERMISSION_UNAVAILABLE: "pfNoSendPermission",
  RECIPIENT_INVALID: "pfRecipientInvalid",
  CRM_RECIPIENT_MISMATCH: "pfCrmMismatch",
  CONSENT_UNDOCUMENTED: "pfConsent",
} as const;

export function CommunicationPreflight({
  draftId,
  draftVersion,
  csrfToken,
  counterparties,
}: {
  draftId: string;
  draftVersion: number;
  csrfToken: string;
  counterparties: { id: string; name: string }[];
}) {
  const key = useId();
  const { t } = useLocale();
  const [expanded, setExpanded] = useState(false);
  const [channel, setChannel] = useState<Channel>("EMAIL");
  const [recipient, setRecipient] = useState("");
  const [counterpartyId, setCounterpartyId] = useState("");
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<PreflightResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function check(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setResult(null);
    setError(null);
    setChecking(true);
    try {
      const response = await fetch(`${BROWSER_API_PREFIX}/communications/preflight`, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "content-type": "application/json",
          accept: "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({
          draft_id: draftId,
          draft_version: draftVersion,
          channel,
          recipient,
          counterparty_id: counterpartyId || null,
        }),
      });
      if (!response.ok) {
        setError(t("pfFailed"));
        return;
      }
      const payload = (await response.json()) as PreflightResponse;
      // The backend must never mark preflight as permission to dispatch.
      if (payload.sendable !== false || payload.external_sending_enabled !== false) {
        setError(t("pfUnexpected"));
        return;
      }
      setResult(payload);
    } catch {
      setError(t("pfUnavailable"));
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="mt-3 border-t border-white/10 pt-3">
      <Button type="button" size="xs" variant="outline" onClick={() => setExpanded(!expanded)}>
        {expanded ? t("pfHide") : t("pfShow")}
      </Button>
      {expanded ? (
        <form onSubmit={check} className="mt-3 space-y-3" aria-label={t("pfFormAria")}>
          <div className="space-y-1">
            <Label htmlFor={`${key}-counterparty`}>{t("pfCounterparty")}</Label>
            <select
              id={`${key}-counterparty`}
              value={counterpartyId}
              onChange={(event) => {
                setCounterpartyId(event.target.value);
                setResult(null);
              }}
              className="h-10 w-full rounded-md border border-white/10 bg-ink-950/70 px-3 text-[13px] text-mist-100"
            >
              <option value="">{t("pfSelectCounterparty")}</option>
              {counterparties.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor={`${key}-channel`}>{t("pfChannel")}</Label>
              <select
                id={`${key}-channel`}
                value={channel}
                onChange={(event) => {
                  setChannel(event.target.value as Channel);
                  setResult(null);
                }}
                className="h-10 w-full rounded-md border border-white/10 bg-ink-950/70 px-3 text-[13px] text-mist-100"
              >
                <option value="EMAIL">{t("commEmail")}</option>
                <option value="WHATSAPP_BUSINESS">{t("commWhatsApp")}</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor={`${key}-recipient`}>{t("pfRecipient")}</Label>
              <Input
                id={`${key}-recipient`}
                type="text"
                required
                maxLength={254}
                placeholder={channel === "EMAIL" ? "contact@example.com" : "+491701234567"}
                autoComplete="off"
                value={recipient}
                onChange={(event) => {
                  setRecipient(event.target.value);
                  setResult(null);
                }}
              />
            </div>
          </div>
          <Button size="sm" type="submit" variant="subtle" disabled={checking || !recipient.trim()}>
            {checking ? t("pfChecking") : t("pfCheck")}
          </Button>
          <p className="text-xs text-mist-500">{t("pfNote")}</p>
          {error ? <Alert variant="warning">{error}</Alert> : null}
          {result ? (
            <Alert variant="info" title={t("pfBlockedTitle")}>
              <ul className="list-disc space-y-1 pl-4">
                {result.blockers.map((code) => (
                  <li key={code}>
                    {t(
                      EXPLANATION_KEYS[code as keyof typeof EXPLANATION_KEYS] ?? "pfBlockerDefault",
                    )}
                  </li>
                ))}
              </ul>
            </Alert>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}
