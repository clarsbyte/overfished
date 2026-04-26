import { ChevronDown, ChevronRight, Minimize2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

export type PanelStatus = "idle" | "running" | "ok" | "error";

interface Props {
  id: string;
  title: string;
  /** Shorter label when collapsed to a chip (defaults to `title`) */
  titleShort?: string;
  icon?: ReactNode;
  status?: PanelStatus;
  badge?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  /** When true, header shows a control to shrink the whole panel to a small chip (persisted separately from body open). */
  minimizableToChip?: boolean;
  /** localStorage key suffix; defaults to `id` */
  chipStorageKey?: string;
  /** Override the outer section className (replaces the default glass-surface glass-panel classes) */
  className?: string;
}

const STATUS_RING: Record<PanelStatus, string> = {
  idle: "bg-slate2-400/40",
  running: "bg-accent-suspect animate-pulse",
  ok: "bg-accent-safe",
  error: "bg-accent-iuu",
};

const STORAGE_PREFIX = "panel-open:";
const CHIP_PREFIX = "panel-chip:";

export function CollapsiblePanel({
  id,
  title,
  titleShort,
  icon,
  status = "idle",
  badge,
  defaultOpen = true,
  children,
  minimizableToChip = false,
  chipStorageKey,
  className,
}: Props) {
  const chipKey = chipStorageKey ?? id;

  const [open, setOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return defaultOpen;
    const raw = window.localStorage.getItem(STORAGE_PREFIX + id);
    if (raw === "1") return true;
    if (raw === "0") return false;
    return defaultOpen;
  });

  const [chipped, setChipped] = useState<boolean>(() => {
    if (!minimizableToChip || typeof window === "undefined") return false;
    return window.localStorage.getItem(CHIP_PREFIX + chipKey) === "1";
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_PREFIX + id, open ? "1" : "0");
  }, [id, open]);

  useEffect(() => {
    if (!minimizableToChip || typeof window === "undefined") return;
    window.localStorage.setItem(CHIP_PREFIX + chipKey, chipped ? "1" : "0");
  }, [chipKey, chipped, minimizableToChip]);

  const chipLabel = titleShort ?? title;

  if (minimizableToChip && chipped) {
    return (
      <button
        type="button"
        onClick={() => setChipped(false)}
        className="glass-surface glass-panel pointer-events-auto flex max-w-[200px] items-center gap-2 self-end px-2.5 py-1.5 text-left transition"
        title={`Expand ${title}`}
      >
        {icon && <span className="shrink-0 text-slate2-200">{icon}</span>}
        <span className="min-w-0 flex-1 truncate font-display text-xs font-semibold text-slate2-200">
          {chipLabel}
        </span>
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${STATUS_RING[status]}`}
          aria-label={`status: ${status}`}
        />
        <ChevronDown size={12} className="shrink-0 text-slate2-500" aria-hidden />
      </button>
    );
  }

  return (
    <section className={className ?? "glass-surface glass-panel pointer-events-auto w-full max-w-[360px] self-end"}>
      <div className="flex w-full items-center gap-0">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left transition hover:bg-white/10"
        >
          {open ? (
            <ChevronDown size={14} className="shrink-0 text-slate2-400" />
          ) : (
            <ChevronRight size={14} className="shrink-0 text-slate2-400" />
          )}
          {icon && <span className="shrink-0 text-slate2-200">{icon}</span>}
          <span className="min-w-0 flex-1 truncate font-display text-sm font-semibold text-slate2-200">
            {title}
          </span>
          {badge}
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${STATUS_RING[status]}`}
            aria-label={`status: ${status}`}
          />
        </button>
        {minimizableToChip && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setChipped(true);
            }}
            className="shrink-0 border-l border-white/10 px-2.5 py-2 text-slate2-300 transition hover:bg-white/10 hover:text-slate2-100"
            title="Minimize to compact bar"
            aria-label="Minimize panel"
          >
            <Minimize2 size={14} />
          </button>
        )}
      </div>
      {open && (
        <div className="max-h-[min(46vh,420px)] overflow-y-auto scrollbar-themed border-t border-white/12 px-3 py-2">
          {children}
        </div>
      )}
    </section>
  );
}
