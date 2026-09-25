"use client";

import { useState } from "react";
import type { TagStat } from "@/lib/types";
import { YOU } from "./colors";
import { signed } from "./DivergingBars";

const KINDS: { kind: string; label: string }[] = [
  { kind: "genre", label: "Genres" },
  { kind: "theme", label: "Themes" },
  { kind: "demographic", label: "Demographics" },
  { kind: "studio", label: "Studios" },
  { kind: "source", label: "Source" },
  { kind: "type", label: "Type" },
  { kind: "era", label: "Decade" },
  { kind: "explicit", label: "Explicit" },
];

type SortKey = "count" | "mean_score" | "mal_mean" | "delta" | "affinity" | "name";
const COLUMNS: { key: SortKey; label: string; title: string }[] = [
  { key: "count", label: "Shows", title: "Shows on your list" },
  { key: "mean_score", label: "You", title: "Your average score" },
  { key: "mal_mean", label: "MAL", title: "MAL's average for the same shows" },
  { key: "delta", label: "vs MAL", title: "Your score minus MAL's, on average" },
  {
    key: "affinity",
    label: "Affinity",
    title: "Points above/below your own average (few shows count less)",
  },
];

const num = (v: number | null, digits = 2) => (v === null ? "–" : v.toFixed(digits));

/** Every genre, theme, studio, ... on the list, in sortable tabs. */
export function Breakdown({ breakdown }: { breakdown: Record<string, TagStat[]> }) {
  const kinds = KINDS.filter((k) => breakdown[k.kind]?.length);
  const [kind, setKind] = useState(kinds[0]?.kind ?? "genre");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "count", desc: true });
  const rows = [...(breakdown[kind] ?? [])];
  if (!(kind === "era" && sort.key === "count")) {
    rows.sort((a, b) => {
      const av = a[sort.key];
      const bv = b[sort.key];
      if (typeof av === "string" || typeof bv === "string")
        return String(av).localeCompare(String(bv)) * (sort.desc ? -1 : 1);
      return ((av ?? -Infinity) - (bv ?? -Infinity)) * (sort.desc ? -1 : 1);
    });
  }
  const maxCount = Math.max(1, ...rows.map((r) => r.count));

  function header(key: SortKey, label: string, title: string, align = "text-right") {
    const active = sort.key === key;
    return (
      <th
        className={`px-2 py-2 font-normal ${align}`}
        title={title}
        aria-sort={active ? (sort.desc ? "descending" : "ascending") : "none"}
      >
        <button
          onClick={() => setSort({ key, desc: active ? !sort.desc : key !== "name" })}
          className={`hover:text-white ${active ? "text-white" : ""}`}
        >
          {label}
          {active ? (sort.desc ? " ↓" : " ↑") : ""}
        </button>
      </th>
    );
  }

  return (
    <div>
      <div role="tablist" className="flex flex-wrap gap-1">
        {kinds.map((k) => (
          <button
            key={k.kind}
            role="tab"
            aria-selected={k.kind === kind}
            onClick={() => setKind(k.kind)}
            className={`rounded-full px-3 py-1 text-sm ${k.kind === kind ? "bg-white text-black" : "bg-white/5 hover:bg-white/10"}`}
          >
            {k.label}
          </button>
        ))}
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[36rem] text-sm tabular-nums">
          <thead className="text-xs text-muted">
            <tr className="border-b border-white/10">
              {header("name", "Name", "Name", "text-left")}
              {COLUMNS.map((c) => header(c.key, c.label, c.title))}
              <th className="px-2 py-2 text-right font-normal" title="Dropped shows">
                Dropped
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-b border-white/5 hover:bg-white/5">
                <td className="px-2 py-1.5">{r.name}</td>
                <td className="px-2 py-1.5">
                  <span className="flex items-center justify-end gap-2">
                    <span className="h-2 w-16 overflow-hidden rounded-sm bg-white/5">
                      <span
                        className="block h-full rounded-r-sm"
                        style={{ width: `${(r.count / maxCount) * 100}%`, background: YOU }}
                      />
                    </span>
                    <span className="w-8 text-right">{r.count}</span>
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right">{num(r.mean_score)}</td>
                <td className="px-2 py-1.5 text-right text-neutral-400">{num(r.mal_mean)}</td>
                <td className="px-2 py-1.5 text-right">
                  {r.delta === null ? (
                    "–"
                  ) : (
                    <>
                      <span
                        aria-hidden
                        className={r.delta >= 0 ? "text-green-400" : "text-red-400"}
                      >
                        {r.delta >= 0 ? "▲ " : "▼ "}
                      </span>
                      {signed(r.delta)}
                    </>
                  )}
                </td>
                <td className="px-2 py-1.5 text-right">
                  {r.affinity === null ? "–" : signed(r.affinity)}
                </td>
                <td className="px-2 py-1.5 text-right text-neutral-400">{r.dropped || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
