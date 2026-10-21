import type { Metadata } from "next";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { TopBar } from "@/components/shell/top-bar";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "TOUCHE COMMERCE — Command Center",
    template: "%s · TOUCHE COMMERCE",
  },
  description: "Independent, premium international trade management.",
  applicationName: "TOUCHE COMMERCE",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="dark">
      <body className="app-canvas min-h-screen">
        <div className="relative flex min-h-screen">
          <div
            className="hairline-grid pointer-events-none absolute inset-0 opacity-70"
            aria-hidden
          />
          <AppSidebar />
          <div className="relative flex min-w-0 flex-1 flex-col">
            <TopBar />
            <main className="flex-1 px-5 py-8 lg:px-10 lg:py-10">{children}</main>
            <footer className="border-t border-white/[0.06] px-5 py-4 lg:px-10">
              <div className="flex flex-wrap items-center justify-between gap-2 text-[10.5px] uppercase tracking-[0.18em] text-mist-600">
                <span>TOUCHE COMMERCE · Internal platform</span>
                <span>Stage 0 · foundation</span>
              </div>
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
