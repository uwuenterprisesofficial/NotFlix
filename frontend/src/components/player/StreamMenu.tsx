"use client";

import { PROVIDER_LABELS } from "@/lib/languages";
import type { Stream } from "@/lib/types";
import { Dropdown } from "./Dropdown";
import type { useSources } from "./useSources";

function kindLabel(stream: Stream) {
  if (stream.kind === "embed") return "Embed";
  return stream.format === "hls" ? "Direct · HLS" : "Direct · MP4";
}

function KindBadge({ stream }: { stream: Stream }) {
  const direct = stream.kind === "direct";
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold ${direct ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-muted"}`}
    >
      {kindLabel(stream)}
    </span>
  );
}

/** Every source and stream of the current language, tucked away behind one button. */
export function StreamMenu({ sources }: { sources: ReturnType<typeof useSources> }) {
  const { active, stream } = sources;
  if (sources.candidates.length === 0) return null;

  return (
    <Dropdown
      align="right"
      onOpen={sources.showAll}
      button={
        <>
          <span className="truncate">
            {active && stream
              ? `${PROVIDER_LABELS[active.provider] ?? active.provider} · ${stream.label}`
              : "Streams"}
          </span>
          {stream && <KindBadge stream={stream} />}
        </>
      }
    >
      {(close) =>
        sources.candidates.map((o) => {
          const resolution = sources.resolutionOf(o);
          const streams = sources.streamsOf(o);
          return (
            <div key={o.id} className="py-1">
              <div className="flex items-baseline justify-between gap-2 px-2 py-1 text-xs text-muted">
                <span className="truncate font-semibold text-white/80">{o.label}</span>
                <span className="shrink-0">{PROVIDER_LABELS[o.provider] ?? o.provider}</span>
              </div>
              {resolution === undefined && (
                <p className="px-2 py-1 text-xs text-muted">Loading streams…</p>
              )}
              {resolution && !resolution.ok && (
                <p className="px-2 py-1 text-xs text-muted line-through">{resolution.error}</p>
              )}
              {streams.map((s) => {
                const current = o.id === active?.id && s.url === stream?.url;
                const broken = sources.streamFailed(s);
                return (
                  <button
                    key={s.url}
                    role="menuitemradio"
                    aria-checked={current}
                    disabled={broken}
                    title={broken ? "This stream didn’t play" : undefined}
                    onClick={() => {
                      sources.choose(o.id, s.url);
                      close();
                    }}
                    className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left ${current ? "bg-white/10" : "hover:bg-white/5"} ${broken ? "opacity-40" : ""}`}
                  >
                    <span aria-hidden className="w-3 text-xs">
                      {current ? "✓" : ""}
                    </span>
                    <span className={`flex-1 truncate ${broken ? "line-through" : ""}`}>
                      {s.label}
                    </span>
                    <KindBadge stream={s} />
                  </button>
                );
              })}
            </div>
          );
        })
      }
    </Dropdown>
  );
}
