"use client";

import { createContext, type ReactNode, use, useState } from "react";
import { FrameContext } from "../player/PlayerFrame";

const HeadingSlot = createContext<HTMLDivElement | null>(null);

/** The element above the video that the page puts its title in. */
export const useHeadingSlot = () => use(HeadingSlot);

/**
 * The series player's frame: the title row and the box the video plays in. It lives in the watch
 * layout, which stays mounted when "Next Episode" moves to another episode page, so fullscreen
 * (which is on this box, not on the <video>, to keep the overlay visible) carries over. The page's
 * player renders into them through portals.
 */
export function SeriesWatchLayout({ children }: { children: ReactNode }) {
  const [heading, setHeading] = useState<HTMLDivElement | null>(null);
  const [frame, setFrame] = useState<HTMLDivElement | null>(null);
  return (
    <>
      <div ref={setHeading} />
      <div
        ref={setFrame}
        className="group relative aspect-video w-full overflow-hidden rounded-lg bg-black [&:fullscreen]:rounded-none"
      />
      <HeadingSlot value={heading}>
        <FrameContext value={frame}>{children}</FrameContext>
      </HeadingSlot>
    </>
  );
}
