"use client";

import { useParams } from "next/navigation";
import { createContext, type ReactNode, use, useState, useSyncExternalStore } from "react";

const FrameContext = createContext<HTMLDivElement | null>(null);

/**
 * The box the video plays in. It lives in the watch layout, which stays mounted when "Next
 * Episode" moves to another episode page, so fullscreen (which is on this box, not on the
 * <video>, to keep Skip Intro / Next Episode visible) carries over to the next episode. The
 * page's player renders into it through a portal.
 */
export function PlayerFrame({ back, children }: { back: ReactNode; children: ReactNode }) {
  const { episode } = useParams<{ episode: string }>();
  const [frame, setFrame] = useState<HTMLDivElement | null>(null);
  return (
    <>
      <div className="mb-4 flex items-baseline gap-3">
        {back}
        <h1 className="text-xl font-semibold">Episode {episode}</h1>
      </div>
      <div
        ref={setFrame}
        className="group relative aspect-video w-full overflow-hidden rounded-lg bg-black [&:fullscreen]:rounded-none"
      />
      <FrameContext value={frame}>{children}</FrameContext>
    </>
  );
}

export function usePlayerFrame() {
  return use(FrameContext);
}

function subscribeFullscreen(onChange: () => void) {
  document.addEventListener("fullscreenchange", onChange);
  return () => document.removeEventListener("fullscreenchange", onChange);
}

const noSubscription = () => () => {};

/** Fullscreen for the player frame; unsupported on iPhones, where only <video> can go fullscreen. */
export function useFrameFullscreen() {
  const frame = usePlayerFrame();
  const supported = useSyncExternalStore(
    noSubscription,
    () => document.fullscreenEnabled,
    () => false,
  );
  const active = useSyncExternalStore(
    subscribeFullscreen,
    () => !!frame && document.fullscreenElement === frame,
    () => false,
  );
  const toggle = () => {
    if (!frame) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else frame.requestFullscreen().catch(() => {});
  };
  return { supported: supported && !!frame, active, toggle };
}

export function FullscreenButton({
  fullscreen,
  className,
}: {
  fullscreen: ReturnType<typeof useFrameFullscreen>;
  className: string;
}) {
  if (!fullscreen.supported) return null;
  const label = fullscreen.active ? "Exit fullscreen" : "Fullscreen";
  return (
    <button
      onClick={fullscreen.toggle}
      aria-label={label}
      title={`${label} (f)`}
      className={`absolute z-10 rounded bg-black/60 p-2 text-white backdrop-blur transition-opacity hover:bg-black/80 ${className}`}
    >
      <svg viewBox="0 0 24 24" aria-hidden className="h-5 w-5" fill="none" stroke="currentColor">
        <path
          strokeWidth="2"
          strokeLinecap="round"
          d={
            fullscreen.active
              ? "M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"
              : "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"
          }
        />
      </svg>
    </button>
  );
}
