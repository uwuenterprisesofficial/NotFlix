"use client";

import { airTime, relativeTime } from "@/lib/format";
import { useNow } from "@/lib/useNow";
import { useT } from "./I18nProvider";

/** An air time in the viewer's time zone ("Sat 27 Sep, 18:30 (in 2 days)"); rendered in the
 * browser only, since the server doesn't know the viewer's time zone. */
export function AirTime({ at }: { at: string }) {
  const { lang } = useT();
  const now = useNow();
  if (now === null) return null;
  return (
    <span suppressHydrationWarning>
      {airTime(lang, at)} ({relativeTime(lang, at, now)})
    </span>
  );
}
