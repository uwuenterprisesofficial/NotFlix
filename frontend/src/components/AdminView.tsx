"use client";

import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { LOCALE, type MessageKey } from "@/lib/i18n";
import { useT } from "./I18nProvider";

const REFRESH_MS = 5000;

type Job = {
  id: string;
  function: string;
  args: (string | number)[];
  started_at: string | null;
  ended_at: string | null;
  error: string | null;
};
type Status = {
  now: string;
  rq: {
    error?: string;
    workers: {
      name: string;
      state: string;
      queues: string[];
      job: Job | null;
      last_heartbeat: string | null;
      successful: number;
      failed: number;
    }[];
    queues: {
      name: string;
      queued: number;
      started: number;
      failed: number;
      finished: number;
      scheduled: number;
      recent_failures: Job[];
    }[];
  };
  api: {
    scans: {
      anime_id: number;
      title: string | null;
      provider: string;
      stored: number;
      total: number;
      stepwise: boolean;
    }[];
    stats: { user_id: number; step?: string; status?: string; done?: number; total?: number }[];
    list_writers: { user_id: number; done?: number; total?: number }[];
    calendar_weeks_refreshing: string[];
    airing_checks: number;
    rooms_open: number;
    http_clients: string[];
  };
  providers: {
    name: string;
    enabled: boolean;
    backoff_s: number | null;
    scans_24h: Record<string, number>;
    last_error: { anime_id: number; error: string | null; at: string | null } | null;
  }[];
  failed_scans: {
    anime_id: number;
    title: string | null;
    provider: string;
    error: string | null;
    at: string | null;
  }[];
  analysis: {
    counts: Record<string, number>;
    recent: {
      id: string;
      anime_id: number;
      title: string | null;
      episodes: number[];
      status: string;
      error: string | null;
      created_at: string;
    }[];
  };
  counts: Record<string, number>;
  redis_memory: string | null;
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg bg-surface-raised p-4">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Badge({ tone, children }: { tone: "ok" | "warn" | "bad" | "muted"; children: ReactNode }) {
  const colors = {
    ok: "bg-green-500/20 text-green-300",
    warn: "bg-amber-500/20 text-amber-300",
    bad: "bg-red-500/20 text-red-300",
    muted: "bg-white/10 text-muted",
  };
  return <span className={`rounded px-1.5 py-0.5 text-xs ${colors[tone]}`}>{children}</span>;
}

