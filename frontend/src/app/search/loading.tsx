import { Skeleton } from "@/components/SearchResults";

/** Shown at once when the search is opened, until the page is there. */
export default function Loading() {
  return (
    <div className="px-4 pt-24 pb-16 md:px-12">
      <div className="h-9 w-40 animate-pulse rounded bg-surface-raised" />
      <div className="mt-4 h-10 w-full animate-pulse rounded bg-surface-raised" />
      <Skeleton />
    </div>
  );
}
