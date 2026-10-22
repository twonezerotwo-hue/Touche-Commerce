"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Upload } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
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
      setError("Choose a file to upload.");
      return;
    }
    if (file.size > maxBytes) {
      setError(`This file is ${formatBytes(file.size)}; the limit is ${formatBytes(maxBytes)}.`);
      return;
    }
    if (!ACCEPTED.includes(file.type)) {
      setError(
        "That content type is not accepted. Use PDF, PNG, JPEG, CSV, plain text, DOCX or XLSX.",
      );
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
      setError(
        result.code === "PAYLOAD_TOO_LARGE"
          ? "The upload is larger than the configured limit."
          : result.message,
      );
      return;
    }
    setFile(null);
    setTitle("");
    setNotice(`Stored as version ${result.data.version} (${formatBytes(result.data.size_bytes)}).`);
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title="Read-only access">
        Uploading requires <span className="font-mono">trade.write</span>.
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="document-type">Document type</Label>
          <Select
            id="document-type"
            value={documentType}
            onChange={(event) => setDocumentType(event.target.value as DocumentType)}
          >
            {DOCUMENT_TYPES.map((value) => (
              <option key={value} value={value}>
                {value.replaceAll("_", " ").toLowerCase()}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="document-title">Title (optional)</Label>
          <Input
            id="document-title"
            value={title}
            maxLength={200}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Signed proof of delivery"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="document-file">File</Label>
          <Input
            id="document-file"
            type="file"
            accept={ACCEPTED.join(",")}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <p className="text-[10px] text-mist-600">
            Attached to {entityLabel}. Maximum {formatBytes(maxBytes)}. Files are stored privately
            and served only through an authorised download.
          </p>
        </div>
      </div>

      <Button type="button" size="sm" disabled={pending} onClick={() => void submit()}>
        {pending ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <Upload className="size-3.5" aria-hidden />
        )}
        {pending ? "Uploading…" : "Upload document"}
      </Button>
    </div>
  );
}
