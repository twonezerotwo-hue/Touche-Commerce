"use client";

import Link from "next/link";
import { ExternalLink, FileSearch } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  BASIS_META,
  PRIORITY_TONE,
  basisLabels,
  describeWarningIn,
  entityWords,
  priorityLabel,
  safeSourceHref,
} from "@/lib/ai/format";
import type { AiBasis, AiEvidence, AiMessage } from "@/lib/ai/types";
import { useLocale } from "@/lib/i18n/locale-provider";

export function BasisBadge({ basis }: { basis: AiBasis }) {
  const { t } = useLocale();
  const meta = BASIS_META[basis];
  const words = basisLabels(t, basis);
  return (
    <Badge variant={meta.tone} title={words.meaning} data-basis={basis}>
      {words.label}
    </Badge>
  );
}

function EvidenceChips({
  ids,
  byId,
}: {
  ids: readonly string[];
  byId: ReadonlyMap<string, AiEvidence>;
}) {
  const { t } = useLocale();
  const items = ids.map((id) => byId.get(id)).filter((e): e is AiEvidence => Boolean(e));
  if (items.length === 0) return null;
  return (
    <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label={t("aiSourcesAria")}>
      {items.map((item) => {
        const href = safeSourceHref(item);
        const content = (
          <>
            <span className="font-mono text-[10px] text-mist-500">{item.id}</span>
            <span className="max-w-[16rem] truncate">{item.reference}</span>
          </>
        );
        const base =
          "inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-[11px] text-mist-300";
        return (
          <li key={item.id}>
            {href ? (
              <Link
                href={href}
                className={`${base} transition-colors hover:border-accent-400/40 hover:text-mist-100`}
                aria-label={t("aiOpenSource", {
                  reference: item.reference,
                  type: entityWords(item.entity_type),
                })}
              >
                {content}
                <ExternalLink className="size-3 text-mist-500" aria-hidden />
              </Link>
            ) : (
              <span className={base}>{content}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function WarningList({ codes }: { codes: readonly string[] }) {
  const { t } = useLocale();
  if (codes.length === 0) return null;
  return (
    <ul className="mt-1.5 space-y-0.5">
      {codes.map((code) => (
        <li key={code} className="text-[11px] leading-relaxed text-amber-400">
          {describeWarningIn(t, code)}
        </li>
      ))}
    </ul>
  );
}

/** The validated answer: every claim carries its basis and the records behind it. */
export function AnswerView({ message }: { message: AiMessage }) {
  const { t } = useLocale();
  const answer = message.structured;
  const byId = new Map(message.evidence.map((item) => [item.id, item] as const));

  if (!answer) {
    return <p className="text-[13px] leading-relaxed text-mist-200">{message.content}</p>;
  }

  const draftCount = answer.drafts.length;
  const taskCount = answer.task_proposals.length;
  return (
    <div className="space-y-4">
      {answer.summary ? (
        <p className="text-[13px] leading-relaxed text-mist-100">{answer.summary}</p>
      ) : null}

      {answer.warnings.length > 0 ? (
        <div className="rounded-md border border-amber-400/25 bg-amber-400/[0.05] px-3 py-2">
          <p className="text-[11px] font-medium text-amber-400">{t("aiCheckedByServer")}</p>
          <WarningList codes={answer.warnings} />
        </div>
      ) : null}

      {answer.findings.length > 0 ? (
        <section aria-label={t("aiFindings")}>
          <p className="eyebrow mb-2">{t("aiFindings")}</p>
          <ol className="space-y-3">
            {answer.findings.map((finding, index) => (
              <li key={`${index}-${finding.claim}`} className="panel-inset p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="min-w-0 flex-1 text-[12.5px] leading-relaxed text-mist-100">
                    {finding.claim}
                  </p>
                  <BasisBadge basis={finding.basis} />
                </div>
                {finding.figures.length > 0 ? (
                  <dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2">
                    {finding.figures.map((figure) => (
                      <div
                        key={`${figure.label}-${figure.value}`}
                        className="flex justify-between gap-3"
                      >
                        <dt className="text-[11px] text-mist-500">{figure.label}</dt>
                        <dd className="font-mono text-[11.5px] text-mist-200">
                          {figure.value}
                          {figure.currency ? ` ${figure.currency}` : ""}
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
                <EvidenceChips ids={finding.evidence} byId={byId} />
                <WarningList codes={finding.warnings} />
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {answer.recommendations.length > 0 ? (
        <section aria-label={t("aiNextSteps")}>
          <p className="eyebrow mb-2">{t("aiNextSteps")}</p>
          <ul className="space-y-2.5">
            {answer.recommendations.map((item, index) => (
              <li key={`${index}-${item.action}`} className="panel-inset p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-[12.5px] leading-relaxed text-mist-100">{item.action}</p>
                  <Badge variant={PRIORITY_TONE[item.priority] ?? "secondary"}>
                    {priorityLabel(t, item.priority)}
                  </Badge>
                </div>
                {item.rationale ? (
                  <p className="mt-1 text-[11.5px] leading-relaxed text-mist-400">
                    {item.rationale}
                  </p>
                ) : null}
                <EvidenceChips ids={item.evidence} byId={byId} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {answer.missing_inputs.length > 0 ? (
        <section aria-label={t("aiMissing")}>
          <p className="eyebrow mb-2">{t("aiMissing")}</p>
          <ul className="space-y-1.5">
            {answer.missing_inputs.map((item, index) => (
              <li key={`${index}-${item.item}`} className="text-[12px] text-mist-300">
                {item.item}
                <EvidenceChips ids={item.evidence} byId={byId} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {draftCount + taskCount > 0 ? (
        <p className="text-[11.5px] text-mist-400">
          {t("aiProposedPre", {
            drafts: t(draftCount === 1 ? "aiDraftsOne" : "aiDraftsMany", { count: draftCount }),
            tasks: t(taskCount === 1 ? "aiTasksOne" : "aiTasksMany", { count: taskCount }),
          })}{" "}
          <span className="text-mist-200">{t("aiProposedLink")}</span>
          {t("aiProposedPost")}
        </p>
      ) : null}

      <SourceList items={message.evidence} />
    </div>
  );
}

export function SourceList({ items }: { items: readonly AiEvidence[] }) {
  const { t } = useLocale();
  if (items.length === 0) {
    return <p className="text-[11px] text-mist-500">{t("aiNoSources")}</p>;
  }
  return (
    <details className="group panel-inset">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[11.5px] text-mist-300 hover:text-mist-100">
        <FileSearch className="size-3.5 text-mist-500" aria-hidden />
        {t("aiSourcesCount", { count: items.length })}
        <span className="ml-auto text-[10.5px] text-mist-500 group-open:hidden">{t("aiShow")}</span>
      </summary>
      <ul className="divide-y divide-white/5 border-t border-white/5">
        {items.map((item) => {
          const href = safeSourceHref(item);
          return (
            <li key={item.id} className="space-y-1 px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] text-mist-500">{item.id}</span>
                {href ? (
                  <Link href={href} className="text-[12px] text-accent-300 hover:text-accent-200">
                    {item.reference}
                  </Link>
                ) : (
                  <span className="text-[12px] text-mist-200">{item.reference}</span>
                )}
                <BasisBadge basis={item.basis} />
                <span className="text-[10.5px] text-mist-500">
                  {item.completeness.toLowerCase()}
                </span>
              </div>
              <p className="text-[11.5px] text-mist-400">{item.label}</p>
              <p className="text-[10.5px] text-mist-500">
                {t("aiReadBy", {
                  type: entityWords(item.entity_type),
                  tool: item.tool,
                  asOf: item.as_of ? t("aiAsOf", { date: item.as_of.slice(0, 10) }) : "",
                })}
              </p>
              <WarningList codes={item.warnings} />
            </li>
          );
        })}
      </ul>
    </details>
  );
}
