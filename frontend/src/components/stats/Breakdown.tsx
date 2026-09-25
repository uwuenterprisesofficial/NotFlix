"use client";

import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { featureName, formatNumber, type MessageKey } from "@/lib/i18n";
import type { TagStat } from "@/lib/types";
import { YOU } from "./colors";

const KINDS = ["genre", "theme", "demographic", "studio", "source", "type", "era", "explicit"];

type SortKey = "count" | "mean_score" | "mal_mean" | "delta" | "affinity" | "name";
const COLUMNS: { key: SortKey; label: MessageKey; title: MessageKey }[] = [
  { key: "count", label: "col.count", title: "col.countInfo" },
  { key: "mean_score", label: "col.mean", title: "col.meanInfo" },
  { key: "mal_mean", label: "col.mal", title: "col.malInfo" },
  { key: "delta", label: "col.delta", title: "col.deltaInfo" },
  { key: "affinity", label: "col.affinity", title: "col.affinityInfo" },
];

/** Every genre, theme, studio, ... on the list, in sortable tabs. */
export function Breakdown({ breakdown }: { breakdown: Record<string, TagStat[]> }) {
  const { t, lang } = useT();
  const num = (v: number | null, digits = 2) => (v === null ? "–" : formatNumber(lang, v, digits));
  const signed = (v: number) => `${v >= 0 ? "+" : "−"}${num(Math.abs(v))}`;
  const kinds = KINDS.filter((k) => breakdown[k]?.length);
  const [kind, setKind] = useState(kinds[0] ?? "genre");
  const named = (breakdown[kind] ?? []).map((r) => ({
    ...r,
    name: featureName(lang, r.key, r.name),
  }));
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "count", desc: true });
  const rows = [...named];
  if (!(kind === "era" && sort.key === "count")) {
    rows.sort((a, b) => {
      const av = a[sort.key];
      const bv = b[sort.key];
      if (typeof av === "string" || typeof bv === "string")
        return String(av).localeCompare(String(bv), lang) * (sort.desc ? -1 : 1);
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
            key={k}
            role="tab"
            aria-selected={k === kind}
            onClick={() => setKind(k)}
            className={`rounded-full px-3 py-1 text-sm ${k === kind ? "bg-white text-black" : "bg-white/5 hover:bg-white/10"}`}
          >
            {t(`kind.${k}` as MessageKey)}
          </button>
        ))}
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[36rem] text-sm tabular-nums">
          <thead className="text-xs text-muted">
            <tr className="border-b border-white/10">
              {header("name", t("col.name"), t("col.name"), "text-left")}
              {COLUMNS.map((c) => header(c.key, t(c.label), t(c.title)))}
              <th className="px-2 py-2 text-right font-normal" title={t("col.droppedInfo")}>
                {t("col.dropped")}
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
