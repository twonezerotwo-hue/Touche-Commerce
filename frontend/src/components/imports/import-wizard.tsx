"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { CheckCircle2, Download, FileSpreadsheet, Loader2, Upload } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  commitImport,
  inspectImport,
  previewImport,
  templateCsv,
  type ImportCommit,
  type ImportInspect,
  type ImportKind,
  type ImportReport,
  type ImportResult,
} from "@/lib/imports/client";
import { useLocale } from "@/lib/i18n/locale-provider";
import type { MessageKey } from "@/lib/i18n/messages";
import { cn } from "@/lib/utils";

type Step = "file" | "mapping" | "review" | "done";

const STATUS_BADGE = {
  NEW: { key: "importStatusNew", variant: "success" },
  EXISTS: { key: "importStatusExists", variant: "secondary" },
  INVALID: { key: "importStatusInvalid", variant: "danger" },
} as const satisfies Record<
  string,
  { key: MessageKey; variant: "success" | "secondary" | "danger" }
>;

const MAX_ROWS_SHOWN = 100;

export function ImportWizard({ csrfToken, canWrite }: { csrfToken: string; canWrite: boolean }) {
  const { t } = useLocale();
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [kind, setKind] = useState<ImportKind>("products");
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>("file");
  const [inspect, setInspect] = useState<ImportInspect | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [report, setReport] = useState<ImportReport | null>(null);
  const [skipExisting, setSkipExisting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<ImportCommit | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset(): void {
    setFile(null);
    setStep("file");
    setInspect(null);
    setMapping({});
    setReport(null);
    setSkipExisting(false);
    setConfirmed(false);
    setResult(null);
    setError(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  function fail<T>(outcome: ImportResult<T>): void {
    if (!outcome.ok) setError(`${outcome.message} (${outcome.code})`);
  }

  async function readFile(): Promise<void> {
    setError(null);
    if (!file) {
      setError(t("importNoFile"));
      return;
    }
    setPending(true);
    const outcome = await inspectImport(kind, file, csrfToken);
    setPending(false);
    if (!outcome.ok) return fail(outcome);
    setInspect(outcome.data);
    setMapping(
      Object.fromEntries(
        outcome.data.headers.flatMap((h) => (h.field ? [[h.heading, h.field]] : [])),
      ),
    );
    setStep("mapping");
  }

  async function runPreview(): Promise<void> {
    if (!file) return;
    setError(null);
    setPending(true);
    const outcome = await previewImport(kind, file, mapping, csrfToken);
    setPending(false);
    if (!outcome.ok) return fail(outcome);
    setReport(outcome.data);
    setConfirmed(false);
    setSkipExisting(false);
    setStep("review");
  }

  async function runCommit(): Promise<void> {
    if (!file || !report) return;
    setError(null);
    setPending(true);
    const outcome = await commitImport(
      kind,
      file,
      mapping,
      report.source_sha256,
      skipExisting,
      csrfToken,
    );
    setPending(false);
    if (!outcome.ok) return fail(outcome);
    setResult(outcome.data);
    setStep("done");
  }

  function downloadTemplate(): void {
    const blob = new Blob([templateCsv(kind)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `touche-${kind}-template.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!canWrite) return <Alert variant="info">{t("importReadOnly")}</Alert>;

  const steps: { id: Step; label: MessageKey }[] = [
    { id: "file", label: "importStepFile" },
    { id: "mapping", label: "importStepMapping" },
    { id: "review", label: "importStepReview" },
    { id: "done", label: "importStepDone" },
  ];
  const stepIndex = steps.findIndex((s) => s.id === step);
  const required = new Set(inspect?.required ?? []);
  const mapped = new Set(Object.values(mapping));
  const missing = [...required].filter((field) => !mapped.has(field));
  const canImport =
    report !== null &&
    report.invalid_rows === 0 &&
    report.new_rows > 0 &&
    !report.already_imported &&
    (report.existing_rows === 0 || skipExisting) &&
    confirmed;

  return (
    <div className="space-y-4">
      <ol className="flex flex-wrap gap-2" aria-label="Steps">
        {steps.map((item, index) => (
          <li
            key={item.id}
            aria-current={index === stepIndex ? "step" : undefined}
            className={cn(
              "rounded-md border px-3 py-1.5 text-[11.5px]",
              index === stepIndex
                ? "border-accent-400/40 bg-accent-400/10 text-mist-100"
                : index < stepIndex
                  ? "border-jade-400/25 text-jade-400"
                  : "border-white/10 text-mist-500",
            )}
          >
            {t(item.label)}
          </li>
        ))}
      </ol>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {step === "file" ? (
        <section className="panel space-y-4 p-5" aria-label={t("importStepFile")}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="import-kind">{t("importKindLabel")}</Label>
              <Select
                id="import-kind"
                value={kind}
                onChange={(event) => setKind(event.target.value as ImportKind)}
              >
                <option value="products">{t("importKindProducts")}</option>
                <option value="counterparties">{t("importKindCounterparties")}</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="import-file">{t("importChooseFile")}</Label>
              <input
                id="import-file"
                ref={fileInput}
                type="file"
                accept=".csv,.xlsx"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="block w-full text-[12px] text-mist-300 file:mr-3 file:rounded-md file:border file:border-white/10 file:bg-white/[0.04] file:px-3 file:py-1.5 file:text-[11.5px] file:text-mist-200"
              />
            </div>
          </div>
          <p className="text-[11.5px] leading-relaxed text-mist-500">{t("importSafetyNote")}</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => void readFile()} disabled={pending}>
              {pending ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
              ) : (
                <Upload className="size-3.5" aria-hidden />
              )}
              {t("importReadFile")}
            </Button>
            <Button type="button" variant="outline" onClick={downloadTemplate}>
              <Download className="size-3.5" aria-hidden />
              {t("importTemplate")}
            </Button>
          </div>
        </section>
      ) : null}

      {step === "mapping" && inspect ? (
        <section className="panel space-y-4 p-5" aria-label={t("importMappingTitle")}>
          <div>
            <h2 className="font-display text-[17px] text-mist-100">{t("importMappingTitle")}</h2>
            <p className="mt-1 text-[12px] leading-relaxed text-mist-500">
              {t("importMappingHint")}
            </p>
          </div>
          <table className="w-full text-left text-[12px]">
            <thead className="text-[10.5px] tracking-[0.06em] text-mist-500 uppercase">
              <tr>
                <th className="pb-2 font-medium">{t("importMappingHeading")}</th>
                <th className="pb-2 font-medium">{t("importMappingField")}</th>
              </tr>
            </thead>
            <tbody>
              {inspect.headers.map((header) => (
                <tr key={header.heading} className="border-t border-white/5">
                  <td className="py-2 pr-3 font-mono text-mist-200">{header.heading || "—"}</td>
                  <td className="py-2">
                    <Select
                      aria-label={`${t("importMappingField")}: ${header.heading}`}
                      value={mapping[header.heading] ?? ""}
                      onChange={(event) =>
                        setMapping((current) => {
                          const next = { ...current };
                          if (event.target.value) next[header.heading] = event.target.value;
                          else delete next[header.heading];
                          return next;
                        })
                      }
                    >
                      <option value="">{t("importMappingUnmapped")}</option>
                      {inspect.fields.map((field) => (
                        <option key={field} value={field}>
                          {field}
                        </option>
                      ))}
                    </Select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className={cn("text-[11.5px]", missing.length ? "text-amber-400" : "text-mist-500")}>
            {t("importMappingRequired", { fields: inspect.required.join(", ") })}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              onClick={() => void runPreview()}
              disabled={pending || missing.length > 0}
            >
              {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
              {t("importPreviewButton")}
            </Button>
            <Button type="button" variant="ghost" onClick={reset}>
              {t("importBack")}
            </Button>
          </div>
        </section>
      ) : null}

      {step === "review" && report ? (
        <section className="panel space-y-4 p-5" aria-label={t("importStepReview")}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[13px] text-mist-100" role="status">
              {t("importSummary", {
                total: report.total_rows,
                created: report.new_rows,
                existing: report.existing_rows,
                invalid: report.invalid_rows,
              })}
            </p>
            <p className="font-mono text-[10px] text-mist-500">
              {t("importFingerprint")}: {report.source_sha256.slice(0, 12)}
            </p>
          </div>

          {report.already_imported ? <Alert variant="warning">{t("importAlready")}</Alert> : null}
          {report.invalid_rows > 0 ? (
            <Alert variant="danger">{t("importBlockedInvalid")}</Alert>
          ) : null}
          {report.invalid_rows === 0 && report.new_rows === 0 && !report.already_imported ? (
            <Alert variant="info">{t("importNothingNew")}</Alert>
          ) : null}

          <div className="max-h-[22rem] overflow-auto rounded-md border border-white/8">
            <table className="w-full text-left text-[12px]">
              <thead className="sticky top-0 bg-ink-900 text-[10.5px] tracking-[0.06em] text-mist-500 uppercase">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("columnRow")}</th>
                  <th className="px-3 py-2 font-medium">{t("columnStatus")}</th>
                  {Object.keys(report.rows[0]?.values ?? {}).map((field) => (
                    <th key={field} className="px-3 py-2 font-medium">
                      {field}
                    </th>
                  ))}
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {report.rows.slice(0, MAX_ROWS_SHOWN).map((row) => {
                  const badge = STATUS_BADGE[row.status];
                  return (
                    <tr key={row.row} className="border-t border-white/5">
                      <td className="px-3 py-2 font-mono text-mist-400">{row.row}</td>
                      <td className="px-3 py-2">
                        <Badge variant={badge.variant}>{t(badge.key)}</Badge>
                      </td>
                      {Object.keys(report.rows[0]?.values ?? {}).map((field) => (
                        <td key={field} className="px-3 py-2 text-mist-200">
                          {row.values[field] ?? ""}
                        </td>
                      ))}
                      <td className="px-3 py-2 text-[11px] text-amber-400">
                        {row.errors.join(" · ")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {report.rows.length > MAX_ROWS_SHOWN ? (
            <p className="text-[11px] text-mist-500">
              {t("importRowsShown", { shown: MAX_ROWS_SHOWN, total: report.rows.length })}
            </p>
          ) : null}

          {report.existing_rows > 0 ? (
            <label className="flex items-start gap-2 text-[12px] leading-relaxed text-mist-300">
              <input
                type="checkbox"
                className="mt-0.5 size-3.5 accent-accent-400"
                checked={skipExisting}
                onChange={(event) => setSkipExisting(event.target.checked)}
              />
              {t("importSkipExisting")}
            </label>
          ) : null}
          {report.existing_rows > 0 && !skipExisting && report.invalid_rows === 0 ? (
            <Alert variant="info">{t("importBlockedExisting")}</Alert>
          ) : null}
          <label className="flex items-start gap-2 text-[12px] leading-relaxed text-mist-300">
            <input
              type="checkbox"
              className="mt-0.5 size-3.5 accent-accent-400"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            {t("importConfirm")}
          </label>

          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => void runCommit()} disabled={pending || !canImport}>
              {pending ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
              ) : (
                <FileSpreadsheet className="size-3.5" aria-hidden />
              )}
              {t("importCommit", { count: report.new_rows })}
            </Button>
            <Button type="button" variant="ghost" onClick={reset} disabled={pending}>
              {t("importBack")}
            </Button>
          </div>
        </section>
      ) : null}

      {step === "done" && result ? (
        <section className="panel space-y-4 p-5" aria-label={t("importStepDone")}>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="size-5 text-jade-400" aria-hidden />
            <h2 className="font-display text-[17px] text-mist-100">{t("importDoneTitle")}</h2>
          </div>
          <p className="text-[13px] text-mist-200" role="status">
            {result.replayed
              ? t("importDoneReplayed")
              : t("importDoneCounts", {
                  created: result.created_rows,
                  skipped: result.skipped_rows,
                })}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button asChild>
              <Link href={result.kind === "products" ? "/products" : "/crm"}>
                {result.kind === "products"
                  ? t("importViewProducts")
                  : t("importViewCounterparties")}
              </Link>
            </Button>
            <Button type="button" variant="outline" onClick={reset}>
              {t("importAnother")}
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
