import { Alert } from "@/components/ui/alert";

/** A failed API read shown as a real error, never as an empty state. */
export function ApiErrorAlert({
  title,
  failure,
}: {
  title: string;
  failure: { code: string; message: string; requestId: string | null };
}) {
  return (
    <Alert variant="danger" title={title}>
      <span>{failure.message}</span>
      <span className="mt-1 block font-mono text-[10px] text-mist-500">
        {failure.code}
        {failure.requestId ? ` · request ${failure.requestId}` : ""}
      </span>
    </Alert>
  );
}
