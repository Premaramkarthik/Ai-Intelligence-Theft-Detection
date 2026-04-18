import type { Metadata } from "next";

import { Providers } from "@/app/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sentinel Deck",
  description: "Production-grade frontend for live CCTV streaming, tracking, and inference.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <Providers>
          <div className="min-h-screen bg-[var(--page-bg)]">
            <div className="mx-auto max-w-[1720px] px-4 py-5 sm:px-6 lg:px-8">
              {children}
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
