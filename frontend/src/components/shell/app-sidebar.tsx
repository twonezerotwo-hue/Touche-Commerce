"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV_ITEMS, PUBLIC_NAV_ITEMS, isActivePath } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export interface ShellIdentity {
  displayName: string;
  email: string;
  companyName: string | null;
  role: string | null;
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "•";
}

export function AppSidebar({ identity }: { identity: ShellIdentity }) {
  const pathname = usePathname();

  return (
    <aside className="hidden w-[268px] shrink-0 flex-col border-r border-white/[0.06] bg-ink-900/60 lg:flex">
      <div className="px-6 pb-6 pt-7">
        <Link href="/" className="block">
          <span className="eyebrow block">Trade management</span>
          <span className="mt-2 block font-display text-[22px] leading-none tracking-[0.22em] text-mist-100">
            TOUCHE
          </span>
          <span className="mt-2 block text-[10.5px] tracking-[0.46em] text-gold-400">COMMERCE</span>
        </Link>
      </div>

      <div className="rule mx-6" />

      <nav aria-label="Primary" className="mt-6 flex-1 overflow-y-auto px-3 pb-6">
        <p className="eyebrow px-3 pb-3">Workspace</p>
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;

            if (item.href) {
              const isActive = isActivePath(pathname, item.href);
              return (
                <li key={item.label}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "group flex items-center gap-3 rounded-md px-3 py-2 text-[13px] transition-colors",
                      isActive
                        ? "bg-white/[0.055] text-mist-100"
                        : "text-mist-300 hover:bg-white/[0.04] hover:text-mist-100",
                    )}
                  >
                    <Icon
                      className={cn("size-4", isActive ? "text-gold-400" : "text-mist-500")}
                      aria-hidden
                    />
                    <span className="flex-1">{item.label}</span>
                    {isActive ? (
                      <span className="size-1.5 rounded-full bg-gold-400" aria-hidden />
                    ) : null}
                  </Link>
                </li>
              );
            }

            return (
              <li key={item.label}>
                <button
                  type="button"
                  disabled
                  title={`${item.label} — planned for ${item.stage}`}
                  className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-[13px] text-mist-600 disabled:cursor-not-allowed"
                >
                  <Icon className="size-4 text-mist-600/70" aria-hidden />
                  <span className="flex-1">{item.label}</span>
                  <span className="text-[9.5px] uppercase tracking-[0.14em] text-mist-600/80">
                    {item.stage}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        <p className="eyebrow px-3 pb-3 pt-6">Platform</p>
        <ul className="space-y-0.5">
          {PUBLIC_NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.label}>
                <Link
                  href={item.href ?? "/status"}
                  className="flex items-center gap-3 rounded-md px-3 py-2 text-[13px] text-mist-300 transition-colors hover:bg-white/[0.04] hover:text-mist-100"
                >
                  <Icon className="size-4 text-mist-500" aria-hidden />
                  <span className="flex-1">{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="px-6 pb-6">
        <div className="rule mb-4" />
        <div className="flex items-center gap-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-gold-400/30 bg-gold-400/10 font-display text-[11px] tracking-wider text-gold-200">
            {initialsOf(identity.displayName)}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[12px] text-mist-200">{identity.displayName}</p>
            <p className="truncate text-[10.5px] text-mist-600">{identity.email}</p>
          </div>
        </div>
        <p className="mt-3 text-[10.5px] leading-relaxed text-mist-600">
          {identity.companyName ?? "No company selected"}
          {identity.role ? (
            <>
              <br />
              <span className="uppercase tracking-[0.14em] text-mist-500">{identity.role}</span>
            </>
          ) : null}
        </p>
      </div>
    </aside>
  );
}
