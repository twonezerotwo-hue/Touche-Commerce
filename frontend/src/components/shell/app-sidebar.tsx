"use client";

import Link from "next/link";

import { Avatar } from "@/components/ui/avatar";
import { NAV_GROUPS } from "@/lib/navigation";

import { SidebarNav } from "./sidebar-nav";

export interface AppSidebarProps {
  identity: {
    displayName: string;
    email: string;
    companyName: string | null;
    role: string | null;
  };
}

export function AppSidebar({ identity }: AppSidebarProps) {
  const available = NAV_GROUPS.filter((group) => group.items.some((item) => item.href));
  const roadmap = NAV_GROUPS.filter((group) => group.items.every((item) => !item.href));

  return (
    <aside className="relative z-20 hidden w-[252px] shrink-0 border-r border-white/[0.06] bg-ink-900/60 backdrop-blur-xl lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
      <div className="px-5 pt-6 pb-5">
        <Link
          href="/"
          className="group flex items-center gap-3"
          aria-label="TOUCHE COMMERCE — home"
        >
          <span className="relative flex size-9 items-center justify-center rounded-lg border border-accent-400/35 bg-gradient-to-b from-accent-400/20 to-accent-500/5 font-display text-[15px] text-accent-100 shadow-[0_10px_24px_-16px_rgb(47_127_232/0.9)]">
            T
            <span className="absolute -right-px -bottom-px size-1.5 rounded-full bg-accent-400 shadow-[0_0_10px_2px_rgb(90_162_255/0.35)]" />
          </span>
          <span className="min-w-0">
            <span className="block font-display text-[14.5px] leading-none tracking-[0.22em] text-mist-100">
              TOUCHE
            </span>
            <span className="mt-1.5 block text-[8.5px] leading-none tracking-[0.42em] text-accent-300">
              COMMERCE
            </span>
          </span>
        </Link>
      </div>

      <div className="hairline mx-5" />

      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3 py-5 [scrollbar-width:thin]">
        {available.map((group) => (
          <SidebarNav key={group.label} group={group} />
        ))}

        <div className="my-4 px-3">
          <div className="hairline" />
        </div>

        {roadmap.map((group) => (
          <SidebarNav key={group.label} group={group} muted />
        ))}
      </nav>

      <div className="border-t border-white/[0.06] px-4 py-4">
        <Link
          href="/account"
          className="flex items-center gap-3 rounded-lg border border-transparent px-1.5 py-1.5 transition-colors hover:border-white/[0.08] hover:bg-white/[0.025]"
        >
          <Avatar name={identity.displayName} size="sm" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12px] text-mist-200">{identity.displayName}</span>
            <span className="block truncate font-mono text-[10px] text-mist-600">
              {identity.companyName ?? identity.email}
            </span>
          </span>
        </Link>
        <div className="mt-3 flex items-center justify-between px-1.5">
          <span className="text-[9px] uppercase tracking-[0.18em] text-mist-600">
            {identity.role ? identity.role.replace(/_/g, " ") : "No membership"}
          </span>
          <span className="rounded-full border border-white/10 px-1.5 py-px text-[8.5px] tracking-[0.12em] text-mist-500">
            S2
          </span>
        </div>
      </div>
    </aside>
  );
}
