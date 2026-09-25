import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { I18nProvider } from "@/components/I18nProvider";
import { Navbar } from "@/components/Navbar";
import { getLang } from "@/lib/i18n/server";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "NotFlix",
  description: "Your anime, Netflix style — synced with MyAnimeList.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const lang = await getLang();
  return (
    <html lang={lang} className={`${geistSans.variable} h-full`}>
      <body className="flex min-h-full flex-col">
        <I18nProvider lang={lang}>
          <Navbar />
          <main className="flex-1">{children}</main>
        </I18nProvider>
      </body>
    </html>
  );
}
