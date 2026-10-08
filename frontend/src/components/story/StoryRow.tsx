"use client";

import { useEffect, useState } from "react";
import type { MessageKey } from "@/lib/i18n";
import type { RelatedShow, Story } from "@/lib/types";
import { AnimeCard } from "../AnimeCard";
import { useT } from "../I18nProvider";

// Asked again this long after an answer that wasn't complete (relations still being looked up).
const RETRY_MS = 4000;
const RETRIES = 3;

const RELATION_LABEL: Record<string, MessageKey> = {
  PREQUEL: "story.prequel",
  SEQUEL: "story.sequel",
  CURRENT: "story.current",
  PARENT: "story.parent",
  SIDE_STORY: "story.sideStory",
  SPIN_OFF: "story.spinOff",
  ALTERNATIVE: "story.alternative",
};

/** A show's page: its prequels and sequels in order (the show itself among them), and the
 * other related shows (films, side stories, spin-offs). */
export function StoryRow({ animeId }: { animeId: number }) {
  const { t } = useT();
  const [story, setStory] = useState<Story | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let tries = 0;
    const load = () =>
      fetch(`/api/anime/${animeId}/story`)
        .then((r) => (r.ok ? (r.json() as Promise<Story>) : null))
        .catch(() => null)
        .then((found) => {
          if (cancelled || !found) return;
          setStory(found);
          if (!found.complete && ++tries < RETRIES) timer = setTimeout(load, RETRY_MS);
        });
    void load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [animeId]);

  if (!story || (!story.story.length && !story.other.length)) return null;
  return (
    <div className="mt-10 space-y-8">
      {story.story.length > 0 && <Shows title={t("story.title")} shows={story.story} numbered />}
      {story.other.length > 0 && <Shows title={t("story.related")} shows={story.other} />}
    </div>
  );
}

function Shows({
  title,
  shows,
  numbered = false,
}: {
  title: string;
  shows: RelatedShow[];
  numbered?: boolean;
}) {
  const { t } = useT();
  return (
    <section>
      <h2 className="text-lg font-semibold md:text-xl">{title}</h2>
      <div className="no-scrollbar mt-3 flex gap-3 overflow-x-auto pb-2">
        {shows.map(({ relation, anime }, i) => (
          <div key={anime.id} className="shrink-0">
            <p
              className={`mb-1.5 text-xs font-semibold tracking-wide uppercase ${relation === "CURRENT" ? "text-brand" : "text-muted"}`}
            >
              {numbered && `${i + 1}. `}
              {RELATION_LABEL[relation] ? t(RELATION_LABEL[relation]) : relation}
            </p>
            <div className={relation === "CURRENT" ? "rounded-md ring-2 ring-brand" : ""}>
              <AnimeCard anime={anime} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
