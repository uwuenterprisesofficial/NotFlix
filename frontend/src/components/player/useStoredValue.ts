import { useSyncExternalStore } from "react";

const EVENT = "notflix:storage-change";

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

/** A per-browser preference kept in localStorage, shared by every component that reads it. */
export function useStoredValue<T extends string>(key: string, fallback: T): [T, (v: T) => void] {
  const read = () => {
    try {
      return (localStorage.getItem(key) as T | null) ?? fallback;
    } catch {
      return fallback;
    }
  };
  const value = useSyncExternalStore(subscribe, read, () => fallback);
  const set = (next: T) => {
    try {
      localStorage.setItem(key, next);
    } catch {
      // Storage unavailable (private mode); the choice just won't persist.
    }
    window.dispatchEvent(new Event(EVENT));
  };
  return [value, set];
}
