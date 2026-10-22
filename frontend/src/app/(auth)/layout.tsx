import Link from "next/link";
import { Activity, ArrowRight, ShieldCheck } from "lucide-react";

export const metadata = { title: "Sign in" };

const ASSURANCES = [
  "Server-side sessions with hashed tokens and rotation",
  "Argon2id password verification and login rate limiting",
  "Company isolation enforced by PostgreSQL row level security",
  "Append-only audit trail for every security action",
] as const;

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen">
      <div className="hairline-grid pointer-events-none absolute inset-0 opacity-70" aria-hidden />
      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-10">
        <header className="flex items-center justify-between">
          <div>
            <span className="block font-display text-[20px] leading-none tracking-[0.22em] text-mist-100">
              TOUCHE
            </span>
            <span className="mt-1.5 block text-[9.5px] tracking-[0.44em] text-accent-400">
              COMMERCE
            </span>
          </div>
          <Link
            href="/status"
            className="inline-flex items-center gap-1.5 text-[11px] text-mist-500 transition-colors hover:text-mist-200"
          >
            <Activity className="size-3.5" aria-hidden />
            System status
          </Link>
        </header>

        <div className="grid flex-1 items-center gap-12 py-10 lg:grid-cols-[1.05fr_0.95fr]">
          <section className="hidden max-w-md lg:block">
            <span className="eyebrow">Private workspace</span>
            <h1 className="mt-3 font-display text-[34px] leading-[1.14] tracking-tight text-mist-100">
              International trade,
              <br />
              under one accountable roof.
            </h1>
            <p className="mt-4 text-[13px] leading-relaxed text-mist-500">
              TOUCHE COMMERCE consolidates deals, documents and settlement for licensed trading
              entities. Access is scoped to your company membership — nothing else is reachable from
              a session.
            </p>

            <ul className="mt-8 space-y-3">
              {ASSURANCES.map((item) => (
                <li key={item} className="flex items-start gap-2.5 text-[12.5px] text-mist-400">
                  <ShieldCheck className="mt-[1px] size-4 shrink-0 text-accent-400" aria-hidden />
                  <span>{item}</span>
                </li>
              ))}
            </ul>

            <p className="mt-8 inline-flex items-center gap-1.5 text-[11px] text-mist-600">
              <ArrowRight className="size-3.5" aria-hidden />
              Accounts are provisioned by an administrator. Self-registration is not available.
            </p>
          </section>

          <section className="w-full max-w-md justify-self-center lg:justify-self-end">
            {children}
          </section>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 text-[10px] tracking-[0.18em] text-mist-600 uppercase">
          <span>TOUCHE COMMERCE · Internal platform</span>
          <span>Stage 2 · commerce interface</span>
        </footer>
      </div>
    </div>
  );
}
