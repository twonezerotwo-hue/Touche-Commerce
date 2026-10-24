"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useLocale } from "@/lib/i18n/locale-provider";
import { updateDeal } from "@/lib/trade/client";
import type { Deal } from "@/lib/trade/types";

export function DealEditForm({
  deal,
  csrfToken,
  canWrite,
}: {
  deal: Deal;
  csrfToken: string;
  canWrite: boolean;
}) {
  const router = useRouter();
  const { t } = useLocale();
  const [title, setTitle] = useState(deal.title);
  const [currency, setCurrency] = useState(deal.currency);
  const [expectedCloseDate, setExpectedCloseDate] = useState(deal.expected_close_date ?? "");
  const [notes, setNotes] = useState(deal.notes ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const closed = ["WON", "LOST", "CANCELLED"].includes(deal.status);

  if (!canWrite) return null;

  if (closed) {
    return (
      <Alert variant="info" title={t("deClosedTitle")}>
        {t("deClosedBody")}
      </Alert>
    );
  }

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (!title.trim()) {
      setError(t("dfErrTitle"));
      return;
    }
    setPending(true);
    const result = await updateDeal(
      deal.id,
      {
        title: title.trim(),
        currency: currency.trim().toUpperCase(),
        expected_close_date: expectedCloseDate || null,
        notes: notes.trim() || null,
      },
      csrfToken,
      `"v${deal.version}"`,
    );
    setPending(false);

    if (!result.ok) {
      setError(
        result.code === "VERSION_CONFLICT"
          ? t("deConflict", { message: result.message })
          : result.requestId
            ? t("requestRef", { message: result.message, id: result.requestId })
            : result.message,
      );
      return;
    }
    setNotice(t("deUpdated"));
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="edit-title">{t("dealsColTitle")}</Label>
          <Input
            id="edit-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={160}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="edit-currency">{t("columnCurrency")}</Label>
          <Input
            id="edit-currency"
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
            maxLength={3}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="edit-close-date">{t("dealsColExpectedClose")}</Label>
          <Input
            id="edit-close-date"
            type="date"
            value={expectedCloseDate}
            onChange={(event) => setExpectedCloseDate(event.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="edit-notes">{t("fieldNotes")}</Label>
          <Textarea
            id="edit-notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            maxLength={2000}
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
          {pending ? t("actionSaving") : t("deSave")}
        </Button>
        <span className="text-[11px] text-mist-600">
          {t("deIfMatch", { version: deal.version })}
        </span>
      </div>
    </form>
  );
}
