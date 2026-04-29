import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Vigil — Adverse-media screening for Canadian gov funding",
  description:
    "Real-time adverse-media + forensic-signals screening for organizations receiving Canadian federal, provincial, and CRA-charity funding.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans bg-[var(--background)] text-[var(--foreground)]">
        <header className="border-b border-[var(--border)] bg-[var(--accent)] text-white">
          <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3">
              <span className="font-mono text-xs uppercase tracking-[0.25em] text-white/60">
                Agency 26 / Ottawa
              </span>
              <span className="h-4 w-px bg-white/30" aria-hidden />
              <span className="text-xl font-semibold tracking-tight">Vigil</span>
              <span className="hidden sm:inline text-xs font-medium uppercase tracking-wider rounded-sm border border-white/30 px-1.5 py-0.5 text-white/80">
                Beta
              </span>
            </Link>
            <nav className="hidden sm:flex items-center gap-5 text-sm text-white/80">
              <Link href="/" className="hover:text-white">Dashboard</Link>
              <a
                href="https://github.com/canlii/API_documentation"
                target="_blank"
                rel="noreferrer noopener"
                className="hover:text-white"
              >
                Sources
              </a>
              <span className="font-mono text-xs text-white/50">v0.1</span>
            </nav>
          </div>
        </header>
        <main className="flex-1">
          <div className="mx-auto max-w-7xl px-6 py-8">{children}</div>
        </main>
        <footer className="border-t border-[var(--border)] bg-white">
          <div className="mx-auto max-w-7xl px-6 py-5 flex flex-col sm:flex-row sm:justify-between gap-2 text-xs text-[var(--muted)]">
            <span>
              Vigil &middot; built for the Agency 2026 Ottawa hackathon, April 29 2026 &middot; Challenge #10 Adverse Media Screening
            </span>
            <span>
              Data: BigQuery · OpenSanctions · CanLII · Tavily · GDELT v2
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
