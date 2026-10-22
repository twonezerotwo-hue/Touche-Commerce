import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { cn } from "@/lib/utils";

export interface PageHeaderProps {
  eyebrow: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  back?: { href: string; label: string };
  className?: string;
}

/**
 * One composition for every workspace screen: context, a single H1, a short
 * explanation and the screen's primary actions.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  meta,
  back,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("animate-enter", className)}>
      {back ? (
        <Link
          href={back.href}
          className="mb-3 inline-flex items-center gap-1.5 text-[11px] text-mist-500 transition-colors hover:text-mist-200"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          {back.label}
        </Link>
      ) : null}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="max-w-2xl">
          <div className="flex flex-wrap items-center gap-3">
            <span className="eyebrow">{eyebrow}</span>
            {meta}
          </div>
          <h1 className="mt-2.5 font-display text-[26px] leading-[1.15] tracking-tight text-mist-100 lg:text-[30px]">
            {title}
          </h1>
          {description ? (
            <p className="mt-2 max-w-xl text-[12.5px] leading-relaxed text-mist-500">
              {description}
            </p>
          ) : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
