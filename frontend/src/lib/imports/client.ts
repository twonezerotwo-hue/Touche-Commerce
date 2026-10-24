"use client";

import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

export type ImportKind = Schemas["InspectResponse"]["kind"];
export type ImportInspect = Schemas["InspectResponse"];
export type ImportReport = Schemas["ImportReportResponse"];
export type ImportRow = Schemas["ImportRowResponse"];
export type ImportCommit = Schemas["ImportCommitResponse"];
export type ImportBatch = Schemas["ImportBatchResponse"];
export type ImportBatchList = Schemas["ImportBatchListResponse"];

export type ImportResult<T> =
  { ok: true; data: T } | { ok: false; code: string; message: string; requestId: string | null };

async function post<T>(
  path: string,
  fields: Record<string, string>,
  file: File,
  csrfToken: string,
): Promise<ImportResult<T>> {
  const body = new FormData();
  for (const [name, value] of Object.entries(fields)) body.append(name, value);
  body.append("file", file, file.name);
  try {
    // No content-type header: the browser adds the multipart boundary itself.
    const response = await fetch(`${BROWSER_API_PREFIX}/imports/${path}`, {
      method: "POST",
      headers: { accept: "application/json", "X-CSRF-Token": csrfToken },
      body,
      credentials: "same-origin",
      cache: "no-store",
    });
    const payload: unknown = await response.json().catch(() => null);
    const requestId = response.headers.get("x-request-id");
    if (!response.ok) {
      const envelope = parseErrorEnvelope(payload);
      return {
        ok: false,
        code: envelope?.error.code ?? `HTTP_${response.status}`,
        message: envelope?.error.message ?? "The request could not be completed.",
        requestId: envelope?.error.request_id ?? requestId,
      };
    }
    return { ok: true, data: payload as T };
  } catch {
    return {
      ok: false,
      code: "UNREACHABLE",
      message: "Cannot reach the API. Confirm the service is running and try again.",
      requestId: null,
    };
  }
}

export function inspectImport(
  kind: ImportKind,
  file: File,
  csrfToken: string,
): Promise<ImportResult<ImportInspect>> {
  return post("inspect", { kind }, file, csrfToken);
}

export function previewImport(
  kind: ImportKind,
  file: File,
  mapping: Record<string, string>,
  csrfToken: string,
): Promise<ImportResult<ImportReport>> {
  return post("preview", { kind, mapping: JSON.stringify(mapping) }, file, csrfToken);
}

export function commitImport(
  kind: ImportKind,
  file: File,
  mapping: Record<string, string>,
  expectedSha256: string,
  skipExisting: boolean,
  csrfToken: string,
): Promise<ImportResult<ImportCommit>> {
  return post(
    "commit",
    {
      kind,
      mapping: JSON.stringify(mapping),
      expected_sha256: expectedSha256,
      skip_existing: String(skipExisting),
    },
    file,
    csrfToken,
  );
}

/** A header-only CSV the operator can fill in (UTF-8 with BOM so Excel reads Turkish text). */
export function templateCsv(kind: ImportKind): string {
  const lines =
    kind === "products"
      ? ["sku,name,unit,currency,unit_price", "EXAMPLE-001,Example product,kg,USD,1.2500"]
      : [
          "name,type,country,contact_name,email,phone,notes",
          "Example Foods Ltd,supplier,TR,Ayşe Yılmaz,sales@example.com,+90 212 000 00 00,",
        ];
  return `﻿${lines.join("\r\n")}\r\n`;
}
