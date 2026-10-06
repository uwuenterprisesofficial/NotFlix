import type { Metadata } from "next";
import { Geist, Nunito, Oswald } from "next/font/google";
import { I18nProvider } from "@/components/I18nProvider";
import { Navbar } from "@/components/Navbar";
import { TogetherSessions } from "@/components/together/Session";
import { cookies } from "next/headers";
import { apiOrNull } from "@/lib/api";
import { DESIGN_COOKIE, isDesign } from "@/lib/design";
import { getLang } from "@/lib/i18n/server";
import type { Me } from "@/lib/types";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});
// Only the designs that use them load them (see globals.css).
const oswald = Oswald({ variable: "--font-oswald", subsets: ["latin"], preload: false });
const nunito = Nunito({ variable: "--font-nunito", subsets: ["latin"], preload: false });

export const metadata: Metadata = {
  title: "NotFlix",
  description: "Your anime, Netflix style — synced with MyAnimeList.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const lang = await getLang();
  // Backend down: signed out (the page itself shows the error).
  const me = await apiOrNull<Me>("/me").catch(() => null);
  const chosen = (await cookies()).get(DESIGN_COOKIE)?.value;
  const design = isDesign(chosen) ? chosen : "standard";
  return (
    <html
      lang={lang}
      data-design={design}
      className={`${geistSans.variable} ${oswald.variable} ${nunito.variable} h-full`}
    >
      <body className="flex min-h-full flex-col">
        <I18nProvider lang={lang}>
          {/* Watch Together: invitations anywhere, and the active session's room (the
              players follow it, and this side follows the partner's episode). */}
          <TogetherSessions me={me?.id ?? null}>
            <Navbar />
            <main className="flex-1">{children}</main>
          </TogetherSessions>
        </I18nProvider>
      </body>
    </html>
  );
}
