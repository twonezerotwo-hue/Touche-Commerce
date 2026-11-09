"use client";

import Link from "next/link";

import { useLocale } from "@/lib/i18n/locale-provider";
import { withQuery } from "@/lib/trade/format";

const NOUNS = {
  row: ["pagerRowOne", "pagerRowMany"],
  order: ["pagerOrderOne", "pagerOrderMany"],
  exception: ["pagerExceptionOne", "pagerExceptionMany"],
} as const;

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
  noun?: keyof typeof NOUNS;
}) {
  const { t } = useLocale();
  const previous = offset > 0 ? Math.max(0, offset - limit) : null;
  const next = offset + limit < total ? offset + limit : null;
  const [one, many] = NOUNS[noun];
  return (
    <nav
      aria-label={t("pagerAria")}
      className="flex items-center justify-between gap-3 text-[10.5px] text-mist-500"
    >
      <span>{t(total === 1 ? one : many, { total, offset })}</span>
      <div className="flex items-center gap-2">
        {previous !== null ? (
          <Link
            href={withQuery(basePath, { ...params, offset: String(previous) })}
            className="rounded border border-white/10 px-2.5 py-1 hover:text-mist-200"
          >
            {t("pagePrevious")}
          </Link>
        ) : null}
        {next !== null ? (
          <Link
            href={withQuery(basePath, { ...params, offset: String(next) })}
            className="rounded border border-white/10 px-2.5 py-1 hover:text-mist-200"
          >
            {t("pageNext")}
          </Link>
        ) : null}
      </div>
    </nav>
  );
}
