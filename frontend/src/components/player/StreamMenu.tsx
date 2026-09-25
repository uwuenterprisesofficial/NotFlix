"use client";

import { providerLabel } from "@/lib/languages";
import type { T } from "@/lib/i18n";
import type { Stream } from "@/lib/types";
import { useT } from "../I18nProvider";
import { Dropdown } from "./Dropdown";
import type { useSources } from "./useSources";

function kindLabel(t: T, stream: Stream) {
  if (stream.kind === "embed") return t("player.embed");
  return `${t("player.direct")} · ${stream.format === "hls" ? "HLS" : "MP4"}`;
}

function KindBadge({ stream }: { stream: Stream }) {
  const { t } = useT();
  const direct = stream.kind === "direct";
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold ${direct ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-muted"}`}
    >
      {kindLabel(t, stream)}
    </span>
  );
}

/** Every source and stream of the current language, tucked away behind one button. */
export function StreamMenu({ sources }: { sources: ReturnType<typeof useSources> }) {
  const { t } = useT();
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
              ? `${providerLabel(t, active.provider)} · ${stream.label}`
              : t("player.streams")}
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
                <span className="shrink-0">{providerLabel(t, o.provider)}</span>
              </div>
              {resolution === undefined && (
                <p className="px-2 py-1 text-xs text-muted">{t("player.loadingStreams")}</p>
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
                    title={broken ? t("player.streamBroken") : undefined}
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
