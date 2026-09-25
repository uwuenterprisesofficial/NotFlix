import { cookies, headers } from "next/headers";
import { LANG_COOKIE, fromAcceptLanguage, isLang, type Lang } from "./core";
import { translator } from "./index";

/** The UI language: chosen in Settings (a cookie), else the browser's. */
export async function getLang(): Promise<Lang> {
  const chosen = (await cookies()).get(LANG_COOKIE)?.value;
  if (isLang(chosen)) return chosen;
  return fromAcceptLanguage((await headers()).get("accept-language"));
}

export async function getT() {
  const lang = await getLang();
  return { lang, t: translator(lang) };
}
