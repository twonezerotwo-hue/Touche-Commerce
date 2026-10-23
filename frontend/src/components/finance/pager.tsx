import Link from "next/link";

import { withQuery } from "@/lib/trade/format";

/** Offset pager for lists that return `total`, `limit` and `offset`. */
export function Pager({
  basePath,
  total,
  limit,
  offset,
  params,
  noun = "row",
}: {
  basePath: string;
  total: number;
  limit: number;
  offset: number;
  params: Record<string, string | null | undefined>;
  noun?: string;
}) {
  const previous = offset > 0 ? Math.max(0, offset - limit) : null;
  const next = offset + limit < total ? offset + limit : null;
  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-between gap-3 text-[10.5px] text-mist-500"
    >
      <span>
        {total} {noun}
        {total === 1 ? "" : "s"} · offset {offset}
      </span>
      <div className="flex items-center gap-2">
        {previous !== null ? (
          <Link
            href={withQuery(basePath, { ...params, offset: String(previous) })}
            className="rounded border border-white/10 px-2.5 py-1 hover:text-mist-200"
          >
            Previous
          </Link>
        ) : null}
        {next !== null ? (
          <Link
            href={withQuery(basePath, { ...params, offset: String(next) })}
            className="rounded border border-white/10 px-2.5 py-1 hover:text-mist-200"
          >
            Next
          </Link>
        ) : null}
      </div>
    </nav>
  );
}
