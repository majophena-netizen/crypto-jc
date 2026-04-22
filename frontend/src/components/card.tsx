import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export function Card({
  title,
  action,
  children,
  className,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-xl border bg-[var(--card)] p-4 shadow-[0_1px_0_0_rgba(0,0,0,0.02)]",
        className,
      )}
    >
      {(title || action) && (
        <header className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium tracking-tight text-[var(--foreground)]">
            {title}
          </h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "success" | "danger" | "warn" | "muted";
}) {
  const toneCls =
    tone === "success"
      ? "text-[var(--success)]"
      : tone === "danger"
        ? "text-[var(--danger)]"
        : tone === "warn"
          ? "text-[var(--warn)]"
          : "";
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-[var(--muted)]">
        {label}
      </div>
      <div className={cn("numeric text-2xl font-medium mt-0.5", toneCls)}>
        {value}
      </div>
      {sub && <div className="text-xs text-[var(--muted)] mt-0.5">{sub}</div>}
    </div>
  );
}
