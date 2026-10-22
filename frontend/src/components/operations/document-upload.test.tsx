import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentUpload } from "./document-upload";

const refreshMock = vi.fn();
const uploadMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/lib/operations/client", () => ({
  uploadDocument: (...args: unknown[]) => uploadMock(...args),
}));

function pdf(size = 32): File {
  return new File([new Uint8Array(size)], "pod.pdf", { type: "application/pdf" });
}

describe("DocumentUpload", () => {
  beforeEach(() => {
    refreshMock.mockReset();
    uploadMock.mockReset();
  });

  it("explains read-only access instead of offering an upload", () => {
    render(
      <DocumentUpload
        csrfToken="csrf"
        canWrite={false}
        maxBytes={1024}
        entityType="SALES_ORDER"
        entityId="order-1"
        entityLabel="order SO-1"
      />,
    );

    expect(screen.getByText(/Read-only access/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Upload document/i })).not.toBeInTheDocument();
  });

  it("rejects a file above the configured limit before calling the API", async () => {
    const user = userEvent.setup();
    render(
      <DocumentUpload
        csrfToken="csrf"
        canWrite
        maxBytes={8}
        entityType="SALES_ORDER"
        entityId="order-1"
        entityLabel="order SO-1"
      />,
    );

    await user.upload(screen.getByLabelText(/File/i), pdf(64));
    await user.click(screen.getByRole("button", { name: /Upload document/i }));

    expect(await screen.findByText(/the limit is 8 B/i)).toBeInTheDocument();
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("rejects a content type outside the allow-list", async () => {
    const user = userEvent.setup();
    render(
      <DocumentUpload
        csrfToken="csrf"
        canWrite
        maxBytes={4096}
        entityType="SALES_ORDER"
        entityId="order-1"
        entityLabel="order SO-1"
      />,
    );

    const html = new File(["<html></html>"], "payload.html", { type: "text/html" });
    const input = screen.getByLabelText(/File/i);
    // Bypass the input's `accept` filter to prove the component itself refuses it.
    fireEvent.change(input, { target: { files: [html] } });
    await user.click(screen.getByRole("button", { name: /Upload document/i }));

    expect(await screen.findByText(/content type is not accepted/i)).toBeInTheDocument();
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("submits the server-required form fields and reports the stored version", async () => {
    const user = userEvent.setup();
    uploadMock.mockResolvedValue({
      ok: true,
      etag: '"v1"',
      data: {
        id: "doc-1",
        version: 1,
        size_bytes: 32,
        sha256: "abc",
      },
    });

    render(
      <DocumentUpload
        csrfToken="csrf"
        canWrite
        maxBytes={4096}
        entityType="SALES_ORDER"
        entityId="order-1"
        entityLabel="order SO-1"
      />,
    );

    await user.upload(screen.getByLabelText(/File/i), pdf());
    await user.click(screen.getByRole("button", { name: /Upload document/i }));

    await waitFor(() => expect(uploadMock).toHaveBeenCalledTimes(1));
    const [form, csrf] = uploadMock.mock.calls[0] as [FormData, string];
    expect(csrf).toBe("csrf");
    expect(form.get("document_type")).toBe("DELIVERY_CONFIRMATION");
    expect(form.get("linked_entity_type")).toBe("SALES_ORDER");
    expect(form.get("linked_entity_id")).toBe("order-1");
    expect(form.get("file")).toBeInstanceOf(File);
    expect(await screen.findByText(/Stored as version 1/i)).toBeInTheDocument();
    expect(refreshMock).toHaveBeenCalled();
  });
});
