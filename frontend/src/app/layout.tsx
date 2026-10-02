import type { Metadata } from "next";
import { Comfortaa } from "next/font/google";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";
import "./globals.css";

// Geist/Geist Mono были в стартовом шаблоне Next.js, но сайт нигде не
// использует font-sans/font-mono (body — Arial, см. globals.css) — шрифты
// грузились впустую, убраны.
const comfortaa = Comfortaa({
  variable: "--font-comfortaa",
  weight: ["600", "700"],
  subsets: ["latin", "cyrillic"],
});

export const metadata: Metadata = {
  title: {
    default: "Mirada Studio",
    template: "%s — Mirada Studio",
  },
  description: "Студия фламенко: расписание, абонементы и запись на занятия.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ru"
      className={`${comfortaa.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <div className="site-backdrop" aria-hidden="true" />
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
