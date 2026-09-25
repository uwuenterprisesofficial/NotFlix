"use client";

import { useEffect, useState } from "react";
import { useT } from "./I18nProvider";

type Text = { language: string; synopsis: string | null };

// One lookup per show and language per visit.
const found = new Map<string, Promise<Text>>();

function load(animeId: number, lang: string): Promise<Text> {
  const key = `${animeId}:${lang}`;
  let request = found.get(key);
  if (!request) {
    request = fetch(`/api/anime/${animeId}/synopsis?lang=${lang}`).then((res) =>
      res.ok ? res.json() : Promise.reject(new Error(String(res.status))),
    );
    request.catch(() => found.delete(key));
    found.set(key, request);
  }
  return request;
}

/**
 * A show's synopsis in the UI's language when there is one (German comes from AniWorld and
 * may take a moment the first time), else MAL's English one.
 */
export function Synopsis({
  animeId,
  text,
  language,
  className,
  note = false,
}: {
  animeId: number;
  text: string | null;
  /** The language `text` is in. */
  language: string;
  className?: string;
  /** Say so when no translation exists (detail page). */
  note?: boolean;
}) {
  const { t, lang } = useT();
  const wanted = lang !== "en" && language !== lang;
  const [result, setResult] = useState<Text | null>(null);

  useEffect(() => {
    if (!wanted) return;
    let cancelled = false;
    load(animeId, lang)
      .then((r) => !cancelled && setResult(r))
      .catch(() => !cancelled && setResult({ language: "en", synopsis: null }));
    return () => {
      cancelled = true;
    };
  }, [animeId, lang, wanted]);

  const shown = wanted && result?.language === lang ? result.synopsis : text;
  if (!shown) return null;
  return (
    <>
      <p className={className} lang={wanted && result?.language === lang ? lang : language}>
        {shown}
      </p>
      {note && wanted && (
        <p className="mt-2 text-xs text-muted">
          {result === null
            ? t("detail.synopsisLoading")
            : result.language !== lang && t("detail.synopsisEnglish")}
        </p>
      )}
    </>
  );
}
