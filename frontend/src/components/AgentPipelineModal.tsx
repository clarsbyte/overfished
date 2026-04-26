import * as Dialog from "@radix-ui/react-dialog";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Database,
  FileText,
  Filter,
  Loader2,
  MapPin,
  Minimize2,
  Network,
  Radar,
  Satellite,
  Scale,
  Ship as ShipIcon,
  Sparkles,
  Upload,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  type AgentRunResponse,
  type AgentTextBlock,
} from "@/lib/agentApi";
import {
  OUTPUT_KEYS,
  PREFETCH_KEYS,
  SUPERVISOR_KEYS,
  useAgentPipeline,
  type PipelineState,
  type StageKey,
  type StageState,
  type StageStatus,
} from "@/state/agentPipeline";

interface StageMeta {
  key: StageKey;
  label: string;
  icon: LucideIcon;
}

const STAGE_LABELS: Record<StageKey, { label: string; icon: LucideIcon }> = {
  ais: { label: "AIS", icon: Radar },
  sar: { label: "SAR", icon: Satellite },
  regional_laws: { label: "Regional Laws", icon: Scale },
  historical_fishing: { label: "Historical Fishing", icon: ShipIcon },
  nearest_port: { label: "Nearest Port", icon: MapPin },
  fishing_filter: { label: "Fishing Filter", icon: Filter },
  classify_vessels_iuu_batch: { label: "Classify Vessels (IUU)", icon: Network },
  render_evidence_pdf: { label: "Render Evidence PDF", icon: FileText },
  synthesis: { label: "Synthesis", icon: Sparkles },
  supabase_upload: { label: "Upload to Supabase", icon: Upload },
};

const PREFETCH_STAGES: StageMeta[] = PREFETCH_KEYS.map((k) => ({ key: k, ...STAGE_LABELS[k] }));
const SUPERVISOR_STAGES: StageMeta[] = SUPERVISOR_KEYS.map((k) => ({ key: k, ...STAGE_LABELS[k] }));
const OUTPUT_STAGES: StageMeta[] = OUTPUT_KEYS.map((k) => ({ key: k, ...STAGE_LABELS[k] }));

