import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "TOUCHE COMMERCE — Command Center",
    template: "%s · TOUCHE COMMERCE",
  },
  description: "Independent, premium international trade management.",
  applicationName: "TOUCHE COMMERCE",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="app-canvas min-h-screen">{children}</body>
    </html>
  );
}
