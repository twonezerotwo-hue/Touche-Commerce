"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Plus, X } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { createCounterparty } from "@/lib/trade/client";
import { COUNTERPARTY_TYPES } from "@/lib/trade/types";

const EMPTY = {
  name: "",
  type: "buyer",
  country: "",
  contact_name: "",
  email: "",
  phone: "",
  notes: "",
};

export function CounterpartyForm({
  csrfToken,
  canWrite,
}: {
  csrfToken: string;
  canWrite: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({ ...EMPTY });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!canWrite) {
    return (
      <Alert variant="info" title="Read-only access">
        Creating a counterparty requires the <span className="font-mono">trade.write</span>{" "}
        permission, which is held by traders. Administrators manage people, not deals.
      </Alert>
    );
  }

  function update(field: keyof typeof EMPTY, value: string): void {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (!values.name.trim()) {
      setError("A counterparty name is required.");
      return;
    }
    setPending(true);
    const result = await createCounterparty(
      {
        name: values.name.trim(),
        type: values.type as (typeof COUNTERPARTY_TYPES)[number],
        country: values.country.trim() || null,
        contact_name: values.contact_name.trim() || null,
        email: values.email.trim() || null,
        phone: values.phone.trim() || null,
        notes: values.notes.trim() || null,
      },
      csrfToken,
    );
    setPending(false);

    if (!result.ok) {
      setError(
        result.requestId ? `${result.message} (request ${result.requestId})` : result.message,
      );
      return;
    }
    setValues({ ...EMPTY });
    setOpen(false);
    setNotice(`${result.data.name} added.`);
    router.refresh();
  }

  if (!open) {
    return (
      <div className="space-y-3">
        {notice ? <Alert variant="success">{notice}</Alert> : null}
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
          <Plus className="size-3.5" aria-hidden />
          New counterparty
        </Button>
      </div>
    );

    return (
      <form onSubmit={submit} className="panel space-y-4 rounded-xl p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <span className="eyebrow">New counterparty</span>
            <p className="mt-1 text-[11.5px] text-mist-600">
              Stored in the active company only. Names are unique per company.
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Close form"
            onClick={() => setOpen(false)}
          >
            <X className="size-4" aria-hidden />
          </Button>
        </div>

        {error ? <Alert variant="danger">{error}</Alert> : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="counterparty-name">Name</Label>
            <Input
              id="counterparty-name"
              value={values.name}
              onChange={(event) => update("name", event.target.value)}
              placeholder="Acme Metals Ltd"
              maxLength={160}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="counterparty-type">Type</Label>
            <Select
              id="counterparty-type"
              value={values.type}
              onChange={(event) => update("type", event.target.value)}
            >
              {COUNTERPARTY_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="counterparty-country">Country</Label>
            <Input
              id="counterparty-country"
              value={values.country}
              onChange={(event) => update("country", event.target.value)}
              placeholder="GB"
              maxLength={2}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="counterparty-contact">Contact name</Label>
            <Input
              id="counterparty-contact"
              value={values.contact_name}
              onChange={(event) => update("contact_name", event.target.value)}
              maxLength={120}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="counterparty-email">Email</Label>
            <Input
              id="counterparty-email"
              type="email"
              value={values.email}
              onChange={(event) => update("email", event.target.value)}
              placeholder="trading@acme.example"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="counterparty-phone">Phone</Label>
            <Input
              id="counterparty-phone"
              value={values.phone}
              onChange={(event) => update("phone", event.target.value)}
              maxLength={40}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="counterparty-notes">Notes</Label>
          <Textarea
            id="counterparty-notes"
            value={values.notes}
            onChange={(event) => update("notes", event.target.value)}
            maxLength={2000}
            placeholder="Payment terms, incoterms, history…"
          />
        </div>

        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" disabled={pending}>
            {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
            {pending ? "Saving…" : "Create counterparty"}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </form>
    );
  }
}
