"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Upload } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useLocale } from "@/lib/i18n/locale-provider";
import { documentTypeText } from "@/lib/i18n/value-labels";
import { uploadDocument } from "@/lib/operations/client";
import { formatBytes } from "@/lib/operations/format";
import { DOCUMENT_TYPES, type DocumentType, type LinkedEntityType } from "@/lib/operations/types";

const ACCEPTED = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "text/csv",
  "text/plain",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
];

/**
 * Upload a trade document to private storage.
 *
 * The client checks size and type for a fast, clear message; the API re-checks
 * both, generates the storage key and hashes the bytes. No client path is ever
 * used for storage.
 */
export function DocumentUpload({
  csrfToken,
  canWrite,
  maxBytes,
  entityType,
  entityId,
  entityLabel,
}: {
  csrfToken: string;
  canWrite: boolean;
  maxBytes: number;
  entityType: LinkedEntityType;
  entityId: string;
  entityLabel: string;
}) {
  const router = useRouter();
  const { t } = useLocale();
  const [documentType, setDocumentType] = useState<DocumentType>("DELIVERY_CONFIRMATION");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(): Promise<void> {
    setError(null);
    setNotice(null);
    if (!file) {
      setError(t("duaChooseFile"));
      return;
    }
    if (file.size > maxBytes) {
      setError(t("duaTooLarge", { size: formatBytes(file.size), max: formatBytes(maxBytes) }));
      return;
    }
    if (!ACCEPTED.includes(file.type)) {
      setError(t("duaBadType"));
      return;
    }

    const form = new FormData();
    form.set("document_type", documentType);
    form.set("linked_entity_type", entityType);
    form.set("linked_entity_id", entityId);
    form.set("title", title.trim() || file.name);
    form.set("file", file);

    setPending(true);
    const result = await uploadDocument(form, csrfToken);
    setPending(false);
    if (!result.ok) {
      setError(result.code === "PAYLOAD_TOO_LARGE" ? t("duaPayloadTooLarge") : result.message);
      return;
    }
    setFile(null);
    setTitle("");
    setNotice(
      t("duaStored", {
        version: result.data.version,
        size: formatBytes(result.data.size_bytes),
      }),
    );
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title={t("logReadOnly")}>
        {t("duaReadOnly")}
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="document-type">{t("duaType")}</Label>
          <Select
            id="document-type"
            value={documentType}
            onChange={(event) => setDocumentType(event.target.value as DocumentType)}
          >
            {DOCUMENT_TYPES.map((value) => (
              <option key={value} value={value}>
                {documentTypeText(t, value)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="document-title">{t("duaTitle")}</Label>
          <Input
            id="document-title"
            value={title}
            maxLength={200}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={t("duaTitlePlaceholder")}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="document-file">{t("duaFile")}</Label>
          <Input
            id="document-file"
            type="file"
            accept={ACCEPTED.join(",")}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <p className="text-[10px] text-mist-600">
            {t("duaHint", { entity: entityLabel, max: formatBytes(maxBytes) })}
          </p>
        </div>
      </div>

      <Button type="button" size="sm" disabled={pending} onClick={() => void submit()}>
        {pending ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <Upload className="size-3.5" aria-hidden />
        )}
        {pending ? t("duaUploading") : t("duaUpload")}
      </Button>
    </div>
  );
}
