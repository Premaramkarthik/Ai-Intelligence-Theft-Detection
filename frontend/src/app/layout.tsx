import type { Metadata } from 'next';
import { Fira_Code, Fira_Sans } from 'next/font/google';
import './globals.css';
import QueryProvider from '@/components/providers/QueryProvider';

const firaCode = Fira_Code({
  variable: '--font-fira-code',
  subsets: ['latin'],
});

const firaSans = Fira_Sans({
  variable: '--font-fira-sans',
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
});

export const metadata: Metadata = {
  title: 'Antigravity Vision | AI Surveillance',
  description: 'High-performance AI-powered real-time detection dashboard.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${firaCode.variable} ${firaSans.variable} font-sans bg-slate-950 text-slate-50 antialiased`}
        suppressHydrationWarning
      >
        <QueryProvider>
          {children}
        </QueryProvider>
      </body>
    </html>
  );
}
