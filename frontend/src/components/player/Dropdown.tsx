"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

/** A button that opens a menu below it; closes on a click outside, Escape, or `close()`. */
export function Dropdown({
  button,
  align,
  className = "w-80",
  onOpen,
  label,
  children,
}: {
  button: ReactNode;
  /** Accessible name when the button's content doesn't say what it's for. */
  label?: string;
  align: "left" | "right";
  className?: string;
  onOpen?: () => void;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (
        e instanceof KeyboardEvent ? e.key === "Escape" : !root.current?.contains(e.target as Node)
      )
        setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        onClick={() => {
          if (!open) onOpen?.();
          setOpen(!open);
        }}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={label}
        className="flex max-w-[20rem] items-center gap-2 rounded bg-surface-raised px-3 py-1.5 hover:bg-neutral-700"
      >
        {button}
        <span aria-hidden className={`text-xs transition-transform ${open ? "rotate-180" : ""}`}>
          ▾
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className={`absolute top-full z-20 mt-2 max-h-96 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-md border border-white/10 bg-surface-raised p-1 shadow-2xl ${align === "right" ? "right-0" : "left-0"} ${className}`}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}
