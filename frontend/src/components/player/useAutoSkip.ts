import { useSyncExternalStore } from "react";

const KEY = "notflix:autoskip";
const EVENT = "notflix:autoskip-change";

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** Per-browser "skip intros/outros automatically" preference. */
export function useAutoSkip(): [boolean, (value: boolean) => void] {
  const value = useSyncExternalStore(subscribe, read, () => false);
  const set = (next: boolean) => {
    try {
      localStorage.setItem(KEY, next ? "1" : "0");
    } catch {
      // Storage unavailable (private mode); the toggle just won't persist.
    }
    window.dispatchEvent(new Event(EVENT));
  };
  return [value, set];
}
