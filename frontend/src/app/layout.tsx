import type { Metadata } from "next";
import { Bodoni_Moda, IBM_Plex_Mono, Inter } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";

const bodyFont = Inter({
  subsets: ["latin"],
  variable: "--font-body-stack",
});

const displayFont = Inter({
  subsets: ["latin"],
  variable: "--font-display-stack",
});

const wordmarkFont = Bodoni_Moda({
  subsets: ["latin"],
  variable: "--font-wordmark-stack",
  weight: ["600", "700"],
});

const monoFont = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono-stack",
});

export const metadata: Metadata = {
  title: "OpenMedium",
  description: "A minimal wizard for discovering Medium articles and exporting PDFs.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${displayFont.variable} ${bodyFont.variable} ${wordmarkFont.variable} ${monoFont.variable} h-full antialiased dark`}
      style={{ colorScheme: "dark" }}
    >
      <body className="min-h-full flex flex-col bg-black text-white selection:bg-white selection:text-black">
        {children}
        <Toaster theme="dark" position="bottom-right" />
      </body>
    </html>
  );
}
