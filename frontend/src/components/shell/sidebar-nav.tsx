"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useLocale } from "@/lib/i18n/locale-provider";
import { localizeNavigation } from "@/lib/i18n/navigation-labels";
import { resolveActiveHref, type NavGroup } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export interface SidebarNavProps {
  group: NavGroup;
  /** Roadmap groups render as non-interactive placeholders. */
  muted?: boolean;
}

export function SidebarNav({ group, muted = false }: SidebarNavProps) {
  const pathname = usePathname();
  const { locale } = useLocale();
  const activeHref = resolveActiveHref(pathname);

  return (
    <div className="mb-4 last:mb-0">
      <p className="eyebrow px-3 pb-2">{localizeNavigation(locale, group.label)}</p>
      <ul className="space-y-0.5">
        {group.items.map((item) => {
          const Icon = item.icon;

          if (!item.href) {
            return (
              <li key={item.label}>
                <div
                  aria-disabled="true"
                  title={`${item.description} — planned for ${item.stage}`}
                  className="flex items-center gap-2.5 rounded-md px-3 py-1.5 text-[12.5px] text-mist-600/85"
                >
                  <Icon className="size-[15px] shrink-0 text-mist-600/60" aria-hidden />
                  <span className="flex-1 truncate">{localizeNavigation(locale, item.label)}</span>
                  <span className="font-mono text-[8.5px] tracking-[0.08em] text-mist-600/70">
                    {item.stage.replace("Stage ", "S")}
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
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group relative flex items-center gap-2.5 rounded-md px-3 py-1.5 text-[12.5px] transition-all duration-200",
                  active
                    ? "bg-gradient-to-r from-accent-400/[0.14] to-accent-400/[0.02] text-mist-100"
                    : muted
                      ? "text-mist-500 hover:bg-white/[0.03] hover:text-mist-300"
                      : "text-mist-400 hover:bg-white/[0.035] hover:text-mist-100",
                )}
              >
                {active ? (
                  <span
                    className="absolute top-1/2 left-0 h-3.5 w-[2px] -translate-y-1/2 rounded-full bg-accent-400 shadow-[0_0_10px_rgb(90_162_255/0.6)]"
                    aria-hidden
                  />
                ) : null}
                <Icon
                  className={cn(
                    "size-[15px] shrink-0 transition-colors",
                    active ? "text-accent-300" : "text-mist-500 group-hover:text-mist-300",
                  )}
                  aria-hidden
                />
                <span className="flex-1 truncate">{localizeNavigation(locale, item.label)}</span>
                {active ? (
                  <span className="status-dot bg-accent-400" aria-hidden />
                ) : (
                  <span
                    className="h-px w-0 bg-transparent transition-all group-hover:w-2.5"
                    aria-hidden
                  />
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
