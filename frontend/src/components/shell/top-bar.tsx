"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Building2, ChevronRight, ShieldCheck } from "lucide-react";

import { Avatar } from "@/components/ui/avatar";
import { useLocale } from "@/lib/i18n/locale-provider";
import { localizeNavigation } from "@/lib/i18n/navigation-labels";
import { resolveWorkspaceContext } from "@/lib/navigation";
import { cn } from "@/lib/utils";

import { LocaleSwitcher } from "./locale-switcher";
import { MobileNav, type MobileIdentity } from "./mobile-nav";

export interface TopBarProps {
  identity: MobileIdentity;
}

export function TopBar({ identity }: TopBarProps) {
  const pathname = usePathname();
  const { t, locale } = useLocale();
  const { section, page } = resolveWorkspaceContext(pathname);

  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-ink-950/75 backdrop-blur-xl">
      <div className="flex h-14 items-center gap-3 px-4 lg:px-10">
        <MobileNav identity={identity} />

        <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-2 lg:flex">
          <span className="text-[11px] tracking-[0.02em] text-mist-600">{t("workspace")}</span>
          <ChevronRight className="size-3 text-mist-600/70" aria-hidden />
          <span className={cn("text-[11px]", page === section ? "text-mist-300" : "text-mist-500")}>
            {localizeNavigation(locale, section)}
          </span>
          {page === section ? null : (
            <>
              <ChevronRight className="size-3 text-mist-600/70" aria-hidden />
              <span className="truncate text-[11px] text-mist-200">{localizeNavigation(locale, page)}</span>
            </>
          )}
        </nav>

        <div className="min-w-0 lg:hidden">
          <p className="truncate text-[12px] text-mist-200">{page}</p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <LocaleSwitcher />
          <span className="hidden items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.02] px-2.5 py-1 text-[10px] text-mist-500 md:inline-flex">
            <ShieldCheck className="size-3 text-jade-400" aria-hidden />
            {t("sessionVerified")}
          </span>

          {identity.companyName ? (
            <span className="hidden max-w-[220px] items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.02] py-1 pr-3 pl-2 text-[10.5px] text-mist-400 sm:inline-flex">
              <Building2 className="size-3 text-mist-500" aria-hidden />
              <span className="truncate">{identity.companyName}</span>
              {identity.role ? (
                <span className="rounded-full bg-accent-400/10 px-1.5 py-px text-[9px] tracking-[0.08em] text-accent-300 uppercase">
                  {identity.role.replace(/_/g, " ")}
                </span>
              ) : null}
            </span>
          ) : null}

          <Link
            href="/status"
            aria-label={t("systemStatus")}
            title={t("systemStatus")}
            className="hidden size-8 items-center justify-center rounded-md text-mist-500 transition-colors hover:bg-white/[0.05] hover:text-mist-200 sm:flex"
          >
            <Activity className="size-3.5" aria-hidden />
          </Link>

          <span className="hidden h-4 w-px bg-white/10 sm:block" aria-hidden />

          <Link
            href="/account"
            aria-label={t("profileAccess")}
            className="rounded-full transition-opacity hover:opacity-85"
          >
            <Avatar name={identity.displayName} size="sm" />
          </Link>
        </div>
      </div>
    </header>
  );
}
