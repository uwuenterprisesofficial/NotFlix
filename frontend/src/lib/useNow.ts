import { useSyncExternalStore } from "react";

const MINUTE = 60_000;

function subscribe(onChange: () => void) {
  const timer = setInterval(onChange, MINUTE);
  return () => clearInterval(timer);
}

// Rounded to the minute, so the snapshot stays the same between renders.
const now = () => Math.floor(Date.now() / MINUTE) * MINUTE;

/** The current time (updated every minute) in the browser; null while rendering on the
 * server, so relative times ("5 h ago") don't mismatch between server and browser. */
export function useNow(): number | null {
  return useSyncExternalStore(subscribe, now, () => null);
}
