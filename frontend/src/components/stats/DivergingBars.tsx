"use client";

import { useT } from "@/components/I18nProvider";
import { formatNumber, type Lang } from "@/lib/i18n";
import { ABOVE, AXIS, BELOW } from "./colors";

export type DivergingItem = { name: string; value: number; detail?: string };

const signed = (lang: Lang, v: number, digits = 2) =>
  `${v >= 0 ? "+" : "−"}${formatNumber(lang, Math.abs(v), digits)}`;

/**
 * Horizontal bars growing left (below) or right (above) from a zero line, value labelled. When
 * every value has the same sign the zero line moves to the left edge, so no half stays empty.
 */
export function DivergingBars({ items, unit = "" }: { items: DivergingItem[]; unit?: string }) {
  const { lang } = useT();
  const peak = Math.max(0.01, ...items.map((i) => Math.abs(i.value)));
  const oneSided = items.every((i) => i.value >= 0) || items.every((i) => i.value < 0);
  const half = oneSided ? 100 : 50;
  const zero = oneSided ? 0 : 50;
  return (
    <ul className="space-y-1.5">
      {items.map((item) => {
        const width = (Math.abs(item.value) / peak) * half;
        const above = item.value >= 0;
        return (
          <li
            key={item.name}
            className="grid grid-cols-[minmax(0,9rem)_1fr_3.5rem] items-center gap-3 text-sm"
            title={item.detail}
          >
            <span className="truncate text-right text-neutral-200">{item.name}</span>
            <span className="relative h-4">
              <span
                className="absolute inset-y-[-3px] w-px"
                style={{ background: AXIS, left: `${zero}%` }}
              />
              <span
                className={`absolute top-0 h-full ${above || oneSided ? "rounded-r" : "rounded-l"}`}
                style={{
                  background: above ? ABOVE : BELOW,
                  width: `${width}%`,
                  left: above || oneSided ? `${zero}%` : `${zero - width}%`,
                }}
              />
            </span>
            <span className="text-neutral-200 tabular-nums">
              {signed(lang, item.value)}
              {unit}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
