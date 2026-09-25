"use client";

import { useEffect, useState } from "react";
import type { StatsStatus } from "@/lib/types";
import { StatsReport } from "./StatsReport";

const POLL_MS = 1500;

/** Loads the statistics, polling while the backend computes them. */
export function StatsView() {
  const [state, setState] = useState<StatsStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll(method: "GET" | "POST") {
      try {
        const res = await fetch(method === "POST" ? "/api/me/stats/refresh" : "/api/me/stats", {
          method,
          cache: "no-store",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const next: StatsStatus = await res.json();
        if (cancelled) return;
        setState(next);
        setError(null);
        if (next.status === "loading") timer = setTimeout(() => poll("GET"), POLL_MS);
      } catch (e) {
        if (cancelled) return;
        setError(String(e));
        timer = setTimeout(() => poll("GET"), POLL_MS * 4);
      }
    }
    poll(attempt ? "POST" : "GET");
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [attempt]);

  const retry = () => setAttempt((a) => a + 1);

  if (!state) {
    return <Loading step={error ? "Can't reach the server, retrying" : "Loading"} />;
  }
  if (!state.stats) {
    if (state.status === "failed") {
      return (
        <div className="rounded-lg bg-surface-raised p-8 text-center">
          <p className="font-semibold">The statistics couldn&apos;t be computed.</p>
          {state.error && <p className="mt-1 text-sm text-muted">{state.error}</p>}
          <button
            onClick={retry}
            className="mt-4 rounded bg-brand px-4 py-2 font-semibold hover:bg-brand-dark"
          >
            Try again
          </button>
        </div>
      );
    }
    return <Loading step={state.step} done={state.done} total={state.total} />;
  }

  return (
    <>
      <div className="mb-6 flex min-h-8 flex-wrap items-center gap-3 text-sm text-muted">
        {state.status === "loading" ? (
          <span className="flex items-center gap-2" role="status">
            <Spinner /> Updating in the background: {progressText(state)}
          </span>
        ) : state.status === "failed" ? (
          <span>
            Updating failed{state.error ? `: ${state.error}` : ""}.{" "}
            <button onClick={retry} className="underline hover:text-white">
              Try again
            </button>
          </span>
        ) : (
          state.computed_at && (
            <span>
              Computed {new Date(state.computed_at).toLocaleString()} ·{" "}
              <button onClick={retry} className="underline hover:text-white">
                Recalculate
              </button>
            </span>
          )
        )}
      </div>
      <div className={state.status === "loading" ? "opacity-60 transition-opacity" : ""}>
        <StatsReport stats={state.stats} />
      </div>
    </>
  );
}

function progressText(s: { step: string | null; done: number; total: number }) {
  const step = s.step ?? "Working";
  return s.total ? `${step} (${s.done} of ${s.total})` : `${step}…`;
}

function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block size-4 animate-spin rounded-full border-2 border-white/20 border-t-white"
    />
  );
}

function Loading({
  step,
  done = 0,
  total = 0,
}: {
  step: string | null;
  done?: number;
  total?: number;
}) {
  return (
    <div role="status" className="rounded-lg bg-surface-raised p-10 text-center">
      <div className="flex items-center justify-center gap-3 text-lg font-semibold">
        <Spinner /> Preparing your statistics
      </div>
      <p className="mt-2 text-sm text-muted">{progressText({ step, done, total })}</p>
      {total > 0 && (
        <div className="mx-auto mt-4 h-1.5 max-w-sm overflow-hidden rounded bg-white/10">
          <div
            className="h-full bg-brand transition-[width]"
            style={{ width: `${Math.min(100, (done / total) * 100)}%` }}
          />
        </div>
      )}
      <p className="mt-4 text-xs text-muted">
        The first time, every show&apos;s genres, studios and more are loaded from MyAnimeList. You
        can leave this page — it keeps going.
      </p>
    </div>
  );
}
