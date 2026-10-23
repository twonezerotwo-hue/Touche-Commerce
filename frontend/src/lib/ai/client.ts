"use client";

import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import type {
  AiConversation,
  AiConversationDetail,
  AiProposal,
  AiRun,
  AiSendMessageResult,
} from "@/lib/ai/types";

export type AiResult<T> =
  | { ok: true; data: T; etag: string | null }
  | { ok: false; code: string; message: string; requestId: string | null };

interface RequestOptions {
  method: "GET" | "POST" | "PATCH";
  path: string;
  csrfToken?: string;
  body?: unknown;
  ifMatch?: string;
}

async function call<T>({
  method,
  path,
  csrfToken,
  body,
  ifMatch,
}: RequestOptions): Promise<AiResult<T>> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (method !== "GET") {
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
    headers["content-type"] = "application/json";
  }
  if (ifMatch) headers["If-Match"] = ifMatch;

  try {
    const response = await fetch(`${BROWSER_API_PREFIX}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
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
    return { ok: true, data: payload as T, etag: response.headers.get("etag") };
  } catch {
    return {
      ok: false,
      code: "UNREACHABLE",
      message: "Cannot reach the API. Confirm the service is running and try again.",
      requestId: null,
    };
  }
}

const etagOf = (version: number): string => `"v${version}"`;

export function createConversation(csrfToken: string): Promise<AiResult<AiConversation>> {
  return call({ method: "POST", path: "/ai/conversations", csrfToken, body: {} });
}

export function loadConversation(id: string): Promise<AiResult<AiConversationDetail>> {
  return call({ method: "GET", path: `/ai/conversations/${id}` });
}

export function sendMessage(
  conversationId: string,
  content: string,
  csrfToken: string,
): Promise<AiResult<AiSendMessageResult>> {
  return call({
    method: "POST",
    path: `/ai/conversations/${conversationId}/messages`,
    csrfToken,
    body: { content },
  });
}

export function loadRun(id: string): Promise<AiResult<AiRun>> {
  return call({ method: "GET", path: `/ai/runs/${id}` });
}

export function cancelRun(id: string, csrfToken: string): Promise<AiResult<AiRun>> {
  return call({ method: "POST", path: `/ai/runs/${id}/cancel`, csrfToken, body: {} });
}

export function loadProposals(): Promise<AiResult<{ items: AiProposal[] }>> {
  return call({ method: "GET", path: "/ai/proposals" });
}

export function loadActivity(): Promise<AiResult<{ items: AiRun[] }>> {
  return call({ method: "GET", path: "/ai/activity" });
}

export function editProposal(
  proposal: AiProposal,
  patch: { title?: string; body?: string; rationale?: string },
  csrfToken: string,
): Promise<AiResult<AiProposal>> {
  return call({
    method: "PATCH",
    path: `/ai/proposals/${proposal.id}`,
    csrfToken,
    body: patch,
    ifMatch: etagOf(proposal.version),
  });
}

export function decideProposal(
  proposal: AiProposal,
  decision: "approve" | "reject",
  options: { notes?: string; acknowledgeWarnings?: boolean },
  csrfToken: string,
): Promise<AiResult<AiProposal>> {
  return call({
    method: "POST",
    path: `/ai/proposals/${proposal.id}/${decision}`,
    csrfToken,
    body: {
      notes: options.notes || null,
      acknowledge_warnings: Boolean(options.acknowledgeWarnings),
    },
    ifMatch: etagOf(proposal.version),
  });
}
