"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowUpRight, Menu, X } from "lucide-react";

import { Avatar } from "@/components/ui/avatar";
import { useLocale } from "@/lib/i18n/locale-provider";
import { localizeNavigation } from "@/lib/i18n/navigation-labels";
import { NAV_GROUPS, PUBLIC_NAV_ITEMS, resolveActiveHref } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export interface MobileIdentity {
  displayName: string;
  email: string;
  companyName: string | null;
  role: string | null;
}

/** Slide-over navigation for screens below the desktop breakpoint. */
export function MobileNav({ identity }: { identity: MobileIdentity }) {
  const pathname = usePathname();
  const { t, locale } = useLocale();
  const translated = (label: string): string => localizeNavigation(locale, label);
  const activeHref = resolveActiveHref(pathname);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="lg:hidden">
      <button
        type="button"
        aria-label={t("openNavigation")}
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className="flex size-9 items-center justify-center rounded-md border border-white/10 text-mist-300 transition-colors hover:border-accent-400/40 hover:text-mist-100"
      >
        <Menu className="size-4" aria-hidden />
      </button>

      {open ? (
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            aria-label={t("closeNavigation")}
            className="absolute inset-0 bg-ink-950/80 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <nav
            aria-label={t("mobilePrimary")}
            className="absolute inset-y-0 left-0 flex w-[300px] max-w-[85vw] flex-col border-r border-white/10 bg-ink-900 shadow-2xl"
          >
            <div className="flex items-start justify-between px-5 pt-6 pb-5">
              <Link href="/" onClick={() => setOpen(false)} className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-lg border border-accent-400/35 bg-accent-400/10 font-display text-[15px] text-accent-200">
                  T
                </span>
                <span>
                  <span className="block font-display text-[15px] tracking-[0.2em] text-mist-100">
                    TOUCHE
                  </span>
                  <span className="mt-1 block text-[8.5px] tracking-[0.4em] text-accent-300">
                    COMMERCE
                  </span>
                </span>
              </Link>
              <button
                type="button"
                aria-label={t("closeNavigation")}
                onClick={() => setOpen(false)}
                className="flex size-8 items-center justify-center rounded-md text-mist-400 hover:bg-white/5 hover:text-mist-100"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
            <div className="hairline mx-5" />

            <div className="flex-1 overflow-y-auto px-3 py-5">
              {NAV_GROUPS.map((group) => (
                <div key={group.label} className="mb-5">
                  <p className="eyebrow px-3 pb-2">{translated(group.label)}</p>
                  <ul className="space-y-0.5">
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      if (!item.href) {
                        return (
                          <li key={item.label}>
                            <div
                              aria-disabled="true"
                              className="flex items-center gap-3 rounded-md px-3 py-2 text-[13px] text-mist-600"
                            >
                              <Icon className="size-4 text-mist-600/70" aria-hidden />
                              <span className="flex-1">{translated(item.label)}</span>
                              <span className="text-[9px] tracking-[0.14em] uppercase text-mist-600/80">
                                {item.stage}
                              </span>
                            </div>
                          </li>
                        );
                      }
                      const active = item.href === activeHref;
                      return (
                        <li key={item.label}>
                          <Link
                            href={item.href}
                            onClick={() => setOpen(false)}
                            aria-current={active ? "page" : undefined}
                            className={cn(
                              "flex items-center gap-3 rounded-md px-3 py-2 text-[13px] transition-colors",
                              active
                                ? "bg-accent-400/10 text-mist-100"
                                : "text-mist-300 hover:bg-white/[0.04] hover:text-mist-100",
                            )}
                          >
                            <Icon
                              className={cn("size-4", active ? "text-accent-300" : "text-mist-500")}
                              aria-hidden
                            />
                            <span className="flex-1">{translated(item.label)}</span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}

              <div className="mb-2">
                <p className="eyebrow px-3 pb-2">{t("platform")}</p>
                {PUBLIC_NAV_ITEMS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.label}
                      href={item.href ?? "/status"}
                      onClick={() => setOpen(false)}
                      className="flex items-center gap-3 rounded-md px-3 py-2 text-[13px] text-mist-300 hover:bg-white/[0.04] hover:text-mist-100"
                    >
                      <Icon className="size-4 text-mist-500" aria-hidden />
                      <span className="flex-1">{translated(item.label)}</span>
                      <ArrowUpRight className="size-3.5 text-mist-600" aria-hidden />
                    </Link>
                  );
                })}
              </div>
            </div>

            <div className="border-t border-white/[0.07] px-5 py-4">
              <Link
                href="/account"
                onClick={() => setOpen(false)}
                className="flex items-center gap-3"
              >
                <Avatar name={identity.displayName} size="sm" />
                <span className="min-w-0">
                  <span className="block truncate text-[12px] text-mist-200">
                    {identity.displayName}
                  </span>
                  <span className="block truncate text-[10.5px] text-mist-600">
                    {identity.companyName ?? identity.email}
                  </span>
                </span>
              </Link>
            </div>
          </nav>
        </div>
      ) : null}
    </div>
  );
}
