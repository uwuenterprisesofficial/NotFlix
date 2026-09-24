import { useId } from "react";
import type { Language } from "@/lib/types";

// Drawn as SVG: flag emoji don't render on Windows.
function Germany() {
  return (
    <svg viewBox="0 0 5 3" aria-hidden className="h-full w-full">
      <rect width="5" height="1" fill="#000" />
      <rect y="1" width="5" height="1" fill="#DD0000" />
      <rect y="2" width="5" height="1" fill="#FFCE00" />
    </svg>
  );
}

function UnitedKingdom() {
  const id = useId();
  return (
    <svg viewBox="0 0 60 30" aria-hidden preserveAspectRatio="none" className="h-full w-full">
      <clipPath id={`${id}-s`}>
        <path d="M0,0 v30 h60 v-30 z" />
      </clipPath>
      <clipPath id={`${id}-t`}>
        <path d="M30,15 h30 v15 z v15 h-30 z h-30 v-15 z v-15 h30 z" />
      </clipPath>
      <g clipPath={`url(#${id}-s)`}>
        <path d="M0,0 v30 h60 v-30 z" fill="#012169" />
        <path d="M0,0 L60,30 M60,0 L0,30" stroke="#fff" strokeWidth="6" />
        <path
          d="M0,0 L60,30 M60,0 L0,30"
          clipPath={`url(#${id}-t)`}
          stroke="#C8102E"
          strokeWidth="4"
        />
        <path d="M30,0 v30 M0,15 h60" stroke="#fff" strokeWidth="10" />
        <path d="M30,0 v30 M0,15 h60" stroke="#C8102E" strokeWidth="6" />
      </g>
    </svg>
  );
}

/** The flag of a language's audio/subtitle language: German or English (a globe otherwise). */
export function LanguageFlag({ language }: { language: Language }) {
  const flag = language.startsWith("de") ? (
    <Germany />
  ) : language.startsWith("en") ? (
    <UnitedKingdom />
  ) : null;
  if (!flag) {
    return (
      <span aria-hidden className="inline-grid h-3.5 w-5 shrink-0 place-items-center text-xs">
        🌐
      </span>
    );
  }
  return (
    <span
      aria-hidden
      className="inline-block h-3.5 w-5 shrink-0 overflow-hidden rounded-[2px] ring-1 ring-white/20"
    >
      {flag}
    </span>
  );
}
