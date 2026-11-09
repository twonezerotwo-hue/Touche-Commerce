"use client";

import { useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import {
  exportFilename,
  intelligenceQuery,
  type IntelligenceFilters,
} from "@/lib/finance/intelligence";
import { useLocale } from "@/lib/i18n/locale-provider";

/**
 * Downloads the operational analysis CSV for the active filters. The export is
 * fetched rather than linked so a refusal (for example too many orders) is shown
 * here instead of being saved as a file containing the error JSON.
 */
export function ExportCsvButton({
  filters,
  orderCount,
}: {
  filters: IntelligenceFilters;
  orderCount?: number;
}) {
  const { t } = useLocale();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download(): Promise<void> {
    setPending(true);
    setError(null);
    try {
      const query = intelligenceQuery(filters);
      const response = await fetch(
        `${BROWSER_API_PREFIX}/finance/intelligence/export${query ? `?${query}` : ""}`,
        {
          headers: { accept: "text/csv, application/json" },
          credentials: "same-origin",
          cache: "no-store",
        },
      );
      if (!response.ok) {
        const payload: unknown = await response.json().catch(() => null);
        const envelope = parseErrorEnvelope(payload);
        const requestId = envelope?.error.request_id ?? response.headers.get("x-request-id");
        setError(
          `${envelope?.error.message ?? t("expFailedFallback")} (${
            envelope?.error.code ?? `HTTP_${response.status}`
          }${requestId ? ` · ${t("expRequest", { id: requestId })}` : ""})`,
        );
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = exportFilename(
        response.headers.get("content-disposition"),
        `touche-operational-financial-analysis-${new Date().toISOString().slice(0, 10).replaceAll("-", "")}.csv`,
      );
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError(t("expUnreachable"));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={pending}
        onClick={() => void download()}
      >
        {pending ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <Download className="size-3.5" aria-hidden />
        )}
        {t("expExport")}
        {typeof orderCount === "number" ? (
          <span className="font-mono text-[10px] text-mist-500">
            {t(orderCount === 1 ? "intOrdersOne" : "intOrdersMany", { count: orderCount })}
          </span>
        ) : null}
      </Button>
      {error ? (
        <Alert variant="danger" title={t("expFailedTitle")}>
          {error}
        </Alert>
      ) : null}
    </div>
  );
}