export function AgentPipelineModal() {
  const { state, request, modalOpen, minimizeModal, closeModal, reset } = useAgentPipeline();

  const phase1Done = useMemo(
    () => PREFETCH_STAGES.every((s) => state.stages[s.key]?.status === "done"),
    [state.stages],
  );
  const phase2Done = useMemo(
    () => SUPERVISOR_STAGES.every((s) => state.stages[s.key]?.status === "done"),
    [state.stages],
  );
  const phase3Done = useMemo(() => state.result !== null, [state.result]);

  const open = modalOpen && request !== null;

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(o) => {
        if (!o) minimizeModal();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[1000] bg-black/80 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in" />
        <Dialog.Content className="glass-surface fixed left-1/2 top-1/2 z-[1001] flex max-h-[90vh] w-[92vw] max-w-[760px] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-cyan-500/20 shadow-2xl">
          <div className="flex items-start justify-between gap-3 border-b border-white/10 px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="font-display text-base font-semibold text-slate-100">
                Agent Pipeline
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 font-mono text-[11px] text-slate-400">
                {request ? (
                  <>
                    {request.latitude.toFixed(4)}, {request.longitude.toFixed(4)}
                    {request.radiusMiles ? ` · ${request.radiusMiles} mi` : ""}
                    {request.portCountryCode ? ` · ${request.portCountryCode}` : ""}
                  </>
                ) : (
                  "—"
                )}
              </Dialog.Description>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={minimizeModal}
                className="rounded p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-slate-200"
                aria-label="Minimize"
                title="Keep running, minimize to chip"
              >
                <Minimize2 size={14} />
              </button>
              <button
                type="button"
                onClick={() => {
                  reset();
                  closeModal();
                }}
                className="rounded p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-slate-200"
                aria-label="Cancel and close"
                title="Cancel run and close"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          <div className="scrollbar-themed flex-1 space-y-4 overflow-y-auto px-5 py-4">
            <Phase
              index={1}
              title="Prefetch"
              subtitle="Parallel data fetches"
              startedAt={state.phase1StartedAt}
              finishedAt={state.phase1FinishedAt}
              done={phase1Done}
              defaultOpen
            >
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {PREFETCH_STAGES.map((s) => (
                  <StageCard key={s.key} meta={s} state={state.stages[s.key]} />
                ))}
              </div>
            </Phase>

            <Phase
              index={2}
              title="Supervisor"
              subtitle="LangChain agent loop"
              startedAt={state.phase2StartedAt}
              finishedAt={state.phase2FinishedAt}
              done={phase2Done}
              defaultOpen={phase1Done && !phase2Done}
            >
              <div className="space-y-1.5">
                {SUPERVISOR_STAGES.map((s, i) => (
                  <TimelineRow
                    key={s.key}
                    meta={s}
                    state={state.stages[s.key]}
                    isLast={i === SUPERVISOR_STAGES.length - 1}
                  />
                ))}
              </div>
            </Phase>

            <Phase
              index={3}
              title="Output"
              subtitle="Persist & finalize"
              startedAt={state.phase3StartedAt}
              finishedAt={state.result ? Date.now() : null}
              done={phase3Done}
              defaultOpen={phase2Done}
            >
              <div className="space-y-1.5">
                {OUTPUT_STAGES.map((s, i) => (
                  <TimelineRow
                    key={s.key}
                    meta={s}
                    state={state.stages[s.key]}
                    isLast={i === OUTPUT_STAGES.length - 1 && !state.result}
                  />
                ))}
                <ResultRow result={state.result} />
              </div>
            </Phase>

            {state.error && (
              <div className="flex items-start gap-2 rounded-md border border-accent-iuu/40 bg-accent-iuu/10 p-3 text-[12px] text-accent-iuu">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{state.error}</span>
              </div>
            )}

            {state.result && <ResultPanel result={state.result} />}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// ── Floating restore chip ───────────────────────────────────────────────

export function AgentPipelineMinimizedChip() {
  const { state, request, modalOpen, status, openModal, reset } = useAgentPipeline();

  if (modalOpen || !request || status === "idle") return null;

  const summary = computeSummary(state);
  const colorClass =
    status === "error"
      ? "border-accent-iuu/40 bg-accent-iuu/15 text-accent-iuu"
      : status === "done"
        ? "border-accent-safe/40 bg-accent-safe/15 text-accent-safe"
        : "border-cyan-500/40 bg-cyan-500/15 text-cyan-300";

  const label =
    status === "error"
      ? "Pipeline error"
      : status === "done"
        ? "Pipeline complete"
        : summary.currentLabel ?? "Pipeline running";

  return (
    <div className="pointer-events-auto fixed bottom-20 right-6 z-[999]">
      <div
        className={`glass-surface flex items-center gap-3 rounded-full border px-3 py-2 shadow-xl ${colorClass}`}
      >
        <button
          type="button"
          onClick={openModal}
          className="flex items-center gap-2.5 pr-1 text-left"
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-black/20">
            {status === "running" ? (
              <Loader2 size={13} className="animate-spin" />
            ) : status === "error" ? (
              <AlertCircle size={13} />
            ) : (
              <Check size={13} strokeWidth={3} />
            )}
          </span>
          <span className="flex flex-col">
            <span className="font-display text-[12px] font-semibold leading-tight">
              {label}
            </span>
            <span className="font-mono text-[10px] leading-tight opacity-80">
              {summary.doneCount}/{summary.totalCount} steps
              {summary.elapsed != null ? ` · ${summary.elapsed.toFixed(0)}s` : ""}
            </span>
          </span>
        </button>
        <button
          type="button"
          onClick={reset}
          className="rounded-full p-1 transition hover:bg-black/20"
          aria-label="Dismiss"
          title="Dismiss"
        >
          <X size={12} />
        </button>
      </div>
    </div>
  );
}

function computeSummary(state: PipelineState): {
  doneCount: number;
  totalCount: number;
  currentLabel: string | null;
  elapsed: number | null;
} {
  const allKeys: StageKey[] = [...PREFETCH_KEYS, ...SUPERVISOR_KEYS, ...OUTPUT_KEYS];
  const totalCount = allKeys.length;
  let doneCount = 0;
  let currentKey: StageKey | null = null;
  for (const k of allKeys) {
    const s = state.stages[k];
    if (s?.status === "done") doneCount += 1;
    else if (s?.status === "running" && !currentKey) currentKey = k;
  }
  // If no running stage, show the first not-done stage as "queued".
  if (!currentKey) {
    for (const k of allKeys) {
      if (state.stages[k]?.status !== "done") {
        currentKey = k;
        break;
      }
    }
  }

  const start = state.phase1StartedAt;
  const elapsed = start ? (Date.now() - start) / 1000 : null;

  return {
    doneCount,
    totalCount,
    currentLabel: currentKey ? STAGE_LABELS[currentKey].label : null,
    elapsed,
  };
}

// ── Phase / row primitives ──────────────────────────────────────────────

function Phase({
  index,
  title,
  subtitle,
  startedAt,
  finishedAt,
  done,
  defaultOpen = false,
  children,
}: {
  index: number;
  title: string;
  subtitle: string;
  startedAt: number | null;
  finishedAt: number | null;
  done: boolean;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const wasDoneRef = useRef(done);

  useEffect(() => {
    if (done && !wasDoneRef.current) setOpen(false);
    if (!done && startedAt) setOpen(true);
    wasDoneRef.current = done;
  }, [done, startedAt]);

  const elapsed = phaseElapsedSeconds(startedAt, finishedAt);

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition hover:bg-white/5"
      >
        {open ? (
          <ChevronDown size={14} className="shrink-0 text-slate-400" />
        ) : (
          <ChevronRight size={14} className="shrink-0 text-slate-400" />
        )}
        <PhaseStatusBadge done={done} active={!!startedAt && !done} />
        <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
          Phase {index}
        </span>
        <span className="font-display text-sm font-semibold text-slate-100">
          {title}
        </span>
        <span className="hidden text-[11px] text-slate-500 sm:inline">· {subtitle}</span>
        <span className="ml-auto font-mono text-[11px] text-slate-400">
          {elapsed != null ? `${elapsed.toFixed(1)}s` : ""}
        </span>
      </button>
      {open && <div className="border-t border-white/10 px-3 py-3">{children}</div>}
    </section>
  );
}

function PhaseStatusBadge({ done, active }: { done: boolean; active: boolean }) {
  if (done) {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent-safe/20 text-accent-safe">
        <Check size={12} strokeWidth={3} />
      </span>
    );
  }
  if (active) {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-cyan-500/20 text-cyan-300">
        <Loader2 size={12} className="animate-spin" />
      </span>
    );
  }
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/5 text-slate-500">
      <CircleDashed size={12} />
    </span>
  );
}

