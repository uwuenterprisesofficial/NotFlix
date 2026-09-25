"use client";

import { type ReactNode, useState } from "react";

/**
 * A <details> whose content is only mounted once it's opened, so what's inside (and the
 * requests it makes) costs nothing while it stays closed.
 */
export function LazyDetails({
  summary,
  className,
  children,
}: {
  summary: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const [opened, setOpened] = useState(false);
  return (
    <details className={className} onToggle={(e) => e.currentTarget.open && setOpened(true)}>
      {summary}
      {opened && children}
    </details>
  );
}
