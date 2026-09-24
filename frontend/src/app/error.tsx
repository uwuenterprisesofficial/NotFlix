"use client";

export default function Error({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <div className="mx-auto mt-32 max-w-lg rounded-lg bg-surface-raised p-8 text-center">
      <h2 className="text-2xl font-bold">Something went wrong</h2>
      <p className="mt-3 text-muted">Couldn’t load this page. Is the NotFlix API running?</p>
      {error.digest && <p className="mt-2 text-xs text-muted">Error ID: {error.digest}</p>}
      <button onClick={() => retry()} className="mt-6 rounded bg-brand px-5 py-2 font-semibold">
        Try again
      </button>
    </div>
  );
}
