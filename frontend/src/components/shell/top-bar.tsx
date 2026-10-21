"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUpRight, Building2, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { API_URLS } from "@/lib/api/config";

const TITLES: Record<string, string> = {
  "/": "Command Center",
  "/account": "Account",
  "/select-company": "Select company",
  "/login": "Sign in",
  "/status": "System status",
};

function titleFor(pathname: string): string {
  if (TITLES[pathname]) return TITLES[pathname];
  const match = Object.keys(TITLES)
    .filter((path) => path !== "/" && pathname.startsWith(`${path}/`))
    .sort((a, b) => b.length - a.length)[0];
  return match ? TITLES[match] : "Workspace";
}

export function TopBar({
  companyName,
  role,
}: {
  companyName?: string | null;
  role?: string | null;
}) {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-ink-950/75 backdrop-blur">
      <div className="flex h-16 items-center gap-4 px-5 lg:px-10">
        <Link href="/" className="flex items-baseline gap-2 lg:hidden">
          <span className="font-display text-[15px] tracking-[0.2em] text-mist-100">TOUCHE</span>
          <span className="text-[9px] tracking-[0.34em] text-gold-400">COMMERCE</span>
        </Link>

        <nav aria-label="Breadcrumb" className="hidden items-center gap-2 text-[12px] lg:flex">
          <span className="text-mist-600">Workspace</span>
          <span className="text-mist-600">/</span>
          <span className="text-mist-200">{titleFor(pathname)}</span>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {companyName ? (
            <Badge variant="outline" className="hidden max-w-[240px] truncate sm:inline-flex">
              <Building2 className="size-3.5 text-gold-400" aria-hidden />
              <span className="truncate">{companyName}</span>
              {role ? (
                <span className="ml-1 text-[9.5px] uppercase tracking-[0.14em] text-mist-600">
                  {role}
                </span>
              ) : null}
            </Badge>
          ) : (
            <Badge variant="outline" className="hidden sm:inline-flex">
              <ShieldCheck className="size-3.5 text-gold-400" aria-hidden />
              Stage 1A · identity
            </Badge>
          )}
          <a
            href={API_URLS.docs}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-white/10 px-3 text-[11.5px] text-mist-300 transition-colors hover:border-gold-400/40 hover:text-mist-100"
          >
            API docs
            <ArrowUpRight className="size-3.5" aria-hidden />
          </a>
        </div>
      </div>
    </header>
  );
}