/** The admin page's live view: asks for the status every few seconds while visible. */
export function AdminView() {
  const { t, lang } = useT();
  const [data, setData] = useState<Status | null>(null);
  const [failed, setFailed] = useState(false);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch("/api/admin/status").catch(() => null);
    if (res?.ok) {
      setData(await res.json());
      setFailed(false);
      setLoadedAt(new Date().toISOString());
    } else {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    const tick = async () => {
      if (document.visibilityState === "visible") await load();
      if (!cancelled) timer = setTimeout(tick, REFRESH_MS);
    };
    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [load]);

  // "12 s ago", "3 min ago": against the server's clock (the times come from there).
  const ago = (at: string | null) => {
    if (!at || !data) return "–";
    const seconds = Math.round((Date.parse(at) - Date.parse(data.now)) / 1000);
    const format = new Intl.RelativeTimeFormat(LOCALE[lang], { numeric: "auto", style: "short" });
    if (Math.abs(seconds) < 60) return format.format(seconds, "second");
    if (Math.abs(seconds) < 3600) return format.format(Math.round(seconds / 60), "minute");
    if (Math.abs(seconds) < 86400) return format.format(Math.round(seconds / 3600), "hour");
    return format.format(Math.round(seconds / 86400), "day");
  };

  async function retry(name: string) {
    await fetch(`/api/admin/providers/${encodeURIComponent(name)}/retry`, { method: "POST" });
    await load();
  }

  if (!data) {
    return <p className="text-muted">{failed ? t("admin.loadFailed") : "…"}</p>;
  }
  const { rq, api } = data;

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted" aria-live="polite">
        {loadedAt &&
          t("admin.updated", { when: new Date(loadedAt).toLocaleTimeString(LOCALE[lang]) })}
        {failed && <span className="ml-2 text-amber-400">{t("admin.loadFailed")}</span>}
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t("admin.workers")}>
          {rq.error && <p className="mb-2 text-sm text-red-400">{rq.error}</p>}
          {rq.workers.length === 0 ? (
            <p className="text-sm text-amber-300">{t("admin.noWorkers")}</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {rq.workers.map((w) => (
                <li key={w.name} className="rounded bg-black/20 p-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={w.state === "busy" ? "warn" : "ok"}>
                      {w.state === "busy" ? t("admin.busy") : t("admin.idle")}
                    </Badge>
                    <span className="font-mono text-xs">{w.name}</span>
                    <span className="text-muted">{w.queues.join(", ")}</span>
                  </div>
                  {w.job && (
                    <p className="mt-1 text-xs">
                      {w.job.function}({w.job.args.join(", ")}) · {ago(w.job.started_at)}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-muted">
                    {t("admin.heartbeat", { when: ago(w.last_heartbeat) })} ·{" "}
                    {t("admin.jobsDone", { ok: w.successful, failed: w.failed })}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={t("admin.queues")}>
          <div className="space-y-3 text-sm">
            {rq.queues.map((q) => (
              <div key={q.name}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{q.name}</span>
                  <Badge tone={q.queued ? "warn" : "muted"}>
                    {q.queued} {t("admin.queued")}
                  </Badge>
                  <Badge tone={q.started ? "ok" : "muted"}>
                    {q.started} {t("admin.started")}
                  </Badge>
                  <Badge tone={q.failed ? "bad" : "muted"}>
                    {q.failed} {t("admin.failed")}
                  </Badge>
                  <Badge tone="muted">
                    {q.finished} {t("admin.finished")}
                  </Badge>
                  {q.scheduled > 0 && (
                    <Badge tone="muted">
                      {q.scheduled} {t("admin.scheduled")}
                    </Badge>
                  )}
                </div>
                {q.recent_failures.length > 0 && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-xs text-muted">
                      {t("admin.recentFailures")}
                    </summary>
                    <ul className="mt-1 space-y-1 text-xs">
                      {q.recent_failures.map((j) => (
                        <li key={j.id}>
                          <span className="font-mono">
                            {j.function}({j.args.join(", ")})
                          </span>{" "}
                          · {ago(j.ended_at)}
                          {j.error && <span className="block text-red-300">{j.error}</span>}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            ))}
          </div>
        </Section>
      </div>

      <Section title={t("admin.api")}>
        <h3 className="mb-1 text-sm font-semibold">{t("admin.scans")}</h3>
        {api.scans.length === 0 ? (
          <p className="text-sm text-muted">{t("admin.noScans")}</p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {api.scans.map((s) => (
              <li key={`${s.anime_id}:${s.provider}`} className="flex items-center gap-3">
                <Link href={`/anime/${s.anime_id}`} className="min-w-0 flex-1 truncate underline">
                  {s.title ?? `#${s.anime_id}`}
                </Link>
                <span className="w-24 text-muted">{s.provider}</span>
                {s.stepwise ? (
                  <span className="flex w-40 items-center gap-2 tabular-nums">
                    <span className="h-1.5 flex-1 overflow-hidden rounded bg-white/15">
                      <span
                        className="block h-full bg-brand"
                        style={{ width: `${(s.stored / Math.max(1, s.total)) * 100}%` }}
                      />
                    </span>
                    {s.stored}/{s.total}
                  </span>
                ) : (
                  <span className="w-40 text-muted">{t("admin.listing")}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted">{t("admin.stats")}</dt>
          <dd>
            {api.stats.length
              ? api.stats
                  .map((s) => `#${s.user_id} ${s.status === "failed" ? "✕" : (s.step ?? "")}`)
                  .join(", ")
              : t("admin.none")}
          </dd>
          <dt className="text-muted">{t("admin.writers")}</dt>
          <dd>
            {api.list_writers.length
              ? api.list_writers
                  .map((w) => `#${w.user_id} ${w.done ?? 0}/${w.total ?? "?"}`)
                  .join(", ")
              : t("admin.none")}
          </dd>
          <dt className="text-muted">{t("admin.calendar")}</dt>
          <dd>{api.calendar_weeks_refreshing.join(", ") || t("admin.none")}</dd>
          <dt className="text-muted">{t("admin.airingChecks")}</dt>
          <dd>{api.airing_checks}</dd>
          <dt className="text-muted">{t("admin.rooms")}</dt>
          <dd>{api.rooms_open}</dd>
          <dt className="text-muted">{t("admin.clients")}</dt>
          <dd>{api.http_clients.join(", ") || t("admin.none")}</dd>
        </dl>
      </Section>

      <Section title={t("admin.providers")}>
        <ul className="space-y-2 text-sm">
          {data.providers.map((p) => (
            <li key={p.name} className="rounded bg-black/20 p-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{p.name}</span>
                {!p.enabled && <Badge tone="muted">{t("admin.disabled")}</Badge>}
                {p.backoff_s !== null && (
                  <Badge tone="bad">{t("admin.skipped", { s: p.backoff_s })}</Badge>
                )}
                {Object.entries(p.scans_24h).map(([state, n]) => (
                  <Badge
                    key={state}
                    tone={state === "failed" ? "bad" : state === "running" ? "warn" : "ok"}
                  >
                    {n} {state}
                  </Badge>
                ))}
                <span className="text-xs text-muted">{t("admin.last24h")}</span>
                {(p.backoff_s !== null || p.scans_24h.failed) && (
                  <button
                    onClick={() => retry(p.name)}
                    className="ml-auto rounded bg-white/10 px-2 py-0.5 text-xs hover:bg-white/20"
                  >
                    {t("admin.retry")}
                  </button>
                )}
              </div>
              {p.last_error?.error && (
                <p className="mt-1 text-xs text-red-300">
                  {t("admin.lastError")} ({ago(p.last_error.at)}): {p.last_error.error}
                </p>
              )}
            </li>
          ))}
        </ul>
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t("admin.failedScans")}>
          {data.failed_scans.length === 0 ? (
            <p className="text-sm text-muted">{t("admin.noFailedScans")}</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {data.failed_scans.map((s) => (
                <li key={`${s.anime_id}:${s.provider}`}>
                  <Link href={`/anime/${s.anime_id}`} className="underline">
                    {s.title ?? `#${s.anime_id}`}
                  </Link>{" "}
                  <span className="text-muted">
                    · {s.provider} · {ago(s.at)}
                  </span>
                  {s.error && <span className="block text-xs text-red-300">{s.error}</span>}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={t("admin.analysis")}>
          <div className="mb-2 flex flex-wrap gap-2">
            {Object.entries(data.analysis.counts).map(([state, n]) => (
              <Badge
                key={state}
                tone={state === "failed" ? "bad" : state === "running" ? "warn" : "muted"}
              >
                {n} {state}
              </Badge>
            ))}
          </div>
          <ul className="space-y-1.5 text-sm">
            {data.analysis.recent.map((j) => (
              <li key={j.id}>
                <Link href={`/anime/${j.anime_id}`} className="underline">
                  {j.title ?? `#${j.anime_id}`}
                </Link>{" "}
                <span className="text-muted">
                  · {t("admin.episodes", { list: j.episodes.join(", ") })} · {j.status} ·{" "}
                  {ago(j.created_at)}
                </span>
                {j.error && <span className="block text-xs text-red-300">{j.error}</span>}
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <Section title={t("admin.stored")}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr_auto_1fr]">
          {Object.entries(data.counts).map(([key, n]) => (
            <div key={key} className="contents">
              <dt className="text-muted">{t(`admin.count.${key}` as MessageKey)}</dt>
              <dd className="tabular-nums">{n.toLocaleString()}</dd>
            </div>
          ))}
          <dt className="text-muted">{t("admin.redis")}</dt>
          <dd>{data.redis_memory ?? "–"}</dd>
        </dl>
      </Section>
    </div>
  );
}
