import { LOCKUP_VIEWBOX, LOCKUP_WORD_X, MARK_LIGHTS, MARK_SCREEN, WORDMARK } from "@/lib/logo";

/**
 * The NotFlix logo (brand/): the Catchlight mark in the design's brand colour, and the NOTFLIX
 * wordmark in the current text colour (so each design colours it). `symbol` shows the mark alone.
 */
export function Logo({ className, symbol = false }: { className?: string; symbol?: boolean }) {
  return (
    <svg
      viewBox={symbol ? "20 46 216 164" : LOCKUP_VIEWBOX}
      className={className}
      role="img"
      aria-label="NotFlix"
    >
      <path d={MARK_SCREEN} fill="var(--color-brand)" />
      <path d={MARK_LIGHTS} fill="#fff" />
      {!symbol && (
        <path transform={`translate(${LOCKUP_WORD_X} 0)`} d={WORDMARK} fill="currentColor" />
      )}
    </svg>
  );
}
