import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  completeStreamUrl,
  type AgentRunResponse,
  type AgentStreamEvent,
} from "@/lib/agentApi";

// ── Stages & metadata ───────────────────────────────────────────────────

export type StageKey =
  | "ais"
  | "sar"
  | "regional_laws"
  | "historical_fishing"
  | "nearest_port"
  | "fishing_filter"
  | "classify_vessels_iuu_batch"
  | "render_evidence_pdf"
  | "synthesis"
  | "supabase_upload";

export type StageStatus = "pending" | "running" | "done" | "error";

export interface StageState {
  status: StageStatus;
  detail?: Record<string, unknown>;
  startedAt?: number;
  finishedAt?: number;
}

export type StageMap = Partial<Record<StageKey, StageState>>;

export const PREFETCH_KEYS: StageKey[] = [
  "ais",
  "sar",
  "regional_laws",
  "historical_fishing",
  "nearest_port",
  "fishing_filter",
];

export const SUPERVISOR_KEYS: StageKey[] = [
  "classify_vessels_iuu_batch",
  "render_evidence_pdf",
  "synthesis",
];

export const OUTPUT_KEYS: StageKey[] = ["supabase_upload"];

export interface PipelineState {
  stages: StageMap;
  phase1StartedAt: number | null;
  phase1FinishedAt: number | null;
  phase2StartedAt: number | null;
  phase2FinishedAt: number | null;
  phase3StartedAt: number | null;
  result: AgentRunResponse | null;
  error: string | null;
  closed: boolean;
}

export interface PipelineRequest {
  latitude: number;
  longitude: number;
  radiusMiles?: number;
  portCountryCode?: string;
  startedAt: number;
}

export type PipelineRunStatus = "idle" | "running" | "done" | "error";

const INITIAL_STATE: PipelineState = {
  stages: {},
  phase1StartedAt: null,
  phase1FinishedAt: null,
  phase2StartedAt: null,
  phase2FinishedAt: null,
  phase3StartedAt: null,
  result: null,
  error: null,
  closed: false,
};

// ── Reducer ─────────────────────────────────────────────────────────────

function reduce(prev: PipelineState, evt: AgentStreamEvent): PipelineState {
  const now = Date.now();

  if (evt.stage === "complete") {
    return { ...prev, result: evt.result ?? null, closed: true };
  }

  if (evt.stage === "error") {
    const detail = evt.detail;
    const message =
      typeof detail?.message === "string"
        ? (detail.message as string)
        : detail
          ? JSON.stringify(detail)
          : "Pipeline error";
    return { ...prev, error: message, closed: true };
  }

  if (evt.stage === "prefetch") {
    if (evt.status === "started") {
      return { ...prev, phase1StartedAt: prev.phase1StartedAt ?? now };
    }
    return prev;
  }

  if (evt.stage === "supervisor") {
    if (evt.status === "started") {
      return {
        ...prev,
        phase2StartedAt: prev.phase2StartedAt ?? now,
        phase1FinishedAt: prev.phase1FinishedAt ?? now,
      };
    }
    return prev;
  }

  const key = evt.stage as StageKey;
  const known =
    PREFETCH_KEYS.includes(key) ||
    SUPERVISOR_KEYS.includes(key) ||
    OUTPUT_KEYS.includes(key);
  if (!known) return prev;

  const existing = prev.stages[key];
  let next: StageState;
  if (evt.status === "running" || evt.status === "started") {
    next = {
      status: "running",
      detail: { ...(existing?.detail ?? {}), ...(evt.detail ?? {}) },
      startedAt: existing?.startedAt ?? now,
    };
  } else if (evt.status === "done" || evt.status === "complete") {
    next = {
      status: "done",
      detail: { ...(existing?.detail ?? {}), ...(evt.detail ?? {}) },
      startedAt: existing?.startedAt ?? now,
      finishedAt: now,
    };
  } else if (evt.status === "error") {
    next = {
      status: "error",
      detail: { ...(existing?.detail ?? {}), ...(evt.detail ?? {}) },
      startedAt: existing?.startedAt ?? now,
      finishedAt: now,
    };
  } else {
    return prev;
  }

  const stages: StageMap = { ...prev.stages, [key]: next };
  const updates: Partial<PipelineState> = { stages };

  if (PREFETCH_KEYS.includes(key)) {
    const allDone = PREFETCH_KEYS.every((k) => stages[k]?.status === "done");
    if (allDone) updates.phase1FinishedAt = prev.phase1FinishedAt ?? now;
  }

  if (key === "synthesis" && next.status === "done") {
    updates.phase2FinishedAt = prev.phase2FinishedAt ?? now;
  }

  if (key === "supabase_upload" && next.status === "running") {
    updates.phase3StartedAt = prev.phase3StartedAt ?? now;
  }

  return { ...prev, ...updates };
}

