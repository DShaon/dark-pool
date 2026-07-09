import type { Metadata } from "next";
import { Geist_Mono, Noto_Sans_Bengali, Space_Grotesk } from "next/font/google";
import "./globals.css";

// Brand voice — Space Grotesk: geometric, futuristic, comfortable to read at a
// glance. Titles/verdict use its bold weight, large (ADR-0013 typography
// amendment; italics dropped per owner review — bold display, never italic).
const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  weight: ["300", "400", "500"],
});

// Bengali secondary voice — subtitles + glossary tooltips (user amendment).
const notoBengali = Noto_Sans_Bengali({
  variable: "--font-noto-bengali",
  subsets: ["bengali"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "DARKPOOL — AI Trading Desk",
  description:
    "Institutional-grade AI trading intelligence: deterministic market engine, mandate-based analyst panel, Claude as CIO.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${geistMono.variable} ${notoBengali.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
