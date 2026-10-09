import { SeriesDetail } from "@/components/series/SeriesDetail";

export default async function SeriesPage({ params }: PageProps<"/series/[slug]">) {
  const { slug } = await params;
  return (
    <div className="mx-auto max-w-6xl px-4 pt-24 pb-16">
      <SeriesDetail slug={decodeURIComponent(slug)} />
    </div>
  );
}
