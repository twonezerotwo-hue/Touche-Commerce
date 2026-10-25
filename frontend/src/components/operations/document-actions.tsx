"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Archive, BadgeCheck, Loader2, XCircle } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/i18n/locale-provider";
import { archiveDocument, verifyDocument } from "@/lib/operations/client";
import type { TradeDocument } from "@/lib/operations/types";

/** Verification and controlled archival of one document version. */
export function DocumentActions({
  document,
  csrfToken,
  canWrite,
}: {
  document: TradeDocument;
  csrfToken: string;
  canWrite: boolean;
}) {
  const router = useRouter();
  const { t } = useLocale();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canWrite) return null;

  async function run(action: "verify" | "reject" | "archive"): Promise<void> {
    setPending(true);
    setError(null);
    const result =
      action === "archive"
        ? await archiveDocument(document.id, "Archived from the document register", csrfToken)
        : await verifyDocument(
            document.id,
            action === "verify" ? "VERIFIED" : "REJECTED",
            null,
            csrfToken,
          );
    setPending(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {error ? <Alert variant="danger">{error}</Alert> : null}
      {document.status === "ACTIVE" ? (
        <>
          <Button
            type="button"
            size="xs"
            variant="ghost"
            disabled={pending}
            onClick={() => void run("verify")}
            title={t("dactVerifyTitle")}
          >
            {pending ? (
              <Loader2 className="size-3 animate-spin" aria-hidden />
            ) : (
              <BadgeCheck className="size-3" aria-hidden />
            )}
            {t("dactVerify")}
          </Button>
          <Button
            type="button"
            size="xs"
            variant="ghost"
            disabled={pending}
            onClick={() => void run("reject")}
            title={t("dactRejectTitle")}
          >
            <XCircle className="size-3" aria-hidden />
            {t("dactReject")}
          </Button>
          <Button
            type="button"
            size="xs"
            variant="ghost"
            disabled={pending}
            onClick={() => void run("archive")}
            title={t("dactArchiveTitle")}
          >
            <Archive className="size-3" aria-hidden />
            {t("dactArchive")}
          </Button>
        </>
      ) : (
        <span className="text-[10px] text-mist-600">{t("opStatusArchived")}</span>
      )}
    </div>
  );
}