// ── SSE reader ──────────────────────────────────────────────────────────

async function runStream(
  url: string,
  signal: AbortSignal,
  onEvent: (evt: AgentStreamEvent) => void,
): Promise<void> {
  const res = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "text/event-stream",
      "ngrok-skip-browser-warning": "true",
    },
    signal,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = findFrameSeparator(buffer)) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + (buffer[sep] === "\r" ? 4 : 2));
      const data = parseFrameData(frame);
      if (!data) continue;
      try {
        onEvent(JSON.parse(data) as AgentStreamEvent);
      } catch {
        // ignore malformed frames
      }
    }
  }
}

function findFrameSeparator(buf: string): number {
  const a = buf.indexOf("\n\n");
  const b = buf.indexOf("\r\n\r\n");
  if (a === -1) return b;
  if (b === -1) return a;
  return Math.min(a, b);
}

function parseFrameData(frame: string): string | null {
  const lines = frame.split(/\r?\n/);
  const data: string[] = [];
  for (const line of lines) {
    if (line.startsWith("data:")) {
      data.push(line.slice(5).replace(/^ /, ""));
    }
  }
  return data.length ? data.join("\n") : null;
}

// ── Context ─────────────────────────────────────────────────────────────

interface StartArgs {
  latitude: number;
  longitude: number;
  radiusMiles?: number;
  portCountryCode?: string;
}

export interface AgentPipelineContextValue {
  status: PipelineRunStatus;
  state: PipelineState;
  request: PipelineRequest | null;
  modalOpen: boolean;
  start: (args: StartArgs) => void;
  cancel: () => void;
  reset: () => void;
  openModal: () => void;
  minimizeModal: () => void;
  closeModal: () => void;
}

const Ctx = createContext<AgentPipelineContextValue | null>(null);

export function AgentPipelineProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PipelineState>(INITIAL_STATE);
  const [request, setRequest] = useState<PipelineRequest | null>(null);
  const [status, setStatus] = useState<PipelineRunStatus>("idle");
  const [modalOpen, setModalOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Derive status from state changes
  useEffect(() => {
    if (!request) {
      setStatus("idle");
      return;
    }
    if (state.error) setStatus("error");
    else if (state.result) setStatus("done");
    else setStatus("running");
  }, [request, state.error, state.result]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState(INITIAL_STATE);
    setRequest(null);
    setStatus("idle");
  }, []);

  const start = useCallback((args: StartArgs) => {
    abortRef.current?.abort();

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const newReq: PipelineRequest = {
      latitude: args.latitude,
      longitude: args.longitude,
      radiusMiles: args.radiusMiles,
      portCountryCode: args.portCountryCode,
      startedAt: Date.now(),
    };

    setState(INITIAL_STATE);
    setRequest(newReq);
    setStatus("running");
    setModalOpen(true);

    const url = completeStreamUrl(
      args.latitude,
      args.longitude,
      args.radiusMiles,
      args.portCountryCode,
    );
    void runStream(url, ctrl.signal, (evt) => {
      setState((prev) => reduce(prev, evt));
    }).catch((err: unknown) => {
      if ((err as { name?: string })?.name === "AbortError") return;
      const message = err instanceof Error ? err.message : "Connection lost";
      setState((prev) =>
        prev.closed || prev.result
          ? prev
          : { ...prev, error: prev.error ?? message, closed: true },
      );
    });
  }, []);

  const openModal = useCallback(() => setModalOpen(true), []);
  const minimizeModal = useCallback(() => setModalOpen(false), []);
  const closeModal = useCallback(() => setModalOpen(false), []);

  const value: AgentPipelineContextValue = {
    status,
    state,
    request,
    modalOpen,
    start,
    cancel,
    reset,
    openModal,
    minimizeModal,
    closeModal,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAgentPipeline(): AgentPipelineContextValue {
  const ctx = useContext(Ctx);
  if (!ctx) {
    throw new Error("useAgentPipeline must be used within AgentPipelineProvider");
  }
  return ctx;
}
