import Link from "next/link";
import { ArrowUpRight, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { API_URLS } from "@/lib/api/config";

export function TopBar() {
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
          <span className="text-mist-200">Command Center</span>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <Badge variant="outline" className="hidden sm:inline-flex">
            <ShieldCheck className="size-3.5 text-gold-400" aria-hidden />
            Stage 0 · foundation
          </Badge>
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
