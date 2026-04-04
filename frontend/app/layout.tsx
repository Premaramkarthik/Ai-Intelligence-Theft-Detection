import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sentinel Deck",
  description: "Production-grade CCTV control and playback console.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body
        suppressHydrationWarning
        className="min-h-full bg-background text-foreground"
      >
        <div className="relative min-h-screen overflow-hidden">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(45,212,191,0.12),_transparent_30%),radial-gradient(circle_at_top_right,_rgba(56,189,248,0.18),_transparent_32%),radial-gradient(circle_at_bottom_right,_rgba(251,191,36,0.10),_transparent_28%)]" />
          <div className="pointer-events-none absolute inset-0 opacity-[0.12] [background-image:linear-gradient(rgba(148,163,184,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.08)_1px,transparent_1px)] [background-size:72px_72px]" />
          <div className="relative mx-auto flex min-h-screen w-full max-w-[1680px] flex-col px-4 py-6 sm:px-6 lg:px-10">
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}
