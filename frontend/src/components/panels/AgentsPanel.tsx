import { Bot, MapPin, Play, Workflow } from "lucide-react";
import { useEffect, useState } from "react";

import { CollapsiblePanel, type PanelStatus } from "@/components/CollapsiblePanel";
import { useAgentPipeline } from "@/state/agentPipeline";
import type { Ship } from "@/types/ship";

interface Props {
  selectedShip: Ship | null;
  className?: string;
  onRequestGlobePick?: (cb: (lat: number, lng: number) => void) => void;
}

export function AgentsPanel({ selectedShip, className, onRequestGlobePick }: Props) {
  const { status, start, openModal } = useAgentPipeline();

  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [radiusMiles, setRadiusMiles] = useState("50");
  const [portCountryCode, setPortCountryCode] = useState("ECU");
  const [awaitingPin, setAwaitingPin] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);

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
    setLat(selectedShip.lat.toFixed(4));
    setLon(selectedShip.lon.toFixed(4));
  }, [selectedShip]);

  const handleRun = () => {
    const la = parseFloat(lat);
    const lo = parseFloat(lon);
    if (!Number.isFinite(la) || !Number.isFinite(lo)) {
      setInputError("Latitude and longitude required");
      return;
    }
    const r = parseFloat(radiusMiles);
    setInputError(null);
    start({
      latitude: la,
      longitude: lo,
      radiusMiles: Number.isFinite(r) ? r : undefined,
      portCountryCode: portCountryCode || undefined,
    });
  };

  const isRunning = status === "running";
  const panelStatus: PanelStatus =
    status === "running"
      ? "running"
      : status === "error"
        ? "error"
        : status === "done"
          ? "ok"
          : "idle";

  return (
    <CollapsiblePanel
      id="agents"
      title="Agents"
      icon={<Bot size={14} />}
      status={panelStatus}
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
        <div className="flex items-center gap-1.5 text-[11px] text-slate2-400">
          <Workflow size={12} />
          <span>Complete · ~2–3 min</span>
        </div>

        <div className="space-y-2">
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
            <Field label="Radius (mi)">
              <input
                value={radiusMiles}
                onChange={(e) => setRadiusMiles(e.target.value)}
                placeholder="50"
                className="w-full rounded border border-ink-800 bg-ink-900 px-2 py-1 font-mono text-[11px] text-slate2-200 focus:border-accent-safe focus:outline-none"
              />
            </Field>
            <Field label="Port Country">
              <input
                value={portCountryCode}
                onChange={(e) => setPortCountryCode(e.target.value.toUpperCase())}
                placeholder="ECU"
                maxLength={3}
                className="w-full rounded border border-ink-800 bg-ink-900 px-2 py-1 font-mono text-[11px] text-slate2-200 focus:border-accent-safe focus:outline-none"
              />
            </Field>
          </div>

          <div className="flex items-stretch gap-2">
            <button
              onClick={handleRun}
              disabled={isRunning}
              className="flex flex-1 items-center justify-center gap-1.5 rounded bg-accent-safe/10 px-2 py-1.5 text-xs font-medium text-accent-safe ring-1 ring-accent-safe/40 transition hover:bg-accent-safe/20 disabled:opacity-50"
            >
              <Play size={12} />
              {isRunning ? "Running…" : "Run Complete"}
            </button>
            {status !== "idle" && (
              <button
                onClick={openModal}
                className="rounded bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-300 ring-1 ring-cyan-500/30 transition hover:bg-cyan-500/20"
                title="Show pipeline progress"
              >
                View
              </button>
            )}
          </div>

          {inputError && (
            <pre className="whitespace-pre-wrap break-words rounded border border-accent-iuu/40 bg-accent-iuu/10 p-2 text-[11px] text-accent-iuu">
              {inputError}
            </pre>
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
