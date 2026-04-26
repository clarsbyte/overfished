import { api } from "@/lib/api";
import type { DocumentArtifact, Vessel } from "@/types/schemas";
import type { Ship } from "@/types/ship";
import { useQuery } from "@tanstack/react-query";
import type { FeatureCollection } from "geojson";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  AlertTriangle,
  Bot,
  Check,
  ChevronRight,
  CircleDot,
  Download,
  Eye,
  Loader2,
  PlayCircle,
  Search,
  Ship as ShipIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useGlobeControlsContext } from "../GlobeControlsContext";
import { LiquidGlass } from "../LiquidGlass";
import { AgentsPanel } from "@/components/panels/AgentsPanel";
import { SequenceModelsPanel } from "@/components/panels/SequenceModelsPanel";
import { SpeciesExposurePanel } from "@/components/panels/SpeciesExposurePanel";

type RegionRisk = "confirmed_iuu" | "high_risk" | "suspect" | "safe";

const RISK_LABEL: Record<RegionRisk, string> = {
  confirmed_iuu: "IUU CONFIRMED",
  high_risk: "HIGH RISK",
  suspect: "SUSPECT",
  safe: "SAFE",
};

const RISK_ICON: Record<RegionRisk, { color: string; Icon: typeof AlertTriangle }> = {
  confirmed_iuu: { color: "text-red-500", Icon: AlertTriangle },
  high_risk: { color: "text-orange-400", Icon: AlertTriangle },
  suspect: { color: "text-yellow-400", Icon: AlertCircle },
  safe: { color: "text-cyan-400", Icon: AlertCircle },
};

const DOC_LABELS: Record<DocumentArtifact["doc_type"], string> = {
  notice_of_violation: "Notice of Violation",
  cease_and_desist_order: "Cease & Desist Order",
  port_inspection_order: "Port Inspection Order",
  evidence_package: "Evidence Package",
  combined_legal_package: "Combined Legal Package",
};

interface SourceVessel {
  mmsi: string;
  name: string;
  flag: string;
  risk: RegionRisk;
  source: "galapagos" | "global";
  raw?: Vessel;
}
type OpsTab = "intel" | "controls" | "agent";

interface Props {
  selectedVessel: Vessel | null;
  documents: DocumentArtifact[];
  activeRegionName?: string | null;
  onSelectVessel: (vessel: Vessel) => void;
  onSelectRegion: (regionId: string) => void;
  onRunDemo: () => void;
  onNotifyPort: () => void;
  onPreview: (doc: DocumentArtifact) => void;
  runDemoPending: boolean;
  notifyPortPending: boolean;
  demoRunning: boolean;
  demoError?: string | null;
  lastPortCall?: { endLat: number; endLng: number } | null;
  bySource?: Record<string, number>;
  selectedShip?: Ship | null;
  onSpeciesHighlightChange?: (geojson: FeatureCollection | null) => void;
}

const SOURCE_META: Record<string, { label: string; short: string; color: string }> = {
  "backend-galapagos": { label: "Galápagos",    short: "GAL", color: "text-cyan-400 bg-cyan-500/15 border-cyan-500/30" },
  "backend-global":    { label: "Global AIS",   short: "AIS", color: "text-violet-400 bg-violet-500/15 border-violet-500/30" },
  "sar-detections":    { label: "SAR Detect.",  short: "SAR", color: "text-amber-400 bg-amber-500/15 border-amber-500/30" },
  "sar-enriched":      { label: "SAR Enriched", short: "ENR", color: "text-emerald-400 bg-emerald-500/15 border-emerald-500/30" },
};

// Map bySource keys to SourceVessel.source for filtering
const SOURCE_TO_VESSEL: Record<string, SourceVessel["source"]> = {
  "backend-galapagos": "galapagos",
  "backend-global":    "global",
};

