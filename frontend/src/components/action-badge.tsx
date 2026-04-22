import { cn } from "@/lib/utils";

export function ActionBadge({ action }: { action: string }) {
  const a = action.toLowerCase();
  const styles =
    a === "buy"
      ? "bg-[var(--success)]/12 text-[var(--success)] border-[var(--success)]/30"
      : a === "sell"
        ? "bg-[var(--danger)]/12 text-[var(--danger)] border-[var(--danger)]/30"
        : "bg-[var(--muted)]/15 text-[var(--muted)] border-[var(--muted)]/30";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[11px] font-medium uppercase tracking-wider px-2 py-0.5 rounded border",
        styles,
      )}
    >
      {a}
    </span>
  );
}
