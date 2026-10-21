import Link from "next/link";

import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export function AppSidebar() {
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
              const isActive = item.href === "/";
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
      </nav>

      <div className="px-6 pb-6">
        <div className="rule mb-4" />
        <p className="text-[11px] leading-relaxed text-mist-600">
          Foundation build
          <br />
          <span className="text-mist-500">Stage 0 · infrastructure only</span>
        </p>
      </div>
    </aside>
  );
}