export function OpsView({
  selectedVessel,
  documents,
  activeRegionName,
  onSelectVessel,
  onSelectRegion,
  onRunDemo,
  onNotifyPort,
  onPreview,
  runDemoPending,
  notifyPortPending,
  demoRunning,
  demoError,
  lastPortCall,
  bySource,
  selectedShip,
  onSpeciesHighlightChange,
}: Props) {
  const [query, setQuery] = useState("");
  const [highRiskOnly, setHighRiskOnly] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<OpsTab>("intel");
  const [approaches, setApproaches] = useState(1);
  const [seqLen, setSeqLen] = useState(3);
  const [hidden, setHidden] = useState(5);

  const { controls, setControl, toggleLayer } = useGlobeControlsContext();

  const vesselsQ = useQuery({ queryKey: ["vessels"], queryFn: () => api.vessels() });
  const globalTracksQ = useQuery({
    queryKey: ["globalTracks"],
    queryFn: () => api.globalVesselTracks(),
  });
  const regionsQ = useQuery({ queryKey: ["fisheryRegions"], queryFn: () => api.fisheryRegions() });
  const heatmapQ = useQuery({ queryKey: ["heatmap"], queryFn: () => api.heatmap() });
  const fineQ = useQuery({ queryKey: ["fine", "demo"], queryFn: () => api.caseFine("demo") });

  const regions = regionsQ.data ?? [];
  const alerts = useMemo(
    () =>
      regions
        .filter((r) => r.risk !== "safe")
        .sort((a, b) => rankRisk(b.risk) - rankRisk(a.risk))
        .slice(0, 5),
    [regions],
  );

  // Combined vessel list: galapagos + global tracks, deduped by MMSI
  const allVessels = useMemo<SourceVessel[]>(() => {
    const seen = new Set<string>();
    const out: SourceVessel[] = [];
    for (const v of vesselsQ.data ?? []) {
      seen.add(v.mmsi);
      out.push({ mmsi: v.mmsi, name: v.name ?? v.mmsi, flag: v.flag ?? "", risk: "confirmed_iuu", source: "galapagos", raw: v });
    }
    for (const t of globalTracksQ.data ?? []) {
      if (seen.has(t.mmsi)) continue;
      seen.add(t.mmsi);
      out.push({ mmsi: t.mmsi, name: t.name ?? t.mmsi, flag: t.flag ?? "", risk: t.risk as RegionRisk, source: "global" });
    }
    return out;
  }, [vesselsQ.data, globalTracksQ.data]);

  const filteredVessels = useMemo(() => {
    const q = query.trim().toLowerCase();
    const vesselSource = sourceFilter ? SOURCE_TO_VESSEL[sourceFilter] : null;
    return allVessels
      .filter((v) => {
        if (vesselSource && v.source !== vesselSource) return false;
        if (highRiskOnly && v.risk !== "confirmed_iuu" && v.risk !== "high_risk") return false;
        if (!q) return true;
        return v.name.toLowerCase().includes(q) || v.mmsi.includes(q) || v.flag.toLowerCase().includes(q);
      })
      .sort((a, b) => rankRisk(b.risk) - rankRisk(a.risk));
  }, [allVessels, highRiskOnly, query, sourceFilter]);

  const totalBySource = useMemo(() => {
    const total = Object.values(bySource ?? {}).reduce((s, n) => s + n, 0) || 1;
    return Object.entries(bySource ?? {}).map(([key, count]) => ({ key, count, pct: count / total }));
  }, [bySource]);

  const galCount = vesselsQ.data?.length ?? 0;
  const globalCount = globalTracksQ.data?.length ?? 0;
  const totalVessels = galCount + globalCount;
  const iuuCount = allVessels.filter((v) => v.risk === "confirmed_iuu" || v.risk === "high_risk").length;

  return (
    <aside className="w-[360px] h-full flex flex-col gap-4 p-4 pointer-events-auto overflow-y-auto">

      {/* ── Summary stats ──────────────────────────────────────── */}
      <LiquidGlass className="rounded-[30px] flex-shrink-0" chromaticAberration={2} depth={8}>
        <div className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Fleet Overview</h2>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)] animate-pulse" />
              <span className="text-[10px] font-bold text-emerald-500 uppercase tracking-widest">Live</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <OverviewStat
              value={totalVessels}
              label="Total Vessels"
              loading={vesselsQ.isLoading || globalTracksQ.isLoading}
            />
            <OverviewStat
              value={iuuCount}
              label="IUU / High-Risk"
              loading={vesselsQ.isLoading || globalTracksQ.isLoading}
              danger
            />
            <OverviewStat
              value={alerts.length}
              label="Active Alerts"
              loading={regionsQ.isLoading}
            />
          </div>
          <div className="flex justify-between text-[11px] text-slate-500 border-t border-white/10 pt-3">
            <span>Galápagos fleet <span className="text-slate-300 font-semibold">{galCount}</span></span>
            <span>Global tracks <span className="text-slate-300 font-semibold">{globalCount}</span></span>
            <span>SAR pts <span className="text-slate-300 font-semibold">{heatmapQ.data?.length ?? 0}</span></span>
          </div>
          <div className="text-[11px] text-slate-500 truncate">
            Region: <span className="text-slate-300">{activeRegionName ?? "Galápagos Marine Reserve"}</span>
          </div>
        </div>
      </LiquidGlass>

      <LiquidGlass className="rounded-[30px] flex-shrink-0" chromaticAberration={2} depth={8}>
        <div className="p-2">
          <div className="grid grid-cols-3 gap-1">
            {([
              { id: "intel" as const, label: "Intel" },
              { id: "controls" as const, label: "Controls" },
              { id: "agent" as const, label: "Agent" },
            ]).map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-2 rounded-xl text-[10px] font-bold uppercase tracking-widest transition-colors ${
                  activeTab === tab.id
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </LiquidGlass>

      {activeTab === "intel" && (
        <>
          {/* ── Vessel list ────────────────────────────────────────── */}
          <LiquidGlass className="rounded-[30px] flex-shrink-0" chromaticAberration={2} depth={8}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Sources</h2>
                <label className="flex items-center gap-1.5 text-[10px] font-medium text-slate-400 cursor-pointer">
                  <input type="checkbox" checked={highRiskOnly} onChange={() => setHighRiskOnly((v) => !v)} className="accent-red-400 w-3 h-3" />
                  High-risk
                </label>
              </div>

              {/* Source overview: stacked bar + filter chips */}
              {totalBySource.length > 0 && (
                <div className="space-y-2">
                  {/* Proportional bar */}
                  <div className="flex h-1.5 rounded-full overflow-hidden gap-px">
                    {totalBySource.map(({ key, pct }) => {
                      const meta = SOURCE_META[key];
                      const barColor = key === "backend-galapagos" ? "bg-cyan-500"
                        : key === "backend-global" ? "bg-violet-500"
                        : key === "sar-detections" ? "bg-amber-500"
                        : "bg-emerald-500";
                      return (
                        <div
                          key={key}
                          title={`${meta?.label ?? key}: ${Math.round(pct * 100)}%`}
                          style={{ width: `${pct * 100}%` }}
                          className={`${barColor} opacity-70 transition-all`}
                        />
                      );
                    })}
                  </div>
                  {/* Filter chips */}
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      onClick={() => setSourceFilter(null)}
                      className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-semibold border transition-colors ${
                        sourceFilter === null
                          ? "text-slate-100 bg-white/15 border-white/25"
                          : "text-slate-400 bg-transparent border-white/10 hover:border-white/20"
                      }`}
                    >
                      All
                      <span className="font-mono opacity-70">{allVessels.length}</span>
                    </button>
                    {totalBySource.map(({ key, count }) => {
                      const meta = SOURCE_META[key] ?? { label: key, short: key.toUpperCase(), color: "text-slate-400 bg-white/10 border-white/20" };
                      const active = sourceFilter === key;
                      return (
                        <button
                          key={key}
                          onClick={() => setSourceFilter(active ? null : key)}
                          className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-semibold border transition-colors ${
                            active ? meta.color : "text-slate-400 bg-transparent border-white/10 hover:border-white/20 hover:text-slate-200"
                          }`}
                        >
                          {meta.label}
                          <span className="font-mono opacity-70">{count}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search MMSI / name / flag"
                  className="w-full pl-9 pr-3 py-2 rounded-xl bg-white/5 border border-white/10 text-[12px] text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/40 transition-colors"
                />
              </div>
              <div className="max-h-[360px] overflow-y-auto space-y-0.5">
                {(vesselsQ.isLoading || globalTracksQ.isLoading) && (
                  <div className="flex items-center gap-2 text-xs text-slate-500 py-3 justify-center">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading vessels…
                  </div>
                )}
                {!vesselsQ.isLoading && !globalTracksQ.isLoading && filteredVessels.length === 0 && (
                  <div className="text-xs text-slate-500 text-center py-2">No vessels match filter</div>
                )}
                {filteredVessels.map((v) => {
                  const { color, Icon } = RISK_ICON[v.risk];
                  const isActive = selectedVessel?.mmsi === v.mmsi;
                  return (
                    <button
                      key={v.mmsi}
                      onClick={() =>
                        onSelectVessel(v.raw ?? ({ mmsi: v.mmsi, name: v.name, flag: v.flag, authorizations: [] } as Vessel))
                      }
                      className={`w-full flex gap-3 group cursor-pointer p-2 -mx-2 rounded-xl transition-colors text-left ${
                        isActive ? "bg-cyan-500/15 border border-cyan-500/25" : "hover:bg-white/5 border border-transparent"
                      }`}
                    >
                      <div className="mt-0.5 flex-shrink-0">
                        <Icon className={`w-4 h-4 ${color}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between items-start gap-2">
                          <h4 className="text-[13px] font-semibold text-slate-100 truncate">{v.name}</h4>
                          <span className="text-[10px] text-slate-500 flex-shrink-0">{v.flag || "UNK"}</span>
                        </div>
                        <p className="text-[11px] text-slate-500 truncate">
                          MMSI {v.mmsi} · {RISK_LABEL[v.risk]}
                          {" · "}
                          <span className={`text-[10px] font-semibold ${v.source === "galapagos" ? "text-cyan-500/70" : "text-violet-500/70"}`}>
                            {v.source === "galapagos" ? "GAL" : "AIS"}
                          </span>
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </LiquidGlass>

          {/* ── Live Alerts ────────────────────────────────────────── */}
          <LiquidGlass className="rounded-[30px] flex-shrink-0" chromaticAberration={2} depth={8}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Live Alerts</h2>
                <span className="text-[10px] font-mono text-slate-500">{alerts.length} active</span>
              </div>
              <div className="space-y-3">
                {regionsQ.isLoading && (
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <Loader2 className="w-3 h-3 animate-spin" /> loading…
                  </div>
                )}
                {!regionsQ.isLoading && alerts.length === 0 && (
                  <div className="text-xs text-slate-500">No active alerts.</div>
                )}
                {alerts.map((r) => {
                  const { color, Icon } = RISK_ICON[r.risk];
                  return (
                    <button
                      key={r.region_id}
                      onClick={() => onSelectRegion(r.region_id)}
                      className="w-full flex gap-3 group cursor-pointer hover:bg-white/5 p-2 -mx-2 rounded-xl transition-colors text-left"
                    >
                      <div className="mt-0.5">
                        <Icon className={`w-4 h-4 ${color}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between items-start gap-2">
                          <h4 className="text-[13px] font-semibold text-slate-100 truncate">{r.name}</h4>
                        </div>
                        <p className="text-[11px] text-slate-500 truncate">{RISK_LABEL[r.risk]}</p>
                      </div>
                      <ChevronRight className="w-4 h-4 text-slate-600 mt-0.5 flex-shrink-0 group-hover:text-slate-400 transition-colors" />
                    </button>
                  );
                })}
              </div>
            </div>
          </LiquidGlass>

          {/* ── Species & IUU Exposure ──────────────────────────────── */}
          <SpeciesExposurePanel onHighlightChange={onSpeciesHighlightChange ?? (() => {})} />
        </>
      )}

      {activeTab === "controls" && (
        <>
          {/* ── Layers ─────────────────────────────────────────────── */}
          <LiquidGlass className="rounded-[30px] flex-shrink-0" chromaticAberration={2} depth={8}>
            <div className="p-5 space-y-4">
              <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Globe Layers</h2>
              <div className="space-y-1">
                {([
                  { key: "showVessels" as const, label: "Vessel Traffic" },
                  { key: "showPaths" as const, label: "Flight Paths" },
                  { key: "showHeatmap" as const, label: "Fishing Heatmap" },
                  { key: "showPoints" as const, label: "AIS Points" },
                ]).map(({ key, label }) => (
                  <LayerToggle key={key} label={label} checked={controls[key]} onClick={() => toggleLayer(key)} />
                ))}
              </div>
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">Traffic Density</span>
                  <span className="text-sm font-bold text-slate-200 tabular-nums">{controls.flightCount}</span>
                </div>
                <input
                  type="range" min={0} max={350} step={10}
                  value={controls.flightCount}
                  onChange={(e) => setControl("flightCount", Number(e.target.value))}
                  className="w-full accent-cyan-400"
                />
              </div>
            </div>
          </LiquidGlass>

          {/* ── Agents ─────────────────────────────────────────────── */}
          <LiquidGlass className="rounded-[30px] flex-shrink-0" chromaticAberration={2} depth={8}>
            <div className="p-5 space-y-4">
              <div className="flex items-center gap-2">
                <Bot className="w-4 h-4 text-cyan-400" />
                <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Agents</h2>
                <span className="text-[10px] text-slate-500">RNN · BI-LSTM</span>
              </div>
              <div className="space-y-3">
                <AgentSlider label="Epochs" value={approaches} min={1} max={4} onChange={setApproaches} />
                <AgentSlider label="Seq Len" value={seqLen} min={1} max={8} onChange={setSeqLen} />
                <AgentSlider label="Hidden" value={hidden} min={2} max={12} onChange={setHidden} />
              </div>
              <button
                onClick={onRunDemo}
                disabled={demoRunning}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/25 text-cyan-300 text-[11px] font-bold uppercase tracking-widest hover:bg-cyan-500/20 disabled:opacity-50 transition-colors"
              >
                {demoRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PlayCircle className="w-3.5 h-3.5" />}
                {demoRunning ? "Running…" : "Run RNN + BI-LSTM"}
              </button>
            </div>
          </LiquidGlass>

        </>
      )}

      {activeTab === "agent" && (
        <>
          {/* ── AI Agents ────────────────────────────────────────────── */}
          <LiquidGlass className="rounded-[30px] flex-shrink-0 overflow-hidden" chromaticAberration={2} depth={8}>
            <AgentsPanel
              selectedShip={selectedShip ?? null}
              className="pointer-events-auto w-full rounded-[30px]"
            />
          </LiquidGlass>

          {/* ── Sequence Models ──────────────────────────────────────── */}
          <LiquidGlass className="rounded-[30px] flex-shrink-0 overflow-hidden" chromaticAberration={2} depth={8}>
            <SequenceModelsPanel
              className="pointer-events-auto w-full rounded-[30px]"
            />
          </LiquidGlass>
        </>
      )}

      {/* bottom spacer for bottom bar */}
      <div className="h-20 flex-shrink-0" />
    </aside>
  );
}

function rankRisk(risk: RegionRisk): number {
  return risk === "confirmed_iuu" ? 3 : risk === "high_risk" ? 2 : risk === "suspect" ? 1 : 0;
}

function OverviewStat({ value, label, loading, danger }: { value: number; label: string; loading?: boolean; danger?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <span className={`text-xl font-bold tracking-tight tabular-nums ${danger && value > 0 ? "text-red-400" : "text-slate-100"}`}>
        {loading ? "…" : value}
      </span>
      <span className="text-[9px] font-bold text-slate-500 uppercase tracking-tighter leading-tight">{label}</span>
    </div>
  );
}

function LayerToggle({ label, checked, onClick }: { label: string; checked: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center justify-between py-2 px-1 rounded-lg hover:bg-white/5 transition-colors"
    >
      <span className={`text-[13px] font-medium transition-colors ${checked ? "text-slate-100" : "text-slate-500"}`}>{label}</span>
      <span className={`relative inline-flex h-5 w-9 rounded-full transition-colors ${checked ? "bg-cyan-500/50" : "bg-slate-700"}`}>
        <span className={`absolute top-[3px] w-3.5 h-3.5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
      </span>
    </button>
  );
}

function AgentSlider({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (v: number) => void }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wide w-16 flex-shrink-0">{label}</span>
      <input
        type="range" min={min} max={max} step={1} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 accent-cyan-400"
      />
      <span className="text-sm font-bold text-slate-200 tabular-nums w-5 text-right flex-shrink-0">{value}</span>
    </div>
  );
}

function CaseStatusRow({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">{label}</span>
      <span className={`text-sm font-bold tabular-nums flex items-center gap-1.5 ${ok ? "text-emerald-400" : "text-amber-400"}`}>
        <CircleDot className="w-3 h-3" />
        {value}
      </span>
    </div>
  );
}