function StageCard({ meta, state }: { meta: StageMeta; state?: StageState }) {
  const status = state?.status ?? "pending";
  const Icon = meta.icon;
  const elapsed = stageElapsedSeconds(state);

  return (
    <div
      className={`flex items-center gap-2.5 rounded-lg border p-2.5 transition ${
        status === "done"
          ? "border-accent-safe/30 bg-accent-safe/5"
          : status === "running"
            ? "border-cyan-500/40 bg-cyan-500/5"
            : status === "error"
              ? "border-accent-iuu/40 bg-accent-iuu/5"
              : "border-white/8 bg-white/[0.02]"
      }`}
    >
      <span
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
          status === "done"
            ? "bg-accent-safe/15 text-accent-safe"
            : status === "running"
              ? "bg-cyan-500/15 text-cyan-300"
              : status === "error"
                ? "bg-accent-iuu/15 text-accent-iuu"
                : "bg-white/5 text-slate-500"
        }`}
      >
        <Icon size={14} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate font-display text-[12px] font-semibold text-slate-100">
          {meta.label}
        </div>
        <div className="font-mono text-[10px] text-slate-500">
          {status === "running" && "running…"}
          {status === "done" && (elapsed != null ? `done · ${elapsed.toFixed(1)}s` : "done")}
          {status === "error" && "error"}
          {status === "pending" && "queued"}
        </div>
      </div>
      <StageStatusIcon status={status} />
    </div>
  );
}

function TimelineRow({
  meta,
  state,
  isLast,
}: {
  meta: StageMeta;
  state?: StageState;
  isLast: boolean;
}) {
  const status = state?.status ?? "pending";
  const Icon = meta.icon;
  const elapsed = stageElapsedSeconds(state);
  const detail = state?.detail;

  return (
    <div className="relative flex gap-3">
      <div className="flex w-7 shrink-0 flex-col items-center">
        <span
          className={`flex h-7 w-7 items-center justify-center rounded-full border ${
            status === "done"
              ? "border-accent-safe/40 bg-accent-safe/15 text-accent-safe"
              : status === "running"
                ? "border-cyan-500/50 bg-cyan-500/15 text-cyan-300"
                : status === "error"
                  ? "border-accent-iuu/50 bg-accent-iuu/15 text-accent-iuu"
                  : "border-white/10 bg-white/[0.04] text-slate-500"
          }`}
        >
          <Icon size={13} />
        </span>
        {!isLast && <span className="my-0.5 w-px flex-1 bg-white/10" />}
      </div>
      <div className="min-w-0 flex-1 pb-2">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-display text-[13px] font-semibold text-slate-100">
            {meta.label}
          </span>
          <span className="font-mono text-[10px] text-slate-500">
            {status === "running" && "running…"}
            {status === "done" && (elapsed != null ? `${elapsed.toFixed(1)}s` : "done")}
            {status === "error" && "error"}
            {status === "pending" && "queued"}
          </span>
        </div>
        <StageDetail stageKey={meta.key} detail={detail} />
      </div>
    </div>
  );
}

function StageDetail({
  stageKey,
  detail,
}: {
  stageKey: StageKey;
  detail?: Record<string, unknown>;
}) {
  if (!detail) return null;

  if (stageKey === "classify_vessels_iuu_batch" && Array.isArray(detail.mmsis)) {
    const mmsis = detail.mmsis as string[];
    if (!mmsis.length) return null;
    return (
      <div className="mt-1.5">
        <div className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
          {mmsis.length} vessels
        </div>
        <div className="mt-1 flex flex-wrap gap-1">
          {mmsis.slice(0, 12).map((m) => (
            <span
              key={m}
              className="rounded bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-slate-300"
            >
              {m}
            </span>
          ))}
          {mmsis.length > 12 && (
            <span className="rounded bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
              +{mmsis.length - 12} more
            </span>
          )}
        </div>
      </div>
    );
  }

  if (stageKey === "render_evidence_pdf" && typeof detail.mmsi === "string") {
    return (
      <div className="mt-1 font-mono text-[10px] text-slate-400">
        MMSI {detail.mmsi as string}
      </div>
    );
  }

  return null;
}

function ResultRow({ result }: { result: AgentRunResponse | null }) {
  return (
    <div className="relative flex gap-3">
      <div className="flex w-7 shrink-0 flex-col items-center">
        <span
          className={`flex h-7 w-7 items-center justify-center rounded-full border ${
            result
              ? "border-accent-safe/40 bg-accent-safe/15 text-accent-safe"
              : "border-white/10 bg-white/[0.04] text-slate-500"
          }`}
        >
          <Database size={13} />
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-display text-[13px] font-semibold text-slate-100">
            Complete
          </span>
          <span className="font-mono text-[10px] text-slate-500">
            {result ? "received" : "waiting"}
          </span>
        </div>
      </div>
    </div>
  );
}

function StageStatusIcon({ status }: { status: StageStatus }) {
  if (status === "done") return <Check size={13} className="text-accent-safe" strokeWidth={3} />;
  if (status === "running") return <Loader2 size={13} className="animate-spin text-cyan-300" />;
  if (status === "error") return <AlertCircle size={13} className="text-accent-iuu" />;
  return <CircleDashed size={13} className="text-slate-500" />;
}

function renderMarkdownLine(line: string, idx: number): ReactNode {
  // Bold markers: **text**
  const parts = line.split(/(\*\*[^*]+\*\*)/g);
  const rendered = parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <span key={i} className="font-semibold text-slate-100">
          {part.slice(2, -2)}
        </span>
      );
    }
    return part;
  });
  return <span key={idx}>{rendered}</span>;
}

function ResultPanel({ result }: { result: AgentRunResponse }) {
  const text = coerceOutput(result);

  const sections = useMemo(() => {
    if (!text) return [];
    const lines = text.split("\n");
    const out: { type: "h2" | "h3" | "text" | "bullet" | "divider"; content: string }[] = [];
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) continue;
      if (line === "---") {
        out.push({ type: "divider", content: "" });
      } else if (line.startsWith("## ")) {
        out.push({ type: "h2", content: line.slice(3).trim() });
      } else if (line.startsWith("### ")) {
        out.push({ type: "h3", content: line.slice(4).trim() });
      } else if (line.startsWith("- ")) {
        out.push({ type: "bullet", content: line.slice(2).trim() });
      } else {
        out.push({ type: "text", content: line });
      }
    }
    return out;
  }, [text]);

  return (
    <div className="space-y-2 rounded-xl border border-white/10 bg-white/[0.02] p-3">
      <div className="flex items-center justify-between text-[11px] text-slate-400">
        <span className="font-mono">agent: {result.agent}</span>
        {result.case_id && (
          <span className="font-mono text-slate-500">case: {result.case_id}</span>
        )}
      </div>
      {result.summary && (
        <p className="text-[12px] leading-snug text-slate-200">{result.summary}</p>
      )}
      {sections.length > 0 && (
        <div className="scrollbar-themed max-h-[400px] space-y-2 overflow-y-auto pr-1">
          {sections.map((s, i) => {
            switch (s.type) {
              case "h2":
                return (
                  <h3
                    key={i}
                    className="border-b border-cyan-500/20 pb-1 pt-2 font-display text-[13px] font-bold uppercase tracking-wide text-cyan-400"
                  >
                    {renderMarkdownLine(s.content, i)}
                  </h3>
                );
              case "h3":
                return (
                  <h4
                    key={i}
                    className="pt-1.5 font-display text-[12px] font-semibold text-slate-200"
                  >
                    {renderMarkdownLine(s.content, i)}
                  </h4>
                );
              case "bullet":
                return (
                  <div key={i} className="flex gap-2 pl-1 text-[11px] leading-snug text-slate-300">
                    <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-cyan-500/60" />
                    <span>{renderMarkdownLine(s.content, i)}</span>
                  </div>
                );
              case "divider":
                return <hr key={i} className="border-white/8" />;
              default:
                return (
                  <p key={i} className="text-[11px] leading-snug text-slate-300">
                    {renderMarkdownLine(s.content, i)}
                  </p>
                );
            }
          })}
        </div>
      )}
      {result.pdf_path && (
        <div className="font-mono text-[10px] text-slate-400">
          PDF: <span className="text-slate-200">{result.pdf_path}</span>
        </div>
      )}
    </div>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────

function stageElapsedSeconds(state?: StageState): number | null {
  if (!state?.startedAt) return null;
  const end = state.finishedAt ?? Date.now();
  return (end - state.startedAt) / 1000;
}

function phaseElapsedSeconds(start: number | null, end: number | null): number | null {
  if (!start) return null;
  return ((end ?? Date.now()) - start) / 1000;
}

function coerceOutput(data: AgentRunResponse): string {
  const out = data.output;
  if (typeof out === "string") return out;
  if (Array.isArray(out)) {
    return out
      .map((b: AgentTextBlock | string) => {
        if (typeof b === "string") return b;
        if (b && typeof b.text === "string") return b.text;
        try {
          return JSON.stringify(b);
        } catch {
          return String(b);
        }
      })
      .filter(Boolean)
      .join("\n");
  }
  return "";
}
