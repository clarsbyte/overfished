import { useMutation } from "@tanstack/react-query";
import { Bot, MapPin, Play, Radar, Workflow } from "lucide-react";
import { useEffect, useState } from "react";

import { CollapsiblePanel, type PanelStatus } from "@/components/CollapsiblePanel";
import {
  agentApi,
  type AgentRunResponse,
  type AgentTextBlock,
} from "@/lib/agentApi";
import type { Ship } from "@/types/ship";

function coerceOutput(data: AgentRunResponse | undefined): string {
  if (!data) return "";
  const out = data.output;
  if (typeof out === "string" && out) return out;
  if (Array.isArray(out)) {
    const text = out
      .map((b: AgentTextBlock | string) => {
        if (typeof b === "string") return b;
        if (b && typeof b.text === "string") return b.text;
        try { return JSON.stringify(b); } catch { return String(b); }
      })
      .filter(Boolean)
      .join("\n");
    if (text) return text;
  }
  if (data.summary) return data.summary;
  return JSON.stringify(data, null, 2);
}

interface Props {
  selectedShip: Ship | null;
  className?: string;
  onRequestGlobePick?: (cb: (lat: number, lng: number) => void) => void;
}

type TabId = "gfw" | "complete";

const TABS: { id: TabId; label: string; icon: JSX.Element; eta: string }[] = [
  { id: "gfw", label: "GFW", icon: <Radar size={12} />, eta: "30-60 s" },
  { id: "complete", label: "Complete", icon: <Workflow size={12} />, eta: "2-3 min" },
];

export function AgentsPanel({ selectedShip, className, onRequestGlobePick }: Props) {
  const [tab, setTab] = useState<TabId>("gfw");
  const [query, setQuery] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [portCountryCode, setPortCountryCode] = useState("ECU");
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [awaitingPin, setAwaitingPin] = useState(false);

  const handlePlacePin = () => {
    if (!onRequestGlobePick) return;
    setAwaitingPin(true);
    onRequestGlobePick((pickedLat, pickedLng) => {
      setLat(pickedLat.toFixed(5));
      setLon(pickedLng.toFixed(5));
      setAwaitingPin(false);
    });
  };

  useEffect(() => {
    if (!selectedShip) return;
    setQuery(selectedShip.mmsi);
    setLat(selectedShip.lat.toFixed(4));
    setLon(selectedShip.lon.toFixed(4));
  }, [selectedShip]);

  const mutation = useMutation<AgentRunResponse, Error, void>({
    mutationFn: async () => {
      const start = performance.now();
      try {
        if (tab === "gfw") {
          const q = query || selectedShip?.mmsi || "";
          if (!q) throw new Error("Query (MMSI/IMO/name) required");
          return await agentApi.gfw(q);
        }
        const la = parseFloat(lat);
        const lo = parseFloat(lon);
        if (!Number.isFinite(la) || !Number.isFinite(lo)) {
          throw new Error("Latitude and longitude required");
        }
        return await agentApi.complete(la, lo, portCountryCode || undefined);
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
            <>
            {onRequestGlobePick && (
              <button
                onClick={handlePlacePin}
                disabled={awaitingPin}
                className={`flex w-full items-center justify-center gap-1.5 rounded px-2 py-1.5 text-[11px] font-medium ring-1 transition ${
                  awaitingPin
                    ? "animate-pulse bg-yellow-400/20 text-yellow-300 ring-yellow-400/50"
                    : "bg-ink-900 text-slate2-300 ring-ink-700 hover:bg-ink-800 hover:text-slate2-100"
                }`}
              >
                <MapPin size={11} />
                {awaitingPin ? "Click globe to place pin…" : "Place pin on globe"}
              </button>
            )}
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
                <Field label="Port Country Code">
                  <input
                    value={portCountryCode}
                    onChange={(e) => setPortCountryCode(e.target.value.toUpperCase())}
                    placeholder="ECU"
                    maxLength={3}
                    className="w-full rounded border border-ink-800 bg-ink-900 px-2 py-1 font-mono text-[11px] text-slate2-200 focus:border-accent-safe focus:outline-none"
                  />
                </Field>
              )}
            </div>
            </>
          )}

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
              Long-running call. Backing off requires the BFF on http://localhost:8001.
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
                <span className="font-mono">agent: {mutation.data.agent}</span>
                {elapsed !== null && <span>{elapsed.toFixed(1)} s</span>}
              </div>
              <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap break-words rounded border border-ink-800 bg-ink-900 p-2 font-mono text-[11px] leading-snug text-slate2-200">
                {coerceOutput(mutation.data)}
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
