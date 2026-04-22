"use client";

import { cn } from "@/lib/utils";
import type { Mode } from "@/lib/api";

const MODES: { value: Mode; label: string; sub: string }[] = [
  { value: "signals", label: "Signals", sub: "Detection only" },
  { value: "paper", label: "Paper", sub: "Virtual wallet" },
  { value: "live", label: "Live", sub: "Real orders" },
];

export function ModeSwitcher({
  current,
  disabled,
  onChange,
}: {
  current: Mode;
  disabled?: boolean;
  onChange: (m: Mode) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border p-1 bg-[var(--card)] gap-1">
      {MODES.map((m) => {
        const active = current === m.value;
        return (
          <button
            key={m.value}
            type="button"
            onClick={() => onChange(m.value)}
            disabled={disabled}
            className={cn(
              "px-3 py-1.5 rounded-md text-xs font-medium transition-colors text-left leading-tight",
              active
                ? "bg-[var(--foreground)] text-[var(--background)]"
                : "text-[var(--muted)] hover:text-[var(--foreground)]",
              disabled && "opacity-50 cursor-not-allowed",
            )}
          >
            <div>{m.label}</div>
            <div className="text-[10px] opacity-70 font-normal">{m.sub}</div>
          </button>
        );
      })}
    </div>
  );
}
