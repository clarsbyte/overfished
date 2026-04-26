import { useMutation } from "@tanstack/react-query";
import { Bot, Brain, Crosshair, Gavel, Play, Radar, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { CollapsiblePanel, type PanelStatus } from "@/components/CollapsiblePanel";
import { buildModelContext, useSequenceLatest } from "@/hooks/useSequenceLatest";
import {
  agentApi,
  type AgentRunResponse,
  type AgentTextBlock,
  type ModelContext,
} from "@/lib/agentApi";
import type { Ship } from "@/types/ship";

function coerceOutput(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value
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

function pickAgentText(data: AgentRunResponse | undefined): string {
  if (!data) return "";
  return (
    coerceOutput(data.output) ||
    coerceOutput(data.message) ||
    JSON.stringify(data, null, 2)
  );
}

interface Props {
  selectedShip: Ship | null;
  className?: string;
}

type TabId = "gfw" | "vessel" | "law" | "complete";

const TABS: { id: TabId; label: string; icon: JSX.Element; eta: string }[] = [
  { id: "gfw", label: "GFW", icon: <Radar size={12} />, eta: "30-60 s" },
  { id: "vessel", label: "AIS", icon: <Crosshair size={12} />, eta: "30-120 s" },
  { id: "law", label: "Law", icon: <Gavel size={12} />, eta: "10-30 s" },
  { id: "complete", label: "Complete", icon: <Workflow size={12} />, eta: "60-120 s" },
];

export function AgentsPanel({ selectedShip, className }: Props) {
  const [tab, setTab] = useState<TabId>("gfw");
  const [query, setQuery] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [mmsi, setMmsi] = useState("");
  const [elapsed, setElapsed] = useState<number | null>(null);

  useEffect(() => {
    if (!selectedShip) return;
    setQuery(selectedShip.mmsi);
    setMmsi(selectedShip.mmsi);
    setLat(selectedShip.lat.toFixed(4));
    setLon(selectedShip.lon.toFixed(4));
  }, [selectedShip]);

  const seq = useSequenceLatest();

  const modelContext: ModelContext | null = useMemo(() => {
    if (!seq.byMmsi.size) return null;
    const targetMmsi = selectedShip?.mmsi ?? mmsi ?? null;
    const flagged: { mmsi: string; lat: number; lon: number }[] = [];
    if (selectedShip) {
      for (const [m, v] of seq.byMmsi) {
        if (m === selectedShip.mmsi) continue;
        if (v.model_risk === "safe") continue;
        flagged.push({
          mmsi: m,
          lat: 0,
          lon: 0,
        });
      }
    }
    const nearbyMmsis = flagged.slice(0, 5).map((f) => f.mmsi);
    return buildModelContext(
      targetMmsi,
      seq.byMmsi,
      seq.reportNarration,
      seq.generatedAt,
      seq.source,
      nearbyMmsis,
    );
  }, [seq.byMmsi, seq.reportNarration, seq.generatedAt, seq.source, selectedShip, mmsi]);

  const mutation = useMutation<AgentRunResponse, Error, void>({
    mutationFn: async () => {
      const start = performance.now();
      try {
        if (tab === "gfw") {
          const q = query || selectedShip?.mmsi || "";
          if (!q) throw new Error("Query (MMSI/IMO/name) required");
          return await agentApi.gfw(q, 365, modelContext);
        }
        const la = parseFloat(lat);
        const lo = parseFloat(lon);
        if (!Number.isFinite(la) || !Number.isFinite(lo)) {
          throw new Error("Latitude and longitude required");
        }
        if (tab === "vessel") return await agentApi.vessel(la, lo, 50, modelContext);
        if (tab === "law") return await agentApi.law(la, lo, modelContext);
        return await agentApi.complete(la, lo, mmsi || undefined, 50, modelContext);
      } finally {
        setElapsed((performance.now() - start) / 1000);
      }
    },
  });

  const status: PanelStatus = mutation.isPending
    ? "running"
    : mutation.isError
      ? "error"
      : mutation.data
        ? "ok"
        : "idle";

  const activeTab = TABS.find((t) => t.id === tab)!;

  return (
    <CollapsiblePanel
      id="agents"
      title="Agents"
      icon={<Bot size={14} />}
      status={status}
      className={className}
      badge={
        selectedShip ? (
          <span className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-slate2-400">
            {selectedShip.mmsi}
          </span>
        ) : null
      }
    >
      <div className="space-y-3">
        <div className="flex flex-wrap gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] transition ${
                tab === t.id
                  ? "bg-accent-safe/20 text-accent-safe ring-1 ring-accent-safe/40"
                  : "bg-ink-900 text-slate2-400 hover:bg-ink-800"
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        <div className="space-y-2">
          {tab === "gfw" ? (
            <Field label="Query (MMSI / IMO / name)">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="412345678"
                className="w-full rounded border border-ink-800 bg-ink-900 px-2 py-1 font-mono text-[11px] text-slate2-200 focus:border-accent-safe focus:outline-none"
              />
            </Field>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <Field label="Latitude">
                <input
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                  placeholder="-0.5"
                  className="w-full rounded border border-ink-800 bg-ink-900 px-2 py-1 font-mono text-[11px] text-slate2-200 focus:border-accent-safe focus:outline-none"
                />
              </Field>
              <Field label="Longitude">
                <input
                  value={lon}
                  onChange={(e) => setLon(e.target.value)}
                  placeholder="-90.5"
                  className="w-full rounded border border-ink-800 bg-ink-900 px-2 py-1 font-mono text-[11px] text-slate2-200 focus:border-accent-safe focus:outline-none"
                />
              </Field>
              {tab === "complete" && (
                <Field label="MMSI (optional)">
                  <input
                    value={mmsi}
                    onChange={(e) => setMmsi(e.target.value)}
                    placeholder="412345678"
                    className="w-full rounded border border-ink-800 bg-ink-900 px-2 py-1 font-mono text-[11px] text-slate2-200 focus:border-accent-safe focus:outline-none"
                  />
                </Field>
              )}
            </div>
          )}

          <ModelContextPreview ctx={modelContext} ready={seq.ready} training={seq.isTraining} />

          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="flex w-full items-center justify-center gap-1.5 rounded bg-accent-safe/10 px-2 py-1.5 text-xs font-medium text-accent-safe ring-1 ring-accent-safe/40 transition hover:bg-accent-safe/20 disabled:opacity-50"
          >
            <Play size={12} />
            {mutation.isPending ? `Running... (~${activeTab.eta})` : `Run ${activeTab.label}`}
          </button>

          {mutation.isPending && (
            <p className="text-[10px] text-slate2-400">
              Long-running call. Backing off requires the BFF on http://localhost:8000.
            </p>
          )}

          {mutation.isError && (
            <pre className="whitespace-pre-wrap break-words rounded border border-accent-iuu/40 bg-accent-iuu/10 p-2 text-[11px] text-accent-iuu">
              {(mutation.error as Error).message}
            </pre>
          )}

          {mutation.data && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[10px] text-slate2-400">
                <span className="font-mono">
                  {String(
                    (mutation.data as { agent?: string; status?: string }).agent ??
                      mutation.data.status ??
                      "agent",
                  )}
                </span>
                {elapsed !== null && <span>{elapsed.toFixed(1)} s</span>}
              </div>
              {modelContext?.selected && (
                <p className="rounded border border-ink-800 bg-ink-950 p-2 text-[10px] text-slate2-400">
                  <span className="text-slate2-300">Context attached:</span>{" "}
                  MMSI {modelContext.selected.mmsi} →{" "}
                  <span className="font-semibold uppercase">
                    {modelContext.selected.model_risk.replace("_", " ")}
                  </span>
                  .
                </p>
              )}
              <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap break-words rounded border border-ink-800 bg-ink-900 p-2 font-mono text-[11px] leading-snug text-slate2-200">
                {pickAgentText(mutation.data)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </CollapsiblePanel>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] uppercase tracking-wider text-slate2-400">
        {label}
      </span>
      {children}
    </label>
  );
}

function ModelContextPreview({
  ctx,
  ready,
  training,
}: {
  ctx: ModelContext | null;
  ready: boolean;
  training: boolean;
}) {
  if (!ctx) {
    return (
      <div className="rounded border border-dashed border-ink-800 bg-ink-950 p-2 text-[10px] text-slate2-400">
        <div className="flex items-center gap-1.5">
          <Brain size={12} className="text-slate2-500" />
          <span className="font-semibold uppercase tracking-wider">Model context</span>
        </div>
        <p className="mt-1">
          {training
            ? "Training RNN+BiLSTM on canonical 300 vessels…"
            : ready
              ? "No per-MMSI signal for this selection."
              : "Sequence model not yet ready — auto-training in background."}
        </p>
      </div>
    );
  }

  const { selected, nearby } = ctx;
  return (
    <div className="rounded border border-ink-800 bg-ink-950 p-2 text-[10px] text-slate2-300">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 font-semibold uppercase tracking-wider text-slate2-200">
          <Brain size={12} className="text-accent-safe" />
          Model context attached
        </span>
        {ctx.source && (
          <span className="font-mono text-slate2-500">{ctx.source}</span>
        )}
      </div>
      {selected && (
        <p className="mt-1 leading-snug">
          MMSI <span className="font-mono">{selected.mmsi}</span> →{" "}
          <span className="font-semibold uppercase">
            {selected.model_risk.replace("_", " ")}
          </span>{" "}
          (mean P {Math.round(selected.mean_confidence * 100)}%
          {selected.alias_mmsi
            ? `, alias ${selected.alias_mmsi} ${Math.round(selected.alias_share * 100)}%`
            : ""}
          ).
        </p>
      )}
      {selected?.narration && (
        <p className="mt-1 italic text-slate2-400">{selected.narration}</p>
      )}
      {nearby.length > 0 && (
        <p className="mt-1 text-slate2-400">
          + {nearby.length} nearby flagged:{" "}
          {nearby
            .map((n) => `${n.mmsi} (${n.model_risk.replace("_", " ")})`)
            .join(", ")}
        </p>
      )}
    </div>
  );
}
