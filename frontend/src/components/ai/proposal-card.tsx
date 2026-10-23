"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckCircle2, Loader2, Lock, Pencil, XCircle } from "lucide-react";

import { BasisBadge } from "@/components/ai/answer-view";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { decideProposal, editProposal } from "@/lib/ai/client";
import {
  DRAFT_KIND_LABEL,
  PRIORITY_TONE,
  describeError,
  describeWarning,
  safeSourceHref,
} from "@/lib/ai/format";
import type { AiProposal } from "@/lib/ai/types";

const STATUS_TONE = { PROPOSED: "warning", APPROVED: "success", REJECTED: "secondary" } as const;
const STATUS_LABEL = {
  PROPOSED: "Awaiting a person",
  APPROVED: "Approved",
  REJECTED: "Rejected",
} as const;

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function ProposalCard({
  proposal,
  csrfToken,
  canDecide,
  onChanged,
}: {
  proposal: AiProposal;
  csrfToken: string;
  canDecide: boolean;
  onChanged: (updated: AiProposal) => void;
}) {
  const payload = proposal.payload;
  const isDraft = proposal.kind === "DRAFT";
  const pending = proposal.status === "PROPOSED";
  const needsAcknowledgement = proposal.warnings.includes("UNVERIFIED_NUMBER");

  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(str(payload.title) || proposal.title);
  const [body, setBody] = useState(isDraft ? str(payload.body) : str(payload.rationale));
  const [notes, setNotes] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState<"save" | "approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(): Promise<void> {
    setBusy("save");
    setError(null);
    const result = await editProposal(
      proposal,
      isDraft ? { title, body } : { title, rationale: body },
      csrfToken,
    );
    setBusy(null);
    if (!result.ok) {
      setError(describeError(result.code, result.message));
      return;
    }
    setEditing(false);
    onChanged(result.data);
  }

  async function decide(decision: "approve" | "reject"): Promise<void> {
    setBusy(decision);
    setError(null);
    const result = await decideProposal(
      proposal,
      decision,
      { notes, acknowledgeWarnings: acknowledged },
      csrfToken,
    );
    setBusy(null);
    if (!result.ok) {
      setError(describeError(result.code, result.message));
      return;
    }
    onChanged(result.data);
  }

  const target = payload.target as { entity_type?: string; entity_id?: string } | null | undefined;

  return (
    <article
      className="panel-inset space-y-3 p-3.5"
      aria-label={`${isDraft ? "Draft" : "Task"}: ${proposal.title}`}
      data-proposal-status={proposal.status}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">
              {isDraft ? (DRAFT_KIND_LABEL[str(payload.kind)] ?? "Draft") : "Suggested task"}
            </Badge>
            {!isDraft && str(payload.priority) ? (
              <Badge variant={PRIORITY_TONE[str(payload.priority)] ?? "secondary"}>
                {str(payload.priority).toLowerCase()}
              </Badge>
            ) : null}
            {proposal.edited ? <Badge variant="info">Edited</Badge> : null}
          </div>
          <h3 className="mt-1.5 text-[13px] font-medium text-mist-100">{proposal.title}</h3>
        </div>
        <Badge variant={STATUS_TONE[proposal.status]} dot>
          {STATUS_LABEL[proposal.status]}
        </Badge>
      </header>

      {editing ? (
        <div className="space-y-2">
          <div className="space-y-1">
            <Label htmlFor={`title-${proposal.id}`}>Title</Label>
            <Input
              id={`title-${proposal.id}`}
              value={title}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`body-${proposal.id}`}>{isDraft ? "Draft text" : "Rationale"}</Label>
            <Textarea
              id={`body-${proposal.id}`}
              value={body}
              rows={isDraft ? 8 : 4}
              maxLength={isDraft ? 6000 : 1200}
              onChange={(event) => setBody(event.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <Button type="button" size="xs" onClick={() => void save()} disabled={busy !== null}>
              {busy === "save" ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
              Save wording
            </Button>
            <Button
              type="button"
              size="xs"
              variant="ghost"
              onClick={() => setEditing(false)}
              disabled={busy !== null}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : isDraft ? (
        <div>
          <p className="eyebrow mb-1">Preview — not sent</p>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-md border border-white/8 bg-ink-950/60 p-3 font-sans text-[12px] leading-relaxed text-mist-200">
            {str(payload.body)}
          </pre>
        </div>
      ) : (
        <div className="space-y-1">
          {str(payload.rationale) ? (
            <p className="text-[12px] leading-relaxed text-mist-300">{str(payload.rationale)}</p>
          ) : null}
          {target?.entity_type ? (
            <p className="text-[11px] text-mist-500">
              Refers to {target.entity_type.replaceAll("_", " ").toLowerCase()}
            </p>
          ) : null}
        </div>
      )}

      {proposal.evidence.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="Evidence">
          {proposal.evidence.map((item) => {
            const href = safeSourceHref(item);
            return (
              <li key={item.id} className="flex items-center gap-1.5">
                {href ? (
                  <Link className="text-[11px] text-accent-300 hover:text-accent-200" href={href}>
                    {item.reference}
                  </Link>
                ) : (
                  <span className="text-[11px] text-mist-300">{item.reference}</span>
                )}
                <BasisBadge basis={item.basis} />
              </li>
            );
          })}
        </ul>
      ) : null}

      {proposal.warnings.length > 0 ? (
        <ul className="space-y-0.5">
          {proposal.warnings.map((code) => (
            <li key={code} className="text-[11px] text-amber-400">
              {describeWarning(code)}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="text-[11px] leading-relaxed text-mist-500">{proposal.effect_summary}</p>

      {proposal.status !== "PROPOSED" ? (
        <p className="text-[11px] text-mist-400">
          {proposal.status === "APPROVED" ? "Approved" : "Rejected"} by a person
          {proposal.decided_at ? ` on ${proposal.decided_at.slice(0, 10)}` : ""}
          {proposal.decision_notes ? ` — “${proposal.decision_notes}”` : ""}.
        </p>
      ) : null}

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {pending && !editing ? (
        canDecide ? (
          <div className="space-y-2.5 border-t border-white/5 pt-3">
            {needsAcknowledgement ? (
              <label className="flex items-start gap-2 text-[11.5px] leading-relaxed text-amber-400">
                <input
                  type="checkbox"
                  className="mt-0.5 size-3.5 accent-amber-400"
                  checked={acknowledged}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                />
                I reviewed the unverified figures in this text.
              </label>
            ) : null}
            <div className="space-y-1">
              <Label htmlFor={`notes-${proposal.id}`}>Decision note (optional)</Label>
              <Input
                id={`notes-${proposal.id}`}
                value={notes}
                maxLength={2000}
                onChange={(event) => setNotes(event.target.value)}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => void decide("approve")}
                disabled={busy !== null || (needsAcknowledgement && !acknowledged)}
              >
                {busy === "approve" ? (
                  <Loader2 className="size-3.5 animate-spin" aria-hidden />
                ) : (
                  <CheckCircle2 className="size-3.5" aria-hidden />
                )}
                {isDraft ? "Approve wording" : "Approve task"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setEditing(true)}
                disabled={busy !== null}
              >
                <Pencil className="size-3.5" aria-hidden />
                Edit
              </Button>
              <Button
                type="button"
                size="sm"
                variant="danger"
                onClick={() => void decide("reject")}
                disabled={busy !== null}
              >
                {busy === "reject" ? (
                  <Loader2 className="size-3.5 animate-spin" aria-hidden />
                ) : (
                  <XCircle className="size-3.5" aria-hidden />
                )}
                Reject
              </Button>
            </div>
          </div>
        ) : (
          <p className="flex items-center gap-1.5 border-t border-white/5 pt-3 text-[11px] text-mist-500">
            <Lock className="size-3" aria-hidden />
            Your role can read proposals but cannot approve, edit or reject them.
          </p>
        )
      ) : null}
    </article>
  );
}
