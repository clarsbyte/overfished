import { Anchor, Filter, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { SOURCE_COLOR, SOURCE_LABEL, type Ship, type ShipSource } from "@/types/ship";

interface Props {
  ships: Ship[];
  bySource: Record<ShipSource, number>;
  selected: Ship | null;
  isLoading: boolean;
  errors: string[];
  renderer: "globe" | "mapbox";
  onSelect: (ship: Ship) => void;
}

const ALL_SOURCES: ShipSource[] = [
  "backend-galapagos",
  "backend-global",
  "sar-detections",
  "sar-enriched",
];

export function Sidebar({ ships, bySource, selected, isLoading, errors, renderer, onSelect }: Props) {
  const [enabledSources, setEnabledSources] = useState<Set<ShipSource>>(
    new Set(ALL_SOURCES),
  );
  const [flag, setFlag] = useState<string>("");
  const [highRiskOnly, setHighRiskOnly] = useState(false);
  const [search, setSearch] = useState("");

  const flags = useMemo(() => {
    const set = new Set<string>();
    ships.forEach((s) => s.flag && set.add(s.flag));
    return [...set].sort();
  }, [ships]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return ships.filter((s) => {
      if (!enabledSources.has(s.source)) return false;
      if (flag && s.flag !== flag) return false;
      if (highRiskOnly && !(s.isHighRisk || s.risk === "high_risk" || s.risk === "confirmed_iuu"))
        return false;
      if (q) {
        const hay = `${s.mmsi} ${s.name ?? ""} ${s.flag ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [ships, enabledSources, flag, highRiskOnly, search]);

  const toggleSource = (s: ShipSource) => {
    setEnabledSources((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  };

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-white/15 px-4 py-3">
        <div className="flex items-center gap-2">
          <Anchor size={18} className="text-accent-safe" />
          <h1 className="font-display text-lg font-semibold tracking-wide">Overfish AI</h1>
        </div>
        <p className="mt-0.5 text-xs text-slate2-400">
          {renderer === "globe" ? "Globe default" : "Mapbox fallback"} + FastAPI{" "}
          {isLoading ? "loading..." : `${ships.length.toLocaleString()} vessels`}
        </p>
      </header>

      <section className="space-y-3 border-b border-white/15 px-4 py-3">
        <div className="flex items-center gap-1 text-xs uppercase tracking-wider text-slate2-400">
          <Filter size={12} /> Sources
        </div>
        <div className="space-y-1.5">
          {ALL_SOURCES.map((s) => {
            const on = enabledSources.has(s);
            return (
              <button
                key={s}
                onClick={() => toggleSource(s)}
                className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs transition ${
                  on ? "glass-chip text-slate2-100" : "text-slate2-300 hover:glass-chip"
                }`}
              >
                <span className="flex items-center gap-2">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ background: SOURCE_COLOR[s], opacity: on ? 1 : 0.3 }}
                  />
                  {SOURCE_LABEL[s]}
                </span>
                <span className="font-mono text-[10px] text-slate2-400">
                  {bySource[s] ?? 0}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2">
          <select
            value={flag}
            onChange={(e) => setFlag(e.target.value)}
            className="glass-chip flex-1 rounded-md px-2 py-1 text-xs text-slate2-100 focus:border-accent-safe focus:outline-none"
          >
            <option value="">All flags</option>
            {flags.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-slate2-400">
            <input
              type="checkbox"
              checked={highRiskOnly}
              onChange={(e) => setHighRiskOnly(e.target.checked)}
              className="accent-accent-iuu"
            />
            High-risk
          </label>
        </div>

        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate2-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search MMSI / name / flag"
            className="glass-chip w-full rounded-md py-1.5 pl-7 pr-2 text-xs text-slate2-100 placeholder:text-slate2-400 focus:border-accent-safe focus:outline-none"
          />
        </div>
      </section>

      <ul className="flex-1 overflow-y-auto px-2 py-2 text-xs">
        {filtered.length === 0 && !isLoading && (
          <li className="px-2 py-3 text-slate2-400">No vessels match.</li>
        )}
        {filtered.map((s) => {
          const isSel = selected?.mmsi === s.mmsi;
          const color = SOURCE_COLOR[s.source];
          return (
            <li key={`${s.source}:${s.mmsi}`}>
              <button
                onClick={() => onSelect(s)}
                className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left transition ${
                  isSel ? "glass-chip text-slate2-100" : "text-slate2-300 hover:glass-chip"
                }`}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span
                    className="inline-block h-2 w-2 shrink-0 rounded-full"
                    style={{ background: color }}
                  />
                  <span className="min-w-0 truncate">
                    <span className="text-slate2-200">{s.name ?? s.mmsi}</span>
                    {s.flag && <span className="ml-1 text-[10px] text-slate2-400">{s.flag}</span>}
                  </span>
                </span>
                <span className="font-mono text-[10px] text-slate2-400">
                  {s.lat.toFixed(1)},{s.lon.toFixed(1)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {errors.length > 0 && (
        <div className="border-t border-white/15 px-4 py-2 text-[11px] text-accent-suspect">
          {errors.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </div>
      )}
    </div>
  );
}
