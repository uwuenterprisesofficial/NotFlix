"use client";

import { useT } from "@/components/I18nProvider";

export default function Error({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  const { t } = useT();
  return (
    <div className="mx-auto mt-32 max-w-lg rounded-lg bg-surface-raised p-8 text-center">
      <h2 className="text-2xl font-bold">{t("error.title")}</h2>
      <p className="mt-3 text-muted">{t("error.body")}</p>
      {error.digest && (
        <p className="mt-2 text-xs text-muted">{t("error.id", { id: error.digest })}</p>
      )}
      <button onClick={() => retry()} className="mt-6 rounded bg-brand px-5 py-2 font-semibold">
        {t("error.retry")}
      </button>
    </div>
  );
}
