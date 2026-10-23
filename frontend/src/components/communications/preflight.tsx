"use client";

import { useId, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import type { components } from "@/lib/api/schema";

type PreflightResponse = components["schemas"]["CommunicationPreflightResponse"];
type Channel = "EMAIL" | "WHATSAPP_BUSINESS";

const EXPLANATIONS: Record<string, string> = {
  DRAFT_NOT_APPROVED: "A person must review and approve this draft first.",
  DRAFT_VERSION_MISMATCH: "The draft changed. Reload the page before checking again.",
  CHANNEL_NOT_CONFIGURED: "The email or WhatsApp connection is not configured.",
  SEND_PERMISSION_UNAVAILABLE: "No role is currently allowed to send messages.",
  RECIPIENT_INVALID: "The recipient format is invalid for the selected channel.",
};

export function CommunicationPreflight({
  draftId,
  draftVersion,
  csrfToken,
}: {
  draftId: string;
  draftVersion: number;
  csrfToken: string;
}) {
  const key = useId();
  const [expanded, setExpanded] = useState(false);
  const [channel, setChannel] = useState<Channel>("EMAIL");
  const [recipient, setRecipient] = useState("");
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<PreflightResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function check(event: React.FormEvent<HTMLFormElement>): Promise<void> {
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
        }),
      });
      if (!response.ok) {
        setError("Cannot check readiness. Verify access and reload this draft.");
        return;
      }
      const payload = (await response.json()) as PreflightResponse;
      // The backend must never mark preflight as permission to dispatch.
      if (payload.sendable !== false || payload.external_sending_enabled !== false) {
        setError("Unexpected response. Sending remains unavailable.");
        return;
      }
      setResult(payload);
    } catch {
      setError("The API is unavailable. Nothing was sent.");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="mt-3 border-t border-white/10 pt-3">
      <Button type="button" size="xs" variant="outline" onClick={() => setExpanded(!expanded)}>
        {expanded ? "Hide readiness check" : "Check readiness (no sending)"}
      </Button>
      {expanded ? (
        <form onSubmit={check} className="mt-3 space-y-3" aria-label="Send readiness preview">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor={`${key}-channel`}>Channel</Label>
              <select
                id={`${key}-channel`}
                value={channel}
                onChange={(event) => {
                  setChannel(event.target.value as Channel);
                  setResult(null);
                }}
                className="h-10 w-full rounded-md border border-white/10 bg-ink-950/70 px-3 text-[13px] text-mist-100"
              >
                <option value="EMAIL">Email</option>
                <option value="WHATSAPP_BUSINESS">WhatsApp Business</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor={`${key}-recipient`}>Recipient (not stored)</Label>
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
            {checking ? "Checking…" : "Check blockers"}
          </Button>
          <p className="text-xs text-mist-500">
            No email or WhatsApp message can be sent. This form does not save the recipient.
          </p>
          {error ? <Alert variant="warning">{error}</Alert> : null}
          {result ? (
            <Alert variant="info" title="Sending blocked">
              <ul className="list-disc space-y-1 pl-4">
                {result.blockers.map((code) => (
                  <li key={code}>{EXPLANATIONS[code] ?? "An unresolved delivery requirement remains."}</li>
                ))}
              </ul>
            </Alert>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}
