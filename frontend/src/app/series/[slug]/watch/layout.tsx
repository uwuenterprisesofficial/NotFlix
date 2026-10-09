import { SeriesWatchLayout } from "@/components/series/SeriesWatchLayout";

// Stays mounted across episodes, so the player frame (and its fullscreen) survives "Next Episode".
export default function SeriesWatchRoot({ children }: LayoutProps<"/series/[slug]/watch">) {
  return (
    <div className="mx-auto max-w-6xl px-4 pt-20 pb-16">
      <SeriesWatchLayout>{children}</SeriesWatchLayout>
    </div>
  );
}
